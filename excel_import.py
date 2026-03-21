"""
Excel Import Module for Flask Application
This module handles importing supplier data from Excel files.
"""

import os
import logging
import pandas as pd
from typing import List, Dict, Any, Optional, Set
from supplier_manager import SupplierManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_suppliers_from_excel(excel_path: str) -> List[Dict[str, Any]]:
    """
    Extract unique supplier information from the Excel file.
    
    Based on the structure of the provided Excel files:
    - Column 1 (index 0): Date
    - Column 2 (index 1): Kind of Transaction (transaction type)
    - Column 3 (index 2): Transactor (supplier name)
    - Column 4 (index 3): Expense Category Account
    
    Returns:
        List of supplier dictionaries with name, category, and transaction type
    """
    try:
        # Store all the suppliers from all sheets
        all_suppliers = []
        unique_suppliers_set = set()
        
        # Try to read all sheets in the Excel file
        excel = pd.ExcelFile(excel_path)
        sheet_names = excel.sheet_names
        
        for sheet_name in sheet_names:
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                
                # Skip sheets with fewer than 4 columns
                if len(df.columns) < 4:
                    logger.info(f"Skipping sheet '{sheet_name}' as it has fewer than 4 columns")
                    continue
                
                logger.info(f"Processing sheet '{sheet_name}' from {excel_path}")
                
                # Find the correct column indices based on expected column names
                # For flexibility, we'll try to find columns by their names first
                transaction_col_idx = None
                supplier_col_idx = None
                category_col_idx = None
                
                # Common column name patterns
                transaction_patterns = ["kind of", "transaction", "type"]
                supplier_patterns = ["transactor", "supplier", "company", "vendor", "biller"]
                category_patterns = ["category", "expense", "account", "service"]
                
                # Find column indices by name
                for i, col_name in enumerate(df.columns):
                    col_name_lower = str(col_name).lower()
                    
                    # Check for transaction type column
                    if any(pattern in col_name_lower for pattern in transaction_patterns):
                        transaction_col_idx = i
                    
                    # Check for supplier/transactor column
                    if any(pattern in col_name_lower for pattern in supplier_patterns):
                        supplier_col_idx = i
                    
                    # Check for category column
                    if any(pattern in col_name_lower for pattern in category_patterns):
                        category_col_idx = i
                
                # If we couldn't find columns by name, use the specified indices 
                # (0-based index for the 1-based column numbers)
                # Column structure as per user:
                # - Column 1 (index 0): Date
                # - Column 2 (index 1): Type of Transactions
                # - Column 3 (index 2): Transactors (supplier names)
                # - Column 4 (index 3): Expense Category Account
                
                if transaction_col_idx is None:
                    transaction_col_idx = 1  # Column 2 (index 1): Type of Transactions
                
                if supplier_col_idx is None:
                    supplier_col_idx = 2  # Column 3 (index 2): Transactors
                
                if category_col_idx is None:
                    category_col_idx = 3  # Column 4 (index 3): Expense Category Account
                
                logger.info(f"Using column indices - Transaction: {transaction_col_idx}, " +
                           f"Supplier: {supplier_col_idx}, Category: {category_col_idx}")
                
                for _, row in df.iterrows():
                    # Skip rows with too few columns
                    if len(row) <= max(transaction_col_idx, supplier_col_idx, category_col_idx):
                        continue
                    
                    try:
                        # Get values by index, handling potential errors
                        supplier_name = str(row.iloc[supplier_col_idx]).strip() if not pd.isna(row.iloc[supplier_col_idx]) else ""
                        transaction_type = str(row.iloc[transaction_col_idx]).strip() if not pd.isna(row.iloc[transaction_col_idx]) else ""
                        category = str(row.iloc[category_col_idx]).strip() if not pd.isna(row.iloc[category_col_idx]) else ""
                        
                        # Skip header rows or empty rows
                        if not supplier_name or supplier_name.lower() in ["transactor", "supplier", "supplier name", "vendor", "nan"]:
                            continue
                            
                        # Skip rows where the supplier name is clearly not a supplier
                        if any(keyword in supplier_name.lower() for keyword in ["total", "date", "sum", "balance", "subtotal"]):
                            continue

                        # Normalize transaction type (remove newlines, etc.)
                        transaction_type = transaction_type.replace("\n", " ").strip()
                        if transaction_type.lower() == "nan":
                            transaction_type = None
                            
                        # Normalize category
                        category = category.replace("\n", " ").strip()
                        if category.lower() == "nan" or not category:
                            category = None
                            
                        # Debug: Log categories being found
                        if category:
                            logger.info(f"Found category: '{category}' for supplier: '{supplier_name}'")
                        else:
                            logger.warning(f"No category found for supplier: '{supplier_name}'")
                        
                        # Only add unique suppliers (case-insensitive)
                        supplier_key = supplier_name.lower()
                        if supplier_key in unique_suppliers_set:
                            continue
                        
                        unique_suppliers_set.add(supplier_key)
                        
                        all_suppliers.append({
                            'supplier_name': supplier_name,
                            'category': category,
                            'transaction_type': transaction_type,
                            'vat_number': None  # Not specified in the columns to extract
                        })
                    except IndexError as idx_err:
                        # Skip problematic rows but log them
                        logger.warning(f"Skipping row due to index error: {str(idx_err)}")
                        continue
            
            except Exception as sheet_err:
                logger.warning(f"Error processing sheet '{sheet_name}': {str(sheet_err)}")
                continue
        
        logger.info(f"Extracted {len(all_suppliers)} unique suppliers from {excel_path}")
        return all_suppliers
    
    except Exception as e:
        logger.error(f"Error processing {excel_path}: {str(e)}")
        return []


def import_suppliers_from_excel(excel_path: str, supplier_manager: SupplierManager) -> Dict[str, Any]:
    """
    Process Excel file and import suppliers into the application's database.
    
    Args:
        excel_path: Path to the Excel file
        supplier_manager: SupplierManager instance to use for storing data
        
    Returns:
        Dict with import statistics
    """
    results = {
        'total_suppliers': 0,
        'new_suppliers': 0,
        'updated_suppliers': 0,
        'error': None
    }
    
    try:
        # Extract suppliers from Excel
        suppliers = extract_suppliers_from_excel(excel_path)
        
        if not suppliers:
            results['error'] = "No suppliers found in the Excel file"
            return results
        
        # Import each supplier
        for supplier in suppliers:
            # Check if supplier already exists
            exists = supplier_manager.supplier_exists(supplier['supplier_name'])
            
            # Prepare data for add/update
            supplier_data = {
                'supplier_name': supplier['supplier_name'],
                'transaction_type': supplier['transaction_type'] or "Not specified"
            }
            
            # Add the category field and categories array
            if supplier['category']:
                supplier_data['category'] = supplier['category']  # Set both the category field
                supplier_data['categories'] = [supplier['category']]  # And the categories array
                logger.info(f"Adding category '{supplier['category']}' to supplier '{supplier['supplier_name']}'")
            else:
                logger.warning(f"No category for '{supplier['supplier_name']}'")
            
            # Add the supplier
            is_new = supplier_manager.add_supplier(supplier_data)
            
            if is_new:
                results['new_suppliers'] += 1
            else:
                results['updated_suppliers'] += 1
        
        results['total_suppliers'] = len(suppliers)
        return results
    
    except Exception as e:
        logger.error(f"Error importing suppliers: {str(e)}")
        results['error'] = str(e)
        return results