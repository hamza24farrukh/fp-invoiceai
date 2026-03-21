"""
Invoice Manager Module

This module manages invoice data with tracking for:
- Date
- Invoice number
- Transactor (supplier)
- Amount
- VAT
- Total in BGN
- Total in Euro
"""

import pandas as pd
import json
import os
import logging
import sqlite3
import datetime
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InvoiceManager:
    """
    Class to manage invoice data extracted from documents.
    """
    
    def __init__(self, db_file: str = "suppliers.db"):
        """
        Initialize the invoice manager.
        
        Args:
            db_file: Database file path
        """
        self.db_file = db_file
        self._ensure_database()
    
    def _ensure_database(self) -> None:
        """
        Ensure the database and invoices table exist.
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Create suppliers table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT UNIQUE,
                category TEXT,
                transaction_type TEXT,
                vat_number TEXT
            )
            ''')

            # Create invoices table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                invoice_number TEXT,
                transactor TEXT,
                amount REAL,
                vat REAL,
                total_bgn REAL,
                total_euro REAL,
                currency TEXT,
                supplier_id INTEGER,
                notes TEXT,
                is_income BOOLEAN DEFAULT 0,
                transaction_type TEXT,
                file_path TEXT,
                raw_extraction TEXT,
                FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
            )
            ''')
            
            # Check if we need to add the is_income column (for backward compatibility)
            cursor.execute("PRAGMA table_info(invoices)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Add is_income column if it doesn't exist
            if 'is_income' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN is_income BOOLEAN DEFAULT 0')
                logger.info("Added is_income column to invoices table")
                
            # Add transaction_type column if it doesn't exist
            if 'transaction_type' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN transaction_type TEXT')
                logger.info("Added transaction_type column to invoices table")
            
            # Add file_path column if it doesn't exist
            if 'file_path' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN file_path TEXT')
                logger.info("Added file_path column to invoices table")
                
            # Add description column if it doesn't exist
            if 'description' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN description TEXT')
                logger.info("Added description column to invoices table")

            if 'raw_extraction' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN raw_extraction TEXT')
                logger.info("Added raw_extraction column to invoices table")

            if 'document_type' not in columns:
                cursor.execute('ALTER TABLE invoices ADD COLUMN document_type TEXT')
                logger.info("Added document_type column to invoices table")

            conn.commit()
            logger.info("Invoice database initialized")
        except Exception as e:
            logger.error(f"Error initializing invoice database: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def add_invoice(self, invoice_data: Dict[str, Any]) -> int:
        """
        Add a new invoice to the database.
        
        Args:
            invoice_data: Dictionary containing invoice information
            
        Returns:
            ID of the added invoice, or -1 if failed
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Get the supplier ID if available
            supplier_id = None
            transactor = invoice_data.get("transactor")
            if transactor:
                cursor.execute("SELECT id FROM suppliers WHERE supplier_name = ?", (transactor,))
                result = cursor.fetchone()
                if result:
                    supplier_id = result[0]
            
            # Check if this is an income transaction
            is_income = invoice_data.get("is_income", False)
            transaction_type = invoice_data.get("transaction_type")
            
            raw_extraction = invoice_data.get("raw_extraction")
            if raw_extraction is not None and not isinstance(raw_extraction, str):
                try:
                    raw_extraction = json.dumps(raw_extraction, ensure_ascii=False)
                except TypeError:
                    raw_extraction = json.dumps(str(raw_extraction))

            # Insert the invoice data
            cursor.execute('''
            INSERT INTO invoices (
                date, invoice_number, transactor, amount, vat, 
                total_bgn, total_euro, currency, supplier_id, notes,
                is_income, transaction_type, file_path, description, raw_extraction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                invoice_data.get("date"),
                invoice_data.get("invoice_number"),
                invoice_data.get("transactor"),
                invoice_data.get("amount"),
                invoice_data.get("vat"),
                invoice_data.get("total_bgn"),
                invoice_data.get("total_euro"),
                invoice_data.get("currency"),
                supplier_id,
                invoice_data.get("notes"),
                is_income,
                transaction_type,
                invoice_data.get("file_path"),
                invoice_data.get("description", ""),
                raw_extraction
            ))
            
            invoice_id = cursor.lastrowid
            conn.commit()
            
            transaction_type_str = "income" if is_income else "expense"
            logger.info(f"Added {transaction_type_str} invoice {invoice_data.get('invoice_number')} for {transactor}")
            return invoice_id
        except Exception as e:
            logger.error(f"Error adding invoice: {str(e)}")
            if conn:
                conn.rollback()
            return -1
        finally:
            if conn:
                conn.close()
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """
        Get invoice by ID.
        
        Args:
            invoice_id: ID of the invoice
            
        Returns:
            Dictionary containing invoice information or None if not found
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices WHERE id = ?
            ''', (invoice_id,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting invoice {invoice_id}: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_invoices_by_transactor(self, transactor: str) -> List[Dict[str, Any]]:
        """
        Get all invoices for a specific transactor.
        
        Args:
            transactor: Name of the transactor
            
        Returns:
            List of invoice dictionaries
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices WHERE transactor = ?
            ORDER BY date DESC
            ''', (transactor,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting invoices for {transactor}: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
                
    def get_invoices_by_supplier(self, supplier: str) -> List[Dict[str, Any]]:
        """
        Get all invoices for a specific supplier.
        This is an alias for get_invoices_by_transactor since 'supplier' and 'transactor' 
        refer to the same entity in our database.
        
        Args:
            supplier: Name of the supplier/transactor
            
        Returns:
            List of invoice dictionaries
        """
        # This is just an alias for get_invoices_by_transactor
        return self.get_invoices_by_transactor(supplier)
    
    def get_all_invoices(self) -> List[Dict[str, Any]]:
        """
        Get all invoices.
        
        Returns:
            List of all invoice dictionaries
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices ORDER BY date DESC
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all invoices: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def update_invoice(self, invoice_id: int, updated_data: Dict[str, Any]) -> bool:
        """
        Update an existing invoice or create a new one if invoice_id is 0.
        
        Args:
            invoice_id: ID of the invoice to update, or 0 to create a new invoice
            updated_data: New invoice data
            
        Returns:
            True if update was successful, False otherwise
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Check if this is a new invoice (id=0)
            if invoice_id == 0:
                # Create a new invoice
                invoice_data = {
                    'date': updated_data.get('date'),
                    'invoice_number': updated_data.get('invoice_number'),
                    'transactor': updated_data.get('transactor'),
                    'amount': updated_data.get('amount', 0.0),
                    'vat': updated_data.get('vat', 0.0),
                    'total_bgn': updated_data.get('total_bgn', 0.0),
                    'total_euro': updated_data.get('total_euro', 0.0),
                    'currency': updated_data.get('currency', 'EUR'),
                    'notes': updated_data.get('notes', ''),
                    'is_income': updated_data.get('is_income', False),
                    'transaction_type': updated_data.get('transaction_type', 'EXPENSES with VAT'),
                    'file_path': updated_data.get('file_path'),
                    'description': updated_data.get('description', '')
                }
                
                # Create the new invoice
                result = self.add_invoice(invoice_data)
                if result > 0:
                    logger.info(f"Created new invoice {invoice_data['invoice_number']} for {invoice_data['transactor']}")
                    return True
                else:
                    logger.error("Failed to create new invoice")
                    return False
            
            # For existing invoices, check if it exists
            cursor.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,))
            if not cursor.fetchone():
                logger.warning(f"Invoice {invoice_id} not found")
                return False
            
            # Get the supplier ID if available and transactor has changed
            supplier_id = updated_data.get("supplier_id")
            if "transactor" in updated_data and not supplier_id:
                transactor = updated_data.get("transactor")
                cursor.execute("SELECT id FROM suppliers WHERE supplier_name = ?", (transactor,))
                result = cursor.fetchone()
                if result:
                    supplier_id = result[0]
                    updated_data["supplier_id"] = supplier_id
            
            # Build the SQL update statement dynamically based on what fields are present
            set_clauses = []
            params = []
            
            for key, value in updated_data.items():
                if key == "raw_extraction" and value is not None and not isinstance(value, str):
                    try:
                        value = json.dumps(value, ensure_ascii=False)
                    except TypeError:
                        value = json.dumps(str(value))
                if key in ["date", "invoice_number", "transactor", "amount", "vat", 
                          "total_bgn", "total_euro", "currency", "supplier_id", "notes",
                          "is_income", "transaction_type", "file_path", "description", "raw_extraction"]:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            
            if not set_clauses:
                logger.warning("No valid fields to update")
                return False
            
            params.append(invoice_id)  # For the WHERE clause
            
            query = f"UPDATE invoices SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, params)
            
            if cursor.rowcount == 0:
                logger.warning(f"Invoice {invoice_id} update had no effect")
                return False
            
            conn.commit()
            logger.info(f"Updated invoice {invoice_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating invoice {invoice_id}: {str(e)}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def delete_all_invoices(self) -> bool:
        """
        Delete all invoices from the database.
        
        Returns:
            True if deletion was successful, False otherwise
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Delete all records from the invoices table
            cursor.execute("DELETE FROM invoices")
            
            # Commit the changes
            conn.commit()
            
            # Log the operation
            logger.info(f"All invoices deleted from database")
            
            return True
        except Exception as e:
            logger.error(f"Error deleting all invoices: {e}")
            return False
        finally:
            if conn:
                conn.close()
                
    def delete_invoice(self, invoice_id: int) -> bool:
        """
        Delete an invoice.
        
        Args:
            invoice_id: ID of the invoice to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
            
            if cursor.rowcount == 0:
                logger.warning(f"Invoice {invoice_id} not found")
                return False
            
            conn.commit()
            logger.info(f"Deleted invoice {invoice_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting invoice {invoice_id}: {str(e)}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_invoices_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Get invoices within a date range.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of invoice dictionaries within the date range
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices 
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
            ''', (start_date, end_date))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting invoices for date range {start_date} to {end_date}: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
                
    def get_invoices_by_year(self, year: int) -> List[Dict[str, Any]]:
        """
        Get invoices for a specific year.
        
        Args:
            year: Year to filter by (e.g., 2023)
            
        Returns:
            List of invoice dictionaries for the specified year
        """
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        return self.get_invoices_by_date_range(start_date, end_date)
    
    def get_invoices_by_year_month(self, year: int, month: int) -> List[Dict[str, Any]]:
        """
        Get invoices for a specific year and month.
        
        Args:
            year: Year to filter by (e.g., 2023)
            month: Month to filter by (1-12)
            
        Returns:
            List of invoice dictionaries for the specified year and month
        """
        # Validate month
        if month < 1 or month > 12:
            logger.error(f"Invalid month: {month}")
            return []
            
        # Create start and end dates for the month
        month_str = f"{month:02d}"
        start_date = f"{year}-{month_str}-01"
        
        # Determine the last day of the month
        if month in [4, 6, 9, 11]:
            last_day = 30
        elif month == 2:
            # Handle February and leap years
            if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                last_day = 29
            else:
                last_day = 28
        else:
            last_day = 31
            
        end_date = f"{year}-{month_str}-{last_day}"
        
        return self.get_invoices_by_date_range(start_date, end_date)
    
    def get_income_invoices_by_year_month(self, year: int, month: int) -> List[Dict[str, Any]]:
        """
        Get income invoices for a specific year and month.
        
        Args:
            year: Year to filter by (e.g., 2023)
            month: Month to filter by (1-12)
            
        Returns:
            List of income invoice dictionaries for the specified year and month
        """
        all_invoices = self.get_invoices_by_year_month(year, month)
        return [invoice for invoice in all_invoices if invoice.get('is_income') == 1]
    
    def get_expense_invoices_by_year_month(self, year: int, month: int) -> List[Dict[str, Any]]:
        """
        Get expense invoices for a specific year and month.
        
        Args:
            year: Year to filter by (e.g., 2023)
            month: Month to filter by (1-12)
            
        Returns:
            List of expense invoice dictionaries for the specified year and month
        """
        all_invoices = self.get_invoices_by_year_month(year, month)
        return [invoice for invoice in all_invoices if invoice.get('is_income') == 0 or invoice.get('is_income') is None]
    
    def get_income_invoices(self) -> List[Dict[str, Any]]:
        """
        Get all income invoices.
        
        Returns:
            List of income invoice dictionaries
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices 
            WHERE is_income = 1
            ORDER BY date DESC
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting income invoices: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_expense_invoices(self) -> List[Dict[str, Any]]:
        """
        Get all expense invoices.
        
        Returns:
            List of expense invoice dictionaries
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM invoices 
            WHERE is_income = 0 OR is_income IS NULL
            ORDER BY date DESC
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting expense invoices: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
    
    def find_invoice_by_number(self, invoice_number: str) -> Optional[Dict[str, Any]]:
        """
        Find an invoice by its invoice number.
        
        Args:
            invoice_number: Invoice number to search for
            
        Returns:
            Dictionary containing invoice information or None if not found
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Use LIKE for case-insensitive matching
            cursor.execute('''
            SELECT * FROM invoices 
            WHERE invoice_number LIKE ? 
            LIMIT 1
            ''', (f"%{invoice_number}%",))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error finding invoice by number {invoice_number}: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()

    def export_invoices_to_json(
        self,
        supplier_manager: Optional[Any] = None,
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """Export all invoices to a JSON file mirroring supplier snapshot structure."""
        invoices = self.get_all_invoices()
        if output_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            output_path = os.path.join(base_dir, "invoices.json")

        if supplier_manager is None:
            try:
                from supplier_manager import SupplierManager  # Local import to avoid circular dependency
                supplier_manager = SupplierManager()
            except Exception as exc:
                logger.warning("Unable to instantiate SupplierManager for export: %s", exc)
                supplier_manager = None

        snapshot: List[Dict[str, Any]] = []
        for invoice in invoices:
            raw_payload = invoice.get('raw_extraction')
            if raw_payload and isinstance(raw_payload, str):
                try:
                    raw_payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    logger.warning("Failed to decode raw_extraction for invoice %s", invoice.get('invoice_number'))

            supplier_details: Dict[str, Any] = {}
            if supplier_manager and invoice.get('transactor'):
                supplier_details = supplier_manager.get_supplier(invoice['transactor']) or {}

            snapshot.append({
                "invoice_id": invoice.get('id'),
                "invoice_number": invoice.get('invoice_number'),
                "invoice_date": invoice.get('date'),
                "supplier_name": invoice.get('transactor'),
                "category": supplier_details.get('category'),
                "categories": supplier_details.get('categories'),
                "transaction_type": invoice.get('transaction_type') or supplier_details.get('transaction_type'),
                "vat_number": supplier_details.get('vat_number'),
                "amount": invoice.get('amount'),
                "vat_amount": invoice.get('vat'),
                "total_bgn": invoice.get('total_bgn'),
                "total_euro": invoice.get('total_euro'),
                "currency": invoice.get('currency'),
                "notes": invoice.get('notes'),
                "description": invoice.get('description'),
                "is_income": invoice.get('is_income'),
                "file_path": invoice.get('file_path'),
                "raw_extraction": raw_payload
            })

        temp_path = f"{output_path}.tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=False, indent=4)
            os.replace(temp_path, output_path)
            logger.info("Exported %d invoices to %s", len(snapshot), output_path)
            return output_path
        except Exception as exc:
            logger.error("Failed to export invoices to %s: %s", output_path, exc)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None
    
    def export_to_dataframe(self) -> pd.DataFrame:
        """
        Export invoices to a pandas DataFrame.
        
        Returns:
            DataFrame containing all invoice information
        """
        invoices = self.get_all_invoices()
        return pd.DataFrame(invoices)