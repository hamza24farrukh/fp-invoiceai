"""
Currency Manager Module

This module provides functions to manage currency exchange rates and perform conversions
between different currencies, with PKR (Pakistani Rupee) as the base reporting currency.
Supports conversions from EUR, USD, and BGN to PKR.
"""

import os
import json
import logging
from typing import Dict, Optional, Tuple, Union, Any
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default exchange rates if no configuration file exists
# All rates convert TO PKR (base currency)
DEFAULT_RATES = {
    "EUR_TO_PKR": 280.50,  # 1 EUR = 280.50 PKR
    "USD_TO_PKR": 278.50,  # 1 USD = 278.50 PKR
    "BGN_TO_PKR": 143.40,  # 1 BGN = 143.40 PKR
}

# Path to store exchange rates
RATES_FILE = "exchange_rates.json"

def load_exchange_rates() -> Dict[str, float]:
    """
    Load exchange rates from the configuration file.
    If the file doesn't exist, create it with default values.

    Returns:
        Dictionary containing exchange rates
    """
    try:
        if os.path.exists(RATES_FILE):
            with open(RATES_FILE, "r") as f:
                rates = json.load(f)
            logger.info(f"Loaded exchange rates: {rates}")
            return rates
        else:
            # Create the file with default rates
            save_exchange_rates(DEFAULT_RATES)
            logger.info(f"Created default exchange rates: {DEFAULT_RATES}")
            return DEFAULT_RATES
    except Exception as e:
        logger.error(f"Error loading exchange rates: {str(e)}")
        return DEFAULT_RATES

def save_exchange_rates(rates: Dict[str, float]) -> bool:
    """
    Save exchange rates to the configuration file.

    Args:
        rates: Dictionary containing exchange rates

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(RATES_FILE, "w") as f:
            json.dump(rates, f, indent=4)
        logger.info(f"Saved exchange rates: {rates}")
        return True
    except Exception as e:
        logger.error(f"Error saving exchange rates: {str(e)}")
        return False

def update_exchange_rate(rate_key: str, value: float) -> bool:
    """
    Update a specific exchange rate.

    Args:
        rate_key: The key for the rate to update ('EUR_TO_PKR', 'USD_TO_PKR', or 'BGN_TO_PKR')
        value: The new exchange rate value

    Returns:
        True if successful, False otherwise
    """
    if rate_key not in ['EUR_TO_PKR', 'USD_TO_PKR', 'BGN_TO_PKR']:
        logger.error(f"Invalid rate key: {rate_key}")
        return False

    try:
        rates = load_exchange_rates()
        rates[rate_key] = value
        return save_exchange_rates(rates)
    except Exception as e:
        logger.error(f"Error updating exchange rate: {str(e)}")
        return False

def convert_to_pkr(amount: Union[float, str], from_currency: str) -> Tuple[float, Optional[str]]:
    """
    Convert an amount from a specified currency to PKR (base currency).

    Args:
        amount: The amount to convert (can be float or string with comma decimal separator)
        from_currency: Source currency code ('EUR', 'USD', 'BGN', or 'PKR')

    Returns:
        Tuple of (converted_amount, error_message)
        If from_currency is 'PKR', the same amount is returned
        If an error occurs, error_message contains the error description
    """
    # If the currency is already PKR, no conversion needed
    if from_currency == 'PKR':
        if isinstance(amount, str):
            try:
                amount = float(amount.replace(',', '.'))
            except ValueError:
                return 0.0, f"Invalid amount format: {amount}"
        return amount, None

    # Load current exchange rates
    rates = load_exchange_rates()

    # Convert string amount to float
    if isinstance(amount, str):
        try:
            amount = float(amount.replace(',', '.'))
        except ValueError:
            return 0.0, f"Invalid amount format: {amount}"

    # Perform the conversion
    if from_currency == 'EUR':
        return amount * rates.get('EUR_TO_PKR', DEFAULT_RATES['EUR_TO_PKR']), None
    elif from_currency == 'USD':
        return amount * rates.get('USD_TO_PKR', DEFAULT_RATES['USD_TO_PKR']), None
    elif from_currency == 'BGN':
        return amount * rates.get('BGN_TO_PKR', DEFAULT_RATES['BGN_TO_PKR']), None
    else:
        return 0.0, f"Unsupported currency: {from_currency}"

# Backward-compatible alias
convert_to_eur = convert_to_pkr

def format_amount(amount: float, currency: str) -> str:
    """
    Format an amount with the appropriate decimal separator for the given currency.

    Args:
        amount: The amount to format
        currency: The currency code ('PKR', 'EUR', 'USD', 'BGN', etc.)

    Returns:
        Formatted amount as a string
    """
    if currency in ['EUR', 'BGN']:
        # European format: comma as decimal separator
        return f"{amount:.2f}".replace('.', ',')
    else:
        # PKR, USD, GBP and others: period as decimal separator
        return f"{amount:.2f}"

def parse_amount(amount_str: str) -> float:
    """
    Parse an amount string to float, handling both period and comma as decimal separators.

    Args:
        amount_str: Amount as string

    Returns:
        Amount as float
    """
    try:
        # Replace comma with period to ensure proper float parsing
        return float(amount_str.replace(',', '.'))
    except ValueError:
        logger.error(f"Failed to parse amount: {amount_str}")
        return 0.0

def get_exchange_rates_for_display() -> Dict[str, str]:
    """
    Get exchange rates formatted for display in UI.
    All rates show conversion TO PKR (base currency).

    Returns:
        Dictionary with formatted exchange rates
    """
    rates = load_exchange_rates()
    return {
        'EUR_TO_PKR': f"{rates.get('EUR_TO_PKR', DEFAULT_RATES['EUR_TO_PKR']):.4f}",
        'USD_TO_PKR': f"{rates.get('USD_TO_PKR', DEFAULT_RATES['USD_TO_PKR']):.4f}",
        'BGN_TO_PKR': f"{rates.get('BGN_TO_PKR', DEFAULT_RATES['BGN_TO_PKR']):.4f}"
    }

def get_amount_with_conversions(amount: Union[float, str], currency: str) -> Dict[str, Any]:
    """
    Get the amount with conversions to PKR (base currency).

    Args:
        amount: Original amount (float or string)
        currency: Original currency code

    Returns:
        Dictionary with original and converted amounts:
        {
            'original': {'amount': str, 'currency': str},
            'converted': [{'amount': str, 'currency': str}]  # Only if conversion needed
        }
    """
    # Parse the amount if it's a string
    if isinstance(amount, str):
        parsed_amount = parse_amount(amount)
    else:
        parsed_amount = amount

    result = {
        'original': {
            'amount': format_amount(parsed_amount, currency),
            'currency': currency
        },
        'converted': []
    }

    # If not PKR, convert to PKR
    if currency != 'PKR':
        pkr_amount, error = convert_to_pkr(parsed_amount, currency)
        if not error:
            result['converted'].append({
                'amount': format_amount(pkr_amount, 'PKR'),
                'currency': 'PKR'
            })

    return result
