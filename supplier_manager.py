import pandas as pd
import json
import os
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SupplierManager:
    """
    Class to manage supplier data extracted from invoices.
    """
    
    def __init__(self, storage_file: str = "suppliers.json"):
        """
        Initialize the supplier manager.
        
        Args:
            storage_file: File path for storing supplier data
        """
        self.storage_file = storage_file
        self._suppliers = self._load_suppliers()
    
    def _load_suppliers(self) -> List[Dict[str, Any]]:
        """
        Load suppliers from storage.
        
        Returns:
            List of supplier dictionaries
        """
        # Try to load from a file if it exists
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    suppliers = json.load(f)
                return suppliers
            except Exception as e:
                logger.error(f"Could not load suppliers from file: {str(e)}")
                return []
        else:
            return []
    
    def _save_suppliers(self) -> None:
        """Save suppliers to storage."""
        # Save to file as backup
        try:
            with open(self.storage_file, "w") as f:
                json.dump(self._suppliers, f)
        except Exception as e:
            logger.warning(f"Could not save suppliers to file: {str(e)}")
    
    def add_supplier(self, supplier_data: Dict[str, Any]) -> bool:
        """
        Add a new supplier or update an existing one.
        
        Args:
            supplier_data: Dictionary containing supplier information
            
        Returns:
            True if a new supplier was added, False if an existing supplier was updated
        """
        # Check if supplier already exists
        supplier_name = supplier_data.get("supplier_name")
        if not supplier_name:
            return False
            
        # Check if supplier exists
        existing_supplier = self.get_supplier(supplier_name)
        
        if existing_supplier:
            # Supplier exists, check if we need to update categories
            if 'categories' not in existing_supplier:
                existing_supplier['categories'] = []
                
            # If supplier_data has a category that's not in the existing supplier's categories, add it
            new_category = supplier_data.get('category')
            if new_category and new_category not in existing_supplier['categories']:
                existing_supplier['categories'].append(new_category)
            
            # Add the original category to categories if it's not there
            original_category = existing_supplier.get('category')
            if original_category and original_category not in existing_supplier['categories']:
                existing_supplier['categories'].append(original_category)
            
            # Update other fields if they're not set
            for key, value in supplier_data.items():
                if key != 'category' and key != 'categories':
                    if key not in existing_supplier or not existing_supplier[key]:
                        existing_supplier[key] = value
            
            # Save changes
            self._save_suppliers()
            return False
        else:
            # New supplier, initialize categories
            if 'category' in supplier_data:
                supplier_data['categories'] = [supplier_data['category']]
            else:
                supplier_data['categories'] = []
                
            self._suppliers.append(supplier_data)
            self._save_suppliers()
            return True
    
    def update_supplier(self, supplier_name: str, updated_data: Dict[str, Any]) -> bool:
        """
        Update an existing supplier.
        
        Args:
            supplier_name: Name of the supplier to update
            updated_data: New supplier data
            
        Returns:
            True if update was successful, False otherwise
        """
        if not supplier_name:
            return False
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        
        for i, supplier in enumerate(self._suppliers):
            existing_name = supplier.get("supplier_name", "")
            if self.normalize_supplier_name(existing_name) == normalized_name:
                self._suppliers[i] = updated_data
                self._save_suppliers()
                return True
        
        return False
    
    def delete_supplier(self, supplier_name: str) -> bool:
        """
        Delete a supplier.
        
        Args:
            supplier_name: Name of the supplier to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        if not supplier_name:
            return False
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        
        for i, supplier in enumerate(self._suppliers):
            existing_name = supplier.get("supplier_name", "")
            if self.normalize_supplier_name(existing_name) == normalized_name:
                self._suppliers.pop(i)
                self._save_suppliers()
                return True
        
        return False
    
    def get_supplier(self, supplier_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information for a specific supplier.
        
        Args:
            supplier_name: Name of the supplier
            
        Returns:
            Dictionary containing supplier information, or None if not found
        """
        if not supplier_name:
            return None
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        
        for supplier in self._suppliers:
            existing_name = supplier.get("supplier_name", "")
            if self.normalize_supplier_name(existing_name) == normalized_name:
                return supplier
        
        return None
    
    def get_all_suppliers(self) -> List[Dict[str, Any]]:
        """
        Get all suppliers.
        
        Returns:
            List of all supplier dictionaries
        """
        return self._suppliers
    
    def normalize_supplier_name(self, name: str) -> str:
        """
        Normalize a supplier name for consistent matching.
        
        Args:
            name: The raw supplier name
            
        Returns:
            Normalized supplier name for matching
        """
        if not name:
            return ""
        
        # Convert to uppercase and replace common separators with spaces
        normalized = name.upper().replace('_', ' ').replace('-', ' ')
        
        # Remove extra spaces and non-alphanumeric characters
        normalized = ' '.join(normalized.split())
        
        return normalized

    def supplier_exists(self, supplier_name: str) -> bool:
        """
        Check if a supplier exists.
        
        Args:
            supplier_name: Name of the supplier
            
        Returns:
            True if the supplier exists, False otherwise
        """
        if not supplier_name:
            return False
            
        normalized_name = self.normalize_supplier_name(supplier_name)
        
        for supplier in self._suppliers:
            existing_name = supplier.get("supplier_name", "")
            if self.normalize_supplier_name(existing_name) == normalized_name:
                return True
        
        return False
    
    def get_suppliers_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get suppliers by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of supplier dictionaries in the specified category
        """
        result = []
        for supplier in self._suppliers:
            # Check for the single 'category' field
            if supplier.get("category") == category:
                result.append(supplier)
                continue
                
            # Check for the 'categories' list
            if 'categories' in supplier and category in supplier['categories']:
                result.append(supplier)
                
        return result
        
    def get_invoices_by_amount(self, amount: float, threshold: float = 0.01) -> List[Dict[str, Any]]:
        """
        Get invoices that match a specific amount within a threshold.
        
        Args:
            amount: Amount to search for
            threshold: Maximum difference allowed between invoice amount and target amount
            
        Returns:
            List of invoice dictionaries with matching amounts
        """
        matching_invoices = []
        try:
            # Try to connect to the invoice database first
            import sqlite3
            from invoice_manager import InvoiceManager
            
            invoice_manager = InvoiceManager()
            conn = sqlite3.connect('suppliers.db')
            cursor = conn.cursor()
            
            # Get a list of invoices with amounts close to the target
            query = """
            SELECT 
                id, supplier_name, invoice_number, invoice_date, 
                amount, vat, total_bgn, total_euro, currency, notes
            FROM invoices
            WHERE ABS(amount - ?) < ? OR ABS(total_bgn - ?) < ? OR ABS(total_euro - ?) < ?
            """
            
            cursor.execute(query, (amount, threshold, amount, threshold, amount, threshold))
            rows = cursor.fetchall()
            
            # Convert rows to dictionaries
            columns = ['id', 'supplier_name', 'invoice_number', 'invoice_date', 
                      'amount', 'vat', 'total_bgn', 'total_euro', 'currency', 'notes']
            
            for row in rows:
                invoice_dict = {columns[i]: row[i] for i in range(len(columns))}
                matching_invoices.append(invoice_dict)
                
            conn.close()
            
            logger.info(f"Found {len(matching_invoices)} invoices matching amount {amount} within threshold {threshold}")
            
        except Exception as e:
            logger.warning(f"Error finding invoices by amount: {str(e)}")
            
            # Fall back to checking supplier data if invoices might have amount info
            for supplier in self._suppliers:
                # Check if supplier has an 'invoices' field with amount information
                if 'invoices' in supplier and isinstance(supplier['invoices'], list):
                    for invoice in supplier['invoices']:
                        invoice_amount = invoice.get('amount') or invoice.get('total_amount') or \
                                        invoice.get('total_bgn') or invoice.get('total_euro')
                        
                        if invoice_amount and abs(float(invoice_amount) - amount) < threshold:
                            # Add supplier info to the invoice
                            invoice_with_supplier = invoice.copy()
                            invoice_with_supplier['supplier_name'] = supplier.get('supplier_name') or \
                                                                    supplier.get('name')
                            matching_invoices.append(invoice_with_supplier)
        
        return matching_invoices
    
    def get_suppliers_by_transaction_type(self, transaction_type: str) -> List[Dict[str, Any]]:
        """
        Get suppliers by transaction type.
        
        Args:
            transaction_type: Transaction type to filter by
            
        Returns:
            List of supplier dictionaries with the specified transaction type
        """
        return [s for s in self._suppliers if s.get("transaction_type") == transaction_type]
    
    def delete_all_suppliers(self) -> bool:
        """
        Delete all suppliers from the database.
        
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self._suppliers = []
            self._save_suppliers()
            return True
        except Exception as e:
            logger.error(f"Error deleting all suppliers: {str(e)}")
            return False
    
    def export_to_dataframe(self) -> pd.DataFrame:
        """
        Export suppliers to a pandas DataFrame.
        
        Returns:
            DataFrame containing all supplier information
        """
        return pd.DataFrame(self._suppliers)
