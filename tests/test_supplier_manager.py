"""Tests for the SupplierManager class."""

import pytest


class TestSupplierManagerCRUD:
    """Test basic CRUD operations."""

    def test_add_supplier(self, supplier_manager, sample_supplier_data):
        result = supplier_manager.add_supplier(sample_supplier_data)
        assert result is True
        all_suppliers = supplier_manager.get_all_suppliers()
        assert len(all_suppliers) == 1

    def test_add_duplicate_supplier(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        # Adding same supplier again should return False (updated, not added)
        result = supplier_manager.add_supplier(sample_supplier_data)
        assert result is False
        assert len(supplier_manager.get_all_suppliers()) == 1

    def test_get_supplier(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        supplier = supplier_manager.get_supplier('Test Supplier Ltd')
        assert supplier is not None
        assert supplier['supplier_name'] == 'Test Supplier Ltd'

    def test_get_supplier_not_found(self, supplier_manager):
        assert supplier_manager.get_supplier('Nonexistent') is None

    def test_update_supplier(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        updated = sample_supplier_data.copy()
        updated['category'] = 'Updated Category'
        result = supplier_manager.update_supplier('Test Supplier Ltd', updated)
        assert result is True

    def test_delete_supplier(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        result = supplier_manager.delete_supplier('Test Supplier Ltd')
        assert result is True
        assert len(supplier_manager.get_all_suppliers()) == 0

    def test_delete_nonexistent_supplier(self, supplier_manager):
        assert supplier_manager.delete_supplier('Nonexistent') is False

    def test_delete_all_suppliers(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        second = sample_supplier_data.copy()
        second['supplier_name'] = 'Another Supplier'
        supplier_manager.add_supplier(second)

        result = supplier_manager.delete_all_suppliers()
        assert result is True
        assert len(supplier_manager.get_all_suppliers()) == 0


class TestSupplierManagerNormalization:
    """Test name normalization and matching."""

    def test_normalize_supplier_name(self, supplier_manager):
        assert supplier_manager.normalize_supplier_name('test supplier') == 'TEST SUPPLIER'
        assert supplier_manager.normalize_supplier_name('test_supplier') == 'TEST SUPPLIER'
        assert supplier_manager.normalize_supplier_name('test-supplier') == 'TEST SUPPLIER'

    def test_supplier_exists_case_insensitive(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        assert supplier_manager.supplier_exists('test supplier ltd') is True
        assert supplier_manager.supplier_exists('TEST SUPPLIER LTD') is True

    def test_normalize_empty_name(self, supplier_manager):
        assert supplier_manager.normalize_supplier_name('') == ''
        assert supplier_manager.normalize_supplier_name(None) == ''


class TestSupplierManagerCategories:
    """Test category tracking."""

    def test_categories_initialized_on_add(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        supplier = supplier_manager.get_supplier('Test Supplier Ltd')
        assert 'categories' in supplier
        assert 'Services' in supplier['categories']

    def test_new_category_added_on_duplicate(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)

        # Add same supplier with different category
        updated = sample_supplier_data.copy()
        updated['category'] = 'IT Services'
        supplier_manager.add_supplier(updated)

        supplier = supplier_manager.get_supplier('Test Supplier Ltd')
        assert 'IT Services' in supplier['categories']

    def test_get_suppliers_by_category(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        results = supplier_manager.get_suppliers_by_category('Services')
        assert len(results) == 1

    def test_get_suppliers_by_transaction_type(self, supplier_manager, sample_supplier_data):
        supplier_manager.add_supplier(sample_supplier_data)
        results = supplier_manager.get_suppliers_by_transaction_type('EXPENSES with VAT')
        assert len(results) == 1
