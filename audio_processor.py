"""
Audio Processor Module

This module provides speech-to-text transcription using OpenAI's Whisper model.
It enables voice note attachments to invoices and hands-free invoice data entry
through audio transcription.

Pre-trained Model: OpenAI Whisper (encoder-decoder transformer)
Data Domain: Audio (speech recognition)
"""

import os
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Supported audio file extensions
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm', '.wma'}


class AudioProcessor:
    """
    Process audio files using OpenAI Whisper for speech-to-text transcription.

    This class wraps the Whisper pre-trained model to provide audio transcription
    capabilities for the invoice processing system. Users can dictate invoice
    details or attach voice notes to existing invoices.

    The Whisper model is a transformer-based encoder-decoder trained on 680,000
    hours of multilingual speech data.
    """

    # Available model sizes with approximate VRAM/RAM requirements
    MODEL_SIZES = {
        'tiny': {'params': '39M', 'ram': '~1GB', 'speed': 'fastest'},
        'base': {'params': '74M', 'ram': '~1GB', 'speed': 'fast'},
        'small': {'params': '244M', 'ram': '~2GB', 'speed': 'moderate'},
        'medium': {'params': '769M', 'ram': '~5GB', 'speed': 'slow'},
        'large': {'params': '1550M', 'ram': '~10GB', 'speed': 'slowest'},
    }

    def __init__(self, model_size: str = "base"):
        """
        Initialize the audio processor.

        Args:
            model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large').
                       Defaults to 'base' for good accuracy/speed balance.
        """
        if model_size not in self.MODEL_SIZES:
            logger.warning(f"Unknown model size '{model_size}', falling back to 'base'")
            model_size = "base"

        self._model_size = model_size
        self._model = None
        logger.info(f"AudioProcessor initialized with model size: {model_size}")

    def _load_model(self) -> None:
        """
        Lazy-load the Whisper model on first use.
        This avoids slow startup when audio features aren't needed.
        """
        if self._model is not None:
            return

        try:
            import whisper
            logger.info(f"Loading Whisper '{self._model_size}' model...")
            start_time = time.time()
            self._model = whisper.load_model(self._model_size)
            load_time = time.time() - start_time
            logger.info(f"Whisper model loaded in {load_time:.1f}s")
        except ImportError:
            raise RuntimeError(
                "OpenAI Whisper is not installed. "
                "Install it with: pip install openai-whisper"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {str(e)}")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe an audio file to text using Whisper.

        Args:
            audio_path: Path to the audio file
            language: Optional language code (e.g., 'en', 'el', 'bg').
                     If None, Whisper auto-detects the language.

        Returns:
            Dictionary with:
                - 'text': Full transcription text
                - 'language': Detected language code
                - 'duration': Audio duration in seconds
                - 'segments': List of timestamped segments
                - 'processing_time': Time taken to transcribe in seconds
                - 'model_size': Whisper model size used

        Raises:
            FileNotFoundError: If the audio file doesn't exist
            RuntimeError: If Whisper is not installed or transcription fails
            ValueError: If the file format is not supported
        """
        # Validate file exists
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Validate format
        if not self.is_supported_format(audio_path):
            ext = Path(audio_path).suffix.lower()
            raise ValueError(
                f"Unsupported audio format: {ext}. "
                f"Supported formats: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
            )

        # Load model if needed
        self._load_model()

        logger.info(f"Transcribing audio: {os.path.basename(audio_path)}")
        start_time = time.time()

        try:
            # Build transcription options
            options = {}
            if language:
                options['language'] = language

            # Run transcription
            result = self._model.transcribe(audio_path, **options)

            processing_time = time.time() - start_time

            # Extract segments with timestamps
            segments = []
            for segment in result.get('segments', []):
                segments.append({
                    'start': segment.get('start', 0.0),
                    'end': segment.get('end', 0.0),
                    'text': segment.get('text', '').strip()
                })

            # Calculate duration from last segment end time
            duration = segments[-1]['end'] if segments else 0.0

            transcription = {
                'text': result.get('text', '').strip(),
                'language': result.get('language', 'unknown'),
                'duration': round(duration, 2),
                'segments': segments,
                'processing_time': round(processing_time, 2),
                'model_size': self._model_size
            }

            logger.info(
                f"Transcription complete: {len(transcription['text'])} chars, "
                f"language={transcription['language']}, "
                f"duration={transcription['duration']}s, "
                f"processed in {processing_time:.1f}s"
            )

            return transcription

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Transcription failed after {processing_time:.1f}s: {str(e)}")
            raise RuntimeError(f"Audio transcription failed: {str(e)}")

    def is_supported_format(self, file_path: str) -> bool:
        """
        Check if the file format is supported for audio processing.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file extension is a supported audio format
        """
        ext = Path(file_path).suffix.lower()
        return ext in ALLOWED_AUDIO_EXTENSIONS

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current Whisper model configuration.

        Returns:
            Dictionary with model details
        """
        info = self.MODEL_SIZES.get(self._model_size, {})
        return {
            'model_size': self._model_size,
            'parameters': info.get('params', 'unknown'),
            'ram_required': info.get('ram', 'unknown'),
            'relative_speed': info.get('speed', 'unknown'),
            'loaded': self._model is not None
        }

    @staticmethod
    def get_available_models() -> Dict[str, Dict[str, str]]:
        """
        Get information about all available Whisper model sizes.

        Returns:
            Dictionary mapping model size names to their specifications
        """
        return AudioProcessor.MODEL_SIZES.copy()
