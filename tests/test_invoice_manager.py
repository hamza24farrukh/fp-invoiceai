"""Tests for the InvoiceManager class."""

import pytest


class TestInvoiceManagerCRUD:
    """Test basic CRUD operations."""

    def test_add_invoice(self, invoice_manager, sample_invoice_data):
        invoice_id = invoice_manager.add_invoice(sample_invoice_data)
        assert invoice_id > 0

    def test_get_invoice(self, invoice_manager, sample_invoice_data):
        invoice_id = invoice_manager.add_invoice(sample_invoice_data)
        invoice = invoice_manager.get_invoice(invoice_id)
        assert invoice is not None
        assert invoice['transactor'] == 'Test Supplier Ltd'
        assert invoice['invoice_number'] == 'INV-2024-001'

    def test_get_all_invoices(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        second = sample_invoice_data.copy()
        second['invoice_number'] = 'INV-2024-002'
        invoice_manager.add_invoice(second)

        all_invoices = invoice_manager.get_all_invoices()
        assert len(all_invoices) == 2

    def test_update_invoice(self, invoice_manager, sample_invoice_data):
        invoice_id = invoice_manager.add_invoice(sample_invoice_data)
        result = invoice_manager.update_invoice(invoice_id, {'transactor': 'Updated Supplier'})
        assert result is True

        updated = invoice_manager.get_invoice(invoice_id)
        assert updated['transactor'] == 'Updated Supplier'

    def test_delete_invoice(self, invoice_manager, sample_invoice_data):
        invoice_id = invoice_manager.add_invoice(sample_invoice_data)
        result = invoice_manager.delete_invoice(invoice_id)
        assert result is True

        deleted = invoice_manager.get_invoice(invoice_id)
        assert deleted is None

    def test_delete_all_invoices(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        invoice_manager.add_invoice(sample_invoice_data)

        result = invoice_manager.delete_all_invoices()
        assert result is True
        assert len(invoice_manager.get_all_invoices()) == 0


class TestInvoiceManagerFiltering:
    """Test filtering and query operations."""

    def test_find_invoice_by_number(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        found = invoice_manager.find_invoice_by_number('INV-2024-001')
        assert found is not None
        assert found['invoice_number'] == 'INV-2024-001'

    def test_find_invoice_by_number_not_found(self, invoice_manager):
        found = invoice_manager.find_invoice_by_number('NONEXISTENT')
        assert found is None

    def test_income_expense_filtering(self, invoice_manager, sample_invoice_data):
        # Add expense
        invoice_manager.add_invoice(sample_invoice_data)

        # Add income
        income_data = sample_invoice_data.copy()
        income_data['is_income'] = True
        income_data['invoice_number'] = 'INC-001'
        invoice_manager.add_invoice(income_data)

        expenses = invoice_manager.get_expense_invoices()
        incomes = invoice_manager.get_income_invoices()
        assert len(expenses) == 1
        assert len(incomes) == 1

    def test_get_invoices_by_transactor(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        invoices = invoice_manager.get_invoices_by_transactor('Test Supplier Ltd')
        assert len(invoices) == 1

    def test_get_invoices_by_date_range(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        invoices = invoice_manager.get_invoices_by_date_range('2024-01-01', '2024-01-31')
        assert len(invoices) == 1

        empty = invoice_manager.get_invoices_by_date_range('2025-01-01', '2025-01-31')
        assert len(empty) == 0

    def test_get_invoices_by_year_month(self, invoice_manager, sample_invoice_data):
        invoice_manager.add_invoice(sample_invoice_data)
        invoices = invoice_manager.get_invoices_by_year_month(2024, 1)
        assert len(invoices) == 1

        empty = invoice_manager.get_invoices_by_year_month(2024, 2)
        assert len(empty) == 0


class TestInvoiceManagerEdgeCases:
    """Test edge cases."""

    def test_get_nonexistent_invoice(self, invoice_manager):
        assert invoice_manager.get_invoice(9999) is None

    def test_delete_nonexistent_invoice(self, invoice_manager):
        assert invoice_manager.delete_invoice(9999) is False

    def test_update_nonexistent_invoice(self, invoice_manager):
        assert invoice_manager.update_invoice(9999, {'notes': 'test'}) is False

    def test_create_invoice_via_update_with_id_zero(self, invoice_manager, sample_invoice_data):
        result = invoice_manager.update_invoice(0, sample_invoice_data)
        assert result is True
        all_invoices = invoice_manager.get_all_invoices()
        assert len(all_invoices) == 1
