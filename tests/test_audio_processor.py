"""Tests for the AudioProcessor class."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from audio_processor import AudioProcessor, ALLOWED_AUDIO_EXTENSIONS


class TestAudioProcessorInit:
    """Test processor initialization."""

    def test_init_default_model(self):
        processor = AudioProcessor()
        assert processor._model_size == "base"
        assert processor._model is None

    def test_init_custom_model(self):
        processor = AudioProcessor(model_size="tiny")
        assert processor._model_size == "tiny"

    def test_init_invalid_model_falls_back(self):
        processor = AudioProcessor(model_size="nonexistent")
        assert processor._model_size == "base"


class TestSupportedFormats:
    """Test file format detection."""

    def test_supported_mp3(self):
        processor = AudioProcessor()
        assert processor.is_supported_format("test.mp3") is True

    def test_supported_wav(self):
        processor = AudioProcessor()
        assert processor.is_supported_format("test.wav") is True

    def test_supported_m4a(self):
        processor = AudioProcessor()
        assert processor.is_supported_format("test.m4a") is True

    def test_unsupported_pdf(self):
        processor = AudioProcessor()
        assert processor.is_supported_format("test.pdf") is False

    def test_unsupported_txt(self):
        processor = AudioProcessor()
        assert processor.is_supported_format("test.txt") is False

    def test_allowed_extensions_complete(self):
        expected = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm', '.wma'}
        assert ALLOWED_AUDIO_EXTENSIONS == expected


class TestAudioProcessorModelInfo:
    """Test model info reporting."""

    def test_get_model_info(self):
        processor = AudioProcessor()
        info = processor.get_model_info()
        assert info['model_size'] == 'base'
        assert info['loaded'] is False
        assert 'parameters' in info

    def test_get_available_models(self):
        models = AudioProcessor.get_available_models()
        assert 'tiny' in models
        assert 'base' in models
        assert 'small' in models
        assert 'medium' in models
        assert 'large' in models


class TestTranscribeErrors:
    """Test error handling in transcription."""

    def test_transcribe_nonexistent_file(self):
        processor = AudioProcessor()
        with pytest.raises(FileNotFoundError):
            processor.transcribe("/nonexistent/audio.mp3")

    def test_transcribe_unsupported_format(self, tmp_path):
        processor = AudioProcessor()
        test_file = tmp_path / "test.xyz"
        test_file.write_text("not audio")
        with pytest.raises(ValueError, match="Unsupported audio format"):
            processor.transcribe(str(test_file))
