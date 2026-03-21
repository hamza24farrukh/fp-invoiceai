"""Tests for the DocumentClassifier class."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from document_classifier import DocumentClassifier, DOCUMENT_TYPES, RVLCDIP_TO_APP_TYPE


class TestDocumentClassifierInit:
    """Test classifier initialization."""

    def test_init_default_model(self):
        classifier = DocumentClassifier()
        assert classifier._model_name == "microsoft/dit-base-finetuned-rvlcdip"
        assert classifier._pipeline is None

    def test_init_custom_model(self):
        classifier = DocumentClassifier(model_name="custom/model")
        assert classifier._model_name == "custom/model"


class TestDocumentTypes:
    """Test document type mappings."""

    def test_all_app_types_valid(self):
        for app_type in RVLCDIP_TO_APP_TYPE.values():
            assert app_type in DOCUMENT_TYPES

    def test_invoice_mapping(self):
        assert RVLCDIP_TO_APP_TYPE['invoice'] == 'invoice'

    def test_unknown_label_maps_to_other(self):
        classifier = DocumentClassifier()
        assert classifier._map_to_app_type('unknown_label') == 'other'

    def test_supported_types(self):
        types = DocumentClassifier.get_supported_types()
        assert 'invoice' in types
        assert 'receipt' in types
        assert 'bank_statement' in types
        assert 'other' in types


class TestClassifierModelInfo:
    """Test model info reporting."""

    def test_get_model_info(self):
        classifier = DocumentClassifier()
        info = classifier.get_model_info()
        assert info['architecture'] == 'Vision Transformer (ViT / DiT)'
        assert info['dataset'] == 'RVL-CDIP (400,000 document images)'
        assert info['loaded'] is False


class TestClassifyErrors:
    """Test error handling in classification."""

    def test_classify_nonexistent_file(self):
        classifier = DocumentClassifier()
        with pytest.raises(FileNotFoundError):
            classifier.classify("/nonexistent/file.pdf")
