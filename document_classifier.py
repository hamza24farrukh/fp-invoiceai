"""
Document Classifier Module

This module provides document type classification using a pre-trained
Document Image Transformer (DiT) model. It automatically identifies
whether an uploaded document is an invoice, receipt, bank statement,
credit note, or other document type.

Pre-trained Model: microsoft/dit-base-finetuned-rvlcdip
    - Architecture: Vision Transformer (ViT) fine-tuned on RVL-CDIP dataset
    - Classes: 16 document types (mapped to 5 application types)
    - Data Domain: Image classification (different from LLM-based extraction)
"""

import os
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Mapping from RVL-CDIP 16 classes to our application document types
# RVL-CDIP classes: letter, form, email, handwritten, advertisement, scientific_report,
#                   scientific_publication, specification, file_folder, news_article,
#                   budget, invoice, presentation, questionnaire, resume, memo
RVLCDIP_TO_APP_TYPE = {
    'invoice': 'invoice',
    'budget': 'invoice',           # Budget documents treated as financial docs
    'form': 'receipt',             # Forms can be receipts
    'letter': 'other',
    'email': 'other',
    'handwritten': 'other',
    'advertisement': 'other',
    'scientific_report': 'other',
    'scientific_publication': 'other',
    'specification': 'other',
    'file_folder': 'other',
    'news_article': 'other',
    'presentation': 'other',
    'questionnaire': 'other',
    'resume': 'other',
    'memo': 'credit_note',        # Memos can be credit notes
}

# Application document types
DOCUMENT_TYPES = ['invoice', 'receipt', 'bank_statement', 'credit_note', 'other']


class DocumentClassifier:
    """
    Classify uploaded documents using a pre-trained Document Image Transformer.

    This classifier uses the microsoft/dit-base-finetuned-rvlcdip model which is
    a Vision Transformer (ViT) fine-tuned on the RVL-CDIP dataset containing
    400,000 grayscale document images across 16 categories.

    Unlike LLM-based analysis, this model operates purely on the visual layout
    and appearance of the document image, making it a fundamentally different
    approach to document understanding.
    """

    def __init__(self, model_name: str = "microsoft/dit-base-finetuned-rvlcdip"):
        """
        Initialize the document classifier.

        Args:
            model_name: HuggingFace model identifier. Defaults to the DiT model
                       fine-tuned on the RVL-CDIP document classification dataset.
        """
        self._model_name = model_name
        self._pipeline = None
        self._label2id = None
        logger.info(f"DocumentClassifier initialized with model: {model_name}")

    def _load_model(self) -> None:
        """
        Lazy-load the classification model on first use.
        Downloads model weights (~350MB) on first call.
        """
        if self._pipeline is not None:
            return

        try:
            from transformers import pipeline

            logger.info(f"Loading document classifier model: {self._model_name}...")
            start_time = time.time()

            self._pipeline = pipeline(
                "image-classification",
                model=self._model_name
            )

            load_time = time.time() - start_time
            logger.info(f"Document classifier loaded in {load_time:.1f}s")

        except ImportError:
            raise RuntimeError(
                "The transformers library is not installed. "
                "Install it with: pip install transformers torch"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load document classifier: {str(e)}")

    def classify(self, file_path: str) -> Dict[str, Any]:
        """
        Classify a document image into a document type.

        Args:
            file_path: Path to the document file (PDF or image)

        Returns:
            Dictionary with:
                - 'document_type': Application document type (invoice, receipt, etc.)
                - 'confidence': Confidence score (0.0 to 1.0)
                - 'raw_label': Original RVL-CDIP label
                - 'all_scores': List of all class scores
                - 'processing_time': Time taken in seconds

        Raises:
            FileNotFoundError: If the file doesn't exist
            RuntimeError: If the model fails to load or classify
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document file not found: {file_path}")

        # Load model if needed
        self._load_model()

        logger.info(f"Classifying document: {os.path.basename(file_path)}")
        start_time = time.time()

        try:
            # Convert document to image for classification
            image = self._prepare_image(file_path)

            # Run classification
            results = self._pipeline(image)

            processing_time = time.time() - start_time

            if not results:
                return {
                    'document_type': 'other',
                    'confidence': 0.0,
                    'raw_label': 'unknown',
                    'all_scores': [],
                    'processing_time': round(processing_time, 2)
                }

            # Get top prediction
            top_result = results[0]
            raw_label = top_result.get('label', 'unknown').lower()
            confidence = top_result.get('score', 0.0)

            # Map to application type
            document_type = self._map_to_app_type(raw_label)

            # Build all scores list
            all_scores = [
                {
                    'label': r.get('label', 'unknown'),
                    'app_type': self._map_to_app_type(r.get('label', 'unknown').lower()),
                    'score': round(r.get('score', 0.0), 4)
                }
                for r in results[:5]  # Top 5 predictions
            ]

            result = {
                'document_type': document_type,
                'confidence': round(confidence, 4),
                'raw_label': raw_label,
                'all_scores': all_scores,
                'processing_time': round(processing_time, 2)
            }

            logger.info(
                f"Classification: {document_type} (confidence={confidence:.2%}, "
                f"raw={raw_label}, time={processing_time:.1f}s)"
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Classification failed after {processing_time:.1f}s: {str(e)}")
            # Return graceful fallback instead of raising
            return {
                'document_type': 'other',
                'confidence': 0.0,
                'raw_label': 'error',
                'all_scores': [],
                'processing_time': round(processing_time, 2),
                'error': str(e)
            }

    def _prepare_image(self, file_path: str) -> Any:
        """
        Convert a document file to an image suitable for classification.

        For PDFs, extracts the first page as an image.
        For image files, opens directly.

        Args:
            file_path: Path to the document

        Returns:
            PIL Image object
        """
        from PIL import Image

        ext = Path(file_path).suffix.lower()

        if ext == '.pdf':
            # Convert first page of PDF to image using PyMuPDF
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                page = doc.load_page(0)  # First page
                # Render at 150 DPI for good quality
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                doc.close()

                from io import BytesIO
                return Image.open(BytesIO(img_data)).convert("RGB")

            except ImportError:
                logger.warning("PyMuPDF not available, trying alternative PDF conversion")
                # Fallback: try pdf2image if available
                try:
                    from pdf2image import convert_from_path
                    images = convert_from_path(file_path, first_page=1, last_page=1)
                    return images[0].convert("RGB")
                except ImportError:
                    raise RuntimeError(
                        "Cannot convert PDF to image. "
                        "Install PyMuPDF: pip install PyMuPDF"
                    )

        elif ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif']:
            return Image.open(file_path).convert("RGB")

        else:
            raise ValueError(f"Unsupported file format for classification: {ext}")

    def _map_to_app_type(self, raw_label: str) -> str:
        """
        Map a raw RVL-CDIP label to an application document type.

        Args:
            raw_label: The raw classification label from the model

        Returns:
            Application document type string
        """
        return RVLCDIP_TO_APP_TYPE.get(raw_label, 'other')

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current classifier model.

        Returns:
            Dictionary with model details
        """
        return {
            'model_name': self._model_name,
            'architecture': 'Vision Transformer (ViT / DiT)',
            'dataset': 'RVL-CDIP (400,000 document images)',
            'num_classes': 16,
            'app_document_types': DOCUMENT_TYPES,
            'loaded': self._pipeline is not None
        }

    @staticmethod
    def get_supported_types() -> List[str]:
        """
        Get the list of supported application document types.

        Returns:
            List of document type strings
        """
        return DOCUMENT_TYPES.copy()
