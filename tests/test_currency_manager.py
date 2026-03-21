"""Tests for the currency_manager module."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from currency_manager import convert_to_eur, parse_amount, format_amount, get_amount_with_conversions


class TestConvertToEur:
    """Test currency conversion to EUR."""

    def test_eur_passthrough(self):
        amount, error = convert_to_eur(100.0, 'EUR')
        assert amount == 100.0
        assert error is None

    def test_usd_to_eur(self):
        amount, error = convert_to_eur(100.0, 'USD')
        assert error is None
        assert amount > 0
        assert amount < 100.0  # USD should be worth less in EUR

    def test_bgn_to_eur(self):
        amount, error = convert_to_eur(100.0, 'BGN')
        assert error is None
        assert amount > 0
        assert amount < 100.0  # BGN should be worth less in EUR

    def test_string_amount(self):
        amount, error = convert_to_eur('100.50', 'EUR')
        assert amount == 100.50
        assert error is None

    def test_comma_decimal_separator(self):
        amount, error = convert_to_eur('100,50', 'EUR')
        assert amount == 100.50
        assert error is None

    def test_unsupported_currency(self):
        amount, error = convert_to_eur(100.0, 'GBP')
        assert amount == 0.0
        assert error is not None

    def test_invalid_amount_string(self):
        amount, error = convert_to_eur('not_a_number', 'USD')
        assert amount == 0.0
        assert error is not None


class TestParseAmount:
    """Test amount parsing."""

    def test_parse_normal_float(self):
        assert parse_amount('100.50') == 100.50

    def test_parse_comma_decimal(self):
        assert parse_amount('100,50') == 100.50

    def test_parse_invalid(self):
        assert parse_amount('invalid') == 0.0

    def test_parse_integer(self):
        assert parse_amount('100') == 100.0


class TestFormatAmount:
    """Test amount formatting."""

    def test_format_eur(self):
        result = format_amount(100.50, 'EUR')
        assert result == '100,50'  # European format

    def test_format_bgn(self):
        result = format_amount(100.50, 'BGN')
        assert result == '100,50'  # European format

    def test_format_usd(self):
        result = format_amount(100.50, 'USD')
        assert result == '100.50'  # US format


class TestGetAmountWithConversions:
    """Test amount conversion helper."""

    def test_eur_no_conversion(self):
        result = get_amount_with_conversions(100.0, 'EUR')
        assert result['original']['currency'] == 'EUR'
        assert len(result['converted']) == 0

    def test_usd_converts_to_eur(self):
        result = get_amount_with_conversions(100.0, 'USD')
        assert result['original']['currency'] == 'USD'
        assert len(result['converted']) > 0
        assert result['converted'][0]['currency'] == 'EUR'
