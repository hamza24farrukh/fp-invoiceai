"""
Bank Statement Converter Module

This module provides a generic bank statement converter that can process
Excel or CSV bank statements from any bank, auto-detect the column format,
and match transactions with invoice records.
"""

import os
import re
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Common column name patterns for auto-detection
COLUMN_PATTERNS = {
    'date': [
        r'date', r'trans.*date', r'value.*date', r'booking.*date',
        r'posting.*date', r'ημερομηνία', r'datum', r'fecha'
    ],
    'description': [
        r'description', r'details', r'narrative', r'reference',
        r'particulars', r'memo', r'remark', r'περιγραφή', r'text'
    ],
    'reference': [
        r'ref(?:erence)?(?:\s*(?:no|num|number))?', r'trans.*(?:id|ref)',
        r'check.*(?:no|num)', r'αριθμός'
    ],
    'debit': [
        r'debit', r'withdrawal', r'charge', r'χρέωση', r'out',
        r'payment', r'expense'
    ],
    'credit': [
        r'credit', r'deposit', r'πίστωση', r'in', r'income', r'receipt'
    ],
    'amount': [
        r'^amount$', r'sum', r'value', r'ποσό'
    ],
    'balance': [
        r'balance', r'υπόλοιπο', r'running.*balance', r'closing.*balance'
    ]
}


class BankStatementConverter:
    """
    Convert any bank statement Excel/CSV into a standardized format
    and match transactions with invoice records.
    """

    STANDARD_COLUMNS = ['date', 'description', 'reference', 'debit', 'credit', 'balance']

    def __init__(self):
        """Initialize the bank statement converter."""
        self.column_mapping: Dict[str, str] = {}
        self.detected_format: str = "Unknown"
        self.header_row: int = 0

    def detect_format(self, file_path: str) -> Dict[str, Any]:
        """
        Auto-detect bank statement format by examining headers and structure.

        Args:
            file_path: Path to the bank statement file (Excel or CSV)

        Returns:
            Dictionary with format detection results including
            'detected_format', 'column_mapping', 'header_row', 'confidence'
        """
        try:
            df, header_row = self._read_file_with_header_detection(file_path)

            if df is None or df.empty:
                return {
                    'detected_format': 'Unknown',
                    'column_mapping': {},
                    'header_row': 0,
                    'confidence': 0.0,
                    'columns_found': []
                }

            self.header_row = header_row
            mapping = self._auto_map_columns(df)
            self.column_mapping = mapping

            # Calculate confidence based on how many standard columns we matched
            matched = sum(1 for v in mapping.values() if v is not None)
            total_needed = 4  # date, description, and at least debit or credit or amount
            confidence = min(matched / total_needed, 1.0)

            # Determine format name
            self.detected_format = self._guess_bank_format(df, file_path)

            result = {
                'detected_format': self.detected_format,
                'column_mapping': mapping,
                'header_row': header_row,
                'confidence': confidence,
                'columns_found': list(df.columns),
                'row_count': len(df)
            }

            logger.info(f"Detected format: {self.detected_format} with confidence {confidence:.0%}")
            return result

        except Exception as e:
            logger.error(f"Error detecting format: {str(e)}")
            return {
                'detected_format': 'Unknown',
                'column_mapping': {},
                'header_row': 0,
                'confidence': 0.0,
                'error': str(e)
            }

    def convert(self, file_path: str, column_mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        """
        Convert bank statement to standard format.

        Args:
            file_path: Path to the bank statement file
            column_mapping: Optional manual column mapping. If None, auto-detects.
                           Format: {'date': 'Date Column', 'description': 'Details', ...}

        Returns:
            DataFrame with standardized columns: date, description, reference, debit, credit, balance
        """
        try:
            df, _ = self._read_file_with_header_detection(file_path)

            if df is None or df.empty:
                logger.warning("No data found in bank statement file")
                return pd.DataFrame(columns=self.STANDARD_COLUMNS)

            # Use provided mapping or auto-detect
            if column_mapping:
                self.column_mapping = column_mapping
            elif not self.column_mapping:
                self.column_mapping = self._auto_map_columns(df)

            # Build standardized DataFrame
            result = pd.DataFrame()

            for std_col in self.STANDARD_COLUMNS:
                source_col = self.column_mapping.get(std_col)
                if source_col and source_col in df.columns:
                    result[std_col] = df[source_col]
                else:
                    result[std_col] = None

            # Handle case where there's a single 'amount' column instead of debit/credit
            amount_col = self.column_mapping.get('amount')
            if amount_col and amount_col in df.columns:
                if result['debit'].isna().all() and result['credit'].isna().all():
                    amounts = pd.to_numeric(df[amount_col], errors='coerce')
                    result['debit'] = amounts.where(amounts < 0).abs()
                    result['credit'] = amounts.where(amounts > 0)

            # Clean and normalize
            result = self._normalize_dataframe(result)

            # Remove completely empty rows
            result = result.dropna(how='all', subset=['description', 'debit', 'credit'])

            logger.info(f"Converted {len(result)} transactions to standard format")
            return result

        except Exception as e:
            logger.error(f"Error converting bank statement: {str(e)}")
            return pd.DataFrame(columns=self.STANDARD_COLUMNS)

    def match_with_invoices(
        self,
        statement_df: pd.DataFrame,
        invoices: List[Dict[str, Any]],
        date_tolerance_days: int = 7,
        amount_tolerance: float = 0.01
    ) -> pd.DataFrame:
        """
        Match bank statement transactions with invoice records.

        Args:
            statement_df: Standardized bank statement DataFrame
            invoices: List of invoice dictionaries from InvoiceManager
            date_tolerance_days: Maximum days difference for date matching
            amount_tolerance: Maximum amount difference for matching

        Returns:
            DataFrame with additional columns: matched_supplier, matched_invoice_number,
            match_confidence, match_method
        """
        result = statement_df.copy()
        result['matched_supplier'] = None
        result['matched_invoice_number'] = None
        result['match_confidence'] = 0.0
        result['match_method'] = None

        if not invoices:
            logger.warning("No invoices provided for matching")
            return result

        for idx, row in result.iterrows():
            best_match = self._find_best_match(row, invoices, date_tolerance_days, amount_tolerance)
            if best_match:
                result.at[idx, 'matched_supplier'] = best_match.get('transactor')
                result.at[idx, 'matched_invoice_number'] = best_match.get('invoice_number')
                result.at[idx, 'match_confidence'] = best_match.get('confidence', 0.0)
                result.at[idx, 'match_method'] = best_match.get('method')

        matched_count = result['matched_supplier'].notna().sum()
        logger.info(f"Matched {matched_count}/{len(result)} transactions with invoices")
        return result

    def _read_file_with_header_detection(self, file_path: str) -> Tuple[Optional[pd.DataFrame], int]:
        """
        Read file and auto-detect the header row.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (DataFrame, header_row_index)
        """
        ext = os.path.splitext(file_path)[1].lower()

        # Try reading with different header rows (some bank statements have metadata rows)
        for header_row in range(0, 10):
            try:
                if ext == '.csv':
                    df = pd.read_csv(file_path, header=header_row)
                else:
                    df = pd.read_excel(file_path, header=header_row)

                # Check if this looks like a valid header
                if self._is_valid_header(df):
                    logger.info(f"Detected header at row {header_row}")
                    return df, header_row

            except Exception:
                continue

        # Fallback: try row 0
        try:
            if ext == '.csv':
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            return df, 0
        except Exception as e:
            logger.error(f"Failed to read file: {str(e)}")
            return None, 0

    def _is_valid_header(self, df: pd.DataFrame) -> bool:
        """
        Check if a DataFrame has a valid-looking header row.

        Args:
            df: DataFrame to check

        Returns:
            True if the header looks valid
        """
        if df.empty or len(df.columns) < 2:
            return False

        # Check if column names are strings (not numbers)
        string_cols = sum(1 for col in df.columns if isinstance(col, str) and not col.startswith('Unnamed'))
        return string_cols >= 2

    def _auto_map_columns(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Auto-detect which DataFrame columns correspond to standard fields.

        Args:
            df: DataFrame with bank statement data

        Returns:
            Dictionary mapping standard column names to actual column names
        """
        mapping: Dict[str, Optional[str]] = {col: None for col in self.STANDARD_COLUMNS}
        used_columns: set = set()

        for std_col, patterns in COLUMN_PATTERNS.items():
            if std_col == 'amount':
                continue  # Handle amount after debit/credit

            for col_name in df.columns:
                if col_name in used_columns:
                    continue

                col_str = str(col_name).lower().strip()
                for pattern in patterns:
                    if re.search(pattern, col_str, re.IGNORECASE):
                        if std_col in mapping and mapping[std_col] is None:
                            mapping[std_col] = col_name
                            used_columns.add(col_name)
                            logger.debug(f"Mapped '{col_name}' -> '{std_col}'")
                            break

        # If no debit/credit found, look for a single amount column
        if mapping.get('debit') is None and mapping.get('credit') is None:
            for col_name in df.columns:
                if col_name in used_columns:
                    continue
                col_str = str(col_name).lower().strip()
                for pattern in COLUMN_PATTERNS['amount']:
                    if re.search(pattern, col_str, re.IGNORECASE):
                        mapping['amount'] = col_name
                        used_columns.add(col_name)
                        break

        return mapping

    def _guess_bank_format(self, df: pd.DataFrame, file_path: str) -> str:
        """
        Try to guess the bank format from file name or content patterns.

        Args:
            df: DataFrame with bank data
            file_path: Path to the file

        Returns:
            String describing the detected bank format
        """
        filename = os.path.basename(file_path).lower()

        # Try to identify common formats from filename
        format_hints = {
            'chase': 'Chase Bank',
            'hsbc': 'HSBC',
            'barclays': 'Barclays',
            'wells_fargo': 'Wells Fargo',
            'bank_of_america': 'Bank of America',
            'revolut': 'Revolut',
            'wise': 'Wise (TransferWise)',
            'paypal': 'PayPal',
            'stripe': 'Stripe',
        }

        for keyword, bank_name in format_hints.items():
            if keyword in filename.replace(' ', '_'):
                return bank_name

        # Generic format based on column count
        col_count = len(df.columns)
        if col_count <= 4:
            return "Simple Statement Format"
        elif col_count <= 7:
            return "Standard Statement Format"
        else:
            return "Extended Statement Format"

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize and clean the standardized DataFrame.

        Args:
            df: DataFrame with standardized columns

        Returns:
            Cleaned DataFrame
        """
        result = df.copy()

        # Normalize date column
        if 'date' in result.columns:
            result['date'] = pd.to_datetime(result['date'], errors='coerce', dayfirst=True)
            result['date'] = result['date'].dt.strftime('%Y-%m-%d')

        # Normalize amount columns
        for col in ['debit', 'credit', 'balance']:
            if col in result.columns:
                result[col] = pd.to_numeric(
                    result[col].astype(str).str.replace(',', '.').str.replace(r'[^\d.\-]', '', regex=True),
                    errors='coerce'
                )

        # Clean description
        if 'description' in result.columns:
            result['description'] = result['description'].astype(str).str.strip()
            result['description'] = result['description'].replace('nan', '')

        return result

    def _find_best_match(
        self,
        transaction: pd.Series,
        invoices: List[Dict[str, Any]],
        date_tolerance_days: int,
        amount_tolerance: float
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best matching invoice for a bank transaction.

        Args:
            transaction: A row from the standardized bank statement
            invoices: List of invoice dictionaries
            date_tolerance_days: Max days difference for date matching
            amount_tolerance: Max amount difference for matching

        Returns:
            Best matching invoice dict with 'confidence' and 'method' keys, or None
        """
        best_match = None
        best_score = 0.0

        trans_amount = transaction.get('debit') or transaction.get('credit') or 0.0
        trans_date = transaction.get('date', '')
        trans_desc = str(transaction.get('description', '')).lower()

        for invoice in invoices:
            score = 0.0
            method_parts = []

            # Amount matching
            invoice_amount = invoice.get('amount') or invoice.get('total_euro') or 0.0
            if invoice_amount and trans_amount:
                try:
                    amount_diff = abs(float(trans_amount) - float(invoice_amount))
                    if amount_diff <= amount_tolerance:
                        score += 0.5
                        method_parts.append('exact_amount')
                    elif amount_diff <= float(invoice_amount) * 0.05:
                        score += 0.3
                        method_parts.append('close_amount')
                except (ValueError, TypeError):
                    pass

            # Date matching
            invoice_date = invoice.get('date', '')
            if trans_date and invoice_date:
                try:
                    t_date = datetime.strptime(str(trans_date)[:10], '%Y-%m-%d')
                    i_date = datetime.strptime(str(invoice_date)[:10], '%Y-%m-%d')
                    day_diff = abs((t_date - i_date).days)
                    if day_diff <= date_tolerance_days:
                        date_score = 0.3 * (1 - day_diff / date_tolerance_days)
                        score += date_score
                        method_parts.append('date_proximity')
                except (ValueError, TypeError):
                    pass

            # Supplier name matching in description
            supplier_name = str(invoice.get('transactor', '')).lower()
            if supplier_name and supplier_name in trans_desc:
                score += 0.4
                method_parts.append('supplier_name')
            elif supplier_name:
                # Partial match — check if any significant word matches
                supplier_words = [w for w in supplier_name.split() if len(w) > 3]
                matched_words = sum(1 for w in supplier_words if w in trans_desc)
                if supplier_words and matched_words > 0:
                    word_score = 0.2 * (matched_words / len(supplier_words))
                    score += word_score
                    method_parts.append('partial_name')

            # Invoice number in description
            invoice_number = str(invoice.get('invoice_number', '')).lower()
            if invoice_number and invoice_number in trans_desc:
                score += 0.3
                method_parts.append('invoice_number')

            if score > best_score and score >= 0.3:
                best_score = score
                best_match = {
                    **invoice,
                    'confidence': min(score, 1.0),
                    'method': '+'.join(method_parts)
                }

        return best_match

    def get_column_mapping_options(self, file_path: str) -> Dict[str, List[str]]:
        """
        Get available columns for manual mapping UI.

        Args:
            file_path: Path to the bank statement file

        Returns:
            Dictionary with 'columns' (list of column names) and
            'suggested_mapping' (auto-detected mapping)
        """
        try:
            df, _ = self._read_file_with_header_detection(file_path)
            if df is None:
                return {'columns': [], 'suggested_mapping': {}}

            suggested = self._auto_map_columns(df)

            return {
                'columns': list(df.columns),
                'suggested_mapping': {k: v for k, v in suggested.items() if v is not None}
            }
        except Exception as e:
            logger.error(f"Error getting column mapping options: {str(e)}")
            return {'columns': [], 'suggested_mapping': {}}
