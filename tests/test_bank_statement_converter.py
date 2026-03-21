"""Tests for the BankStatementConverter class."""

import pytest
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from bank_statement_converter import BankStatementConverter


class TestBankStatementConverterInit:
    """Test converter initialization."""

    def test_init(self):
        converter = BankStatementConverter()
        assert converter.detected_format == "Unknown"
        assert converter.column_mapping == {}
        assert converter.STANDARD_COLUMNS == ['date', 'description', 'reference', 'debit', 'credit', 'balance']


class TestAutoColumnMapping:
    """Test auto-detection of column mappings."""

    def test_detect_standard_columns(self):
        converter = BankStatementConverter()
        df = pd.DataFrame({
            'Date': ['2024-01-01'],
            'Description': ['Payment'],
            'Debit': [100.00],
            'Credit': [0],
            'Balance': [900.00]
        })
        mapping = converter._auto_map_columns(df)
        assert mapping['date'] == 'Date'
        assert mapping['description'] == 'Description'
        assert mapping['debit'] == 'Debit'
        assert mapping['credit'] == 'Credit'

    def test_detect_alternative_column_names(self):
        converter = BankStatementConverter()
        df = pd.DataFrame({
            'Transaction Date': ['2024-01-01'],
            'Details': ['Wire transfer'],
            'Withdrawal': [50.00],
            'Deposit': [0],
        })
        mapping = converter._auto_map_columns(df)
        assert mapping['date'] == 'Transaction Date'
        assert mapping['description'] == 'Details'
        assert mapping['debit'] == 'Withdrawal'
        assert mapping['credit'] == 'Deposit'


class TestConvert:
    """Test conversion to standard format."""

    def test_convert_excel_file(self, tmp_path):
        # Create test Excel file
        df = pd.DataFrame({
            'Date': ['2024-01-15', '2024-01-16'],
            'Description': ['Payment to supplier', 'Refund received'],
            'Reference': ['REF001', 'REF002'],
            'Debit': [100.00, None],
            'Credit': [None, 50.00],
            'Balance': [900.00, 950.00]
        })
        file_path = str(tmp_path / "test_statement.xlsx")
        df.to_excel(file_path, index=False)

        converter = BankStatementConverter()
        result = converter.convert(file_path)

        assert len(result) == 2
        assert 'date' in result.columns
        assert 'description' in result.columns
        assert 'debit' in result.columns
        assert 'credit' in result.columns

    def test_convert_returns_empty_for_nonexistent(self):
        converter = BankStatementConverter()
        result = converter.convert("/nonexistent/file.xlsx")
        assert len(result) == 0


class TestMatchWithInvoices:
    """Test transaction-invoice matching with currency-aware algorithm."""

    def test_match_same_currency_exact_amount(self):
        """Test matching when invoice and bank statement are in the same currency."""
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15'],
            'description': ['Payment to supplier'],
            'reference': ['REF001'],
            'debit': [100.00],
            'credit': [None],
            'balance': [900.00]
        })

        invoices = [{
            'transactor': 'Test Supplier',
            'invoice_number': 'INV-001',
            'date': '2024-01-14',
            'amount': 100.00,
            'currency': 'PKR',
            'is_income': 0
        }]

        result = converter.match_with_invoices(statement, invoices, bank_currency='PKR')
        assert 'matched_supplier' in result.columns
        assert result.iloc[0]['matched_supplier'] == 'Test Supplier'
        assert result.iloc[0]['match_confidence'] >= 50

    def test_match_cross_currency_with_transfer_fee(self):
        """Test: 520.89 USD invoice should match 139898.58 PKR bank credit (3.56% SWIFT fee deduction)."""
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2026-02-24'],
            'description': ['Inward Telex Payment G1460485528101'],
            'reference': ['FT26049P1M0S'],
            'debit': [None],
            'credit': [139898.58],
            'balance': [140957.58]
        })

        invoices = [{
            'transactor': 'Kodecraft',
            'invoice_number': '2026',
            'date': '2026-02-15',
            'amount': 520.89,
            'currency': 'USD',
            'is_income': 1
        }]

        result = converter.match_with_invoices(statement, invoices, bank_currency='PKR')
        assert result.iloc[0]['matched_supplier'] == 'Kodecraft'
        # Should have reasonable confidence (amount ~3.56% diff + date ~9 days)
        assert result.iloc[0]['match_confidence'] >= 55
        assert result.iloc[0]['match_confidence'] <= 80
        assert result.iloc[0]['converted_invoice_amount'] > 0
        assert result.iloc[0]['amount_difference_pct'] > 0

    def test_no_match_when_bank_exceeds_invoice(self):
        """Bank amount significantly exceeding converted invoice should NOT match."""
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15'],
            'description': ['Large deposit'],
            'reference': ['REF001'],
            'debit': [None],
            'credit': [500000.00],
            'balance': [600000.00]
        })

        invoices = [{
            'transactor': 'Small Vendor',
            'invoice_number': 'INV-001',
            'date': '2024-01-14',
            'amount': 100.00,
            'currency': 'USD',
            'is_income': 1
        }]

        result = converter.match_with_invoices(statement, invoices, bank_currency='PKR')
        assert result.iloc[0]['matched_supplier'] is None

    def test_debit_matches_expense_credit_matches_income(self):
        """Debit transactions should only match expense invoices, credits should match income."""
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15', '2024-01-15'],
            'description': ['Payment out', 'Payment in'],
            'reference': ['REF001', 'REF002'],
            'debit': [5000.00, None],
            'credit': [None, 5000.00],
            'balance': [95000.00, 100000.00]
        })

        expense_invoice = {
            'transactor': 'Expense Vendor',
            'invoice_number': 'EXP-001',
            'date': '2024-01-14',
            'amount': 5000.00,
            'currency': 'PKR',
            'is_income': 0
        }
        income_invoice = {
            'transactor': 'Income Client',
            'invoice_number': 'INC-001',
            'date': '2024-01-14',
            'amount': 5000.00,
            'currency': 'PKR',
            'is_income': 1
        }

        result = converter.match_with_invoices(
            statement, [expense_invoice, income_invoice], bank_currency='PKR'
        )
        # Debit row should match expense invoice
        assert result.iloc[0]['matched_supplier'] == 'Expense Vendor'
        # Credit row should match income invoice
        assert result.iloc[1]['matched_supplier'] == 'Income Client'

    def test_match_empty_invoices(self):
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15'],
            'description': ['Payment'],
            'reference': ['REF001'],
            'debit': [100.00],
            'credit': [None],
            'balance': [900.00]
        })

        result = converter.match_with_invoices(statement, [])
        assert result.iloc[0]['matched_supplier'] is None

    def test_match_output_columns_present(self):
        """Verify all new output columns are present in results."""
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15'],
            'description': ['Payment'],
            'reference': ['REF001'],
            'debit': [100.00],
            'credit': [None],
            'balance': [900.00]
        })

        result = converter.match_with_invoices(statement, [])
        for col in ['matched_supplier', 'matched_invoice_number', 'match_confidence',
                     'match_method', 'converted_invoice_amount', 'amount_difference_pct', 'match_details']:
            assert col in result.columns, f"Missing column: {col}"


class TestDetectFormat:
    """Test format detection."""

    def test_detect_format_excel(self, tmp_path):
        df = pd.DataFrame({
            'Date': ['2024-01-15'],
            'Description': ['Test'],
            'Amount': [-100.00]
        })
        file_path = str(tmp_path / "statement.xlsx")
        df.to_excel(file_path, index=False)

        converter = BankStatementConverter()
        result = converter.detect_format(file_path)

        assert 'detected_format' in result
        assert 'confidence' in result
        assert result['confidence'] > 0

    def test_detect_format_nonexistent(self):
        converter = BankStatementConverter()
        result = converter.detect_format("/nonexistent/file.xlsx")
        assert result['confidence'] == 0.0
