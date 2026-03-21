"""
Shared pytest fixtures for the InvoiceAI test suite.
"""

import os
import json
import pytest
import sys

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def temp_db(tmp_path):
    """Provide a fresh SQLite database file path for each test."""
    return str(tmp_path / "test_suppliers.db")


@pytest.fixture
def invoice_manager(temp_db):
    """Provide an InvoiceManager instance with a temporary database."""
    from invoice_manager import InvoiceManager
    return InvoiceManager(db_file=temp_db)


@pytest.fixture
def supplier_manager(tmp_path):
    """Provide a SupplierManager instance with a temporary JSON file."""
    storage_file = str(tmp_path / "test_suppliers.json")
    from supplier_manager import SupplierManager
    return SupplierManager(storage_file=storage_file)


@pytest.fixture
def sample_invoice_data():
    """Provide sample invoice data for testing."""
    return {
        'date': '2024-01-15',
        'invoice_number': 'INV-2024-001',
        'transactor': 'Test Supplier Ltd',
        'amount': 100.00,
        'vat': 20.00,
        'total_bgn': 195.58,
        'total_euro': 100.00,
        'currency': 'EUR',
        'notes': 'Test invoice',
        'is_income': False,
        'transaction_type': 'EXPENSES with VAT',
        'description': 'Test services'
    }


@pytest.fixture
def sample_supplier_data():
    """Provide sample supplier data for testing."""
    return {
        'supplier_name': 'Test Supplier Ltd',
        'category': 'Services',
        'transaction_type': 'EXPENSES with VAT',
        'vat_number': 'TEST123456'
    }


@pytest.fixture
def sample_exchange_rates(tmp_path):
    """Provide a temporary exchange rates file."""
    rates = {"USD_TO_EUR": 0.92, "BGN_TO_EUR": 0.51}
    rates_file = str(tmp_path / "test_rates.json")
    with open(rates_file, 'w') as f:
        json.dump(rates, f)
    return rates_file, rates
