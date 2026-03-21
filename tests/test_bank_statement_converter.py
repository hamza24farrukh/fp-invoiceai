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
    """Test transaction-invoice matching."""

    def test_match_by_amount(self):
        converter = BankStatementConverter()
        statement = pd.DataFrame({
            'date': ['2024-01-15'],
            'description': ['Payment'],
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
            'total_euro': 100.00
        }]

        result = converter.match_with_invoices(statement, invoices)
        assert 'matched_supplier' in result.columns
        # Should match by amount + date proximity
        assert result.iloc[0]['matched_supplier'] == 'Test Supplier'

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
