"""Tests for the pdf_processor module."""

import pytest
import os
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pdf_processor import encode_file_to_base64, extract_text_from_document, get_ocr_info


class TestEncodeFileToBase64:
    """Test base64 encoding."""

    def test_encode_text_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")
        result = encode_file_to_base64(str(test_file))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_nonexistent_file(self):
        with pytest.raises(Exception):
            encode_file_to_base64("/nonexistent/file.pdf")


class TestExtractTextFromDocument:
    """Test document type dispatching."""

    def test_unsupported_format(self, tmp_path):
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")
        with pytest.raises(Exception, match="Unsupported file type"):
            extract_text_from_document(str(test_file))

    def test_image_returns_metadata(self, tmp_path):
        # Create a minimal valid image file (1x1 PNG)
        import base64
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        test_file = tmp_path / "test.png"
        test_file.write_bytes(png_data)

        result = extract_text_from_document(str(test_file))
        assert "IMAGE INVOICE" in result
        assert "test.png" in result


class TestOCRInfo:
    """Test OCR availability check."""

    def test_get_ocr_info_returns_dict(self):
        info = get_ocr_info()
        assert isinstance(info, dict)
        assert 'available' in info
        assert 'engine' in info
        assert info['engine'] == 'Tesseract OCR'
