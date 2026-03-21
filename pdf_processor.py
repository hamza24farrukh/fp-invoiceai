"""
PDF and Document Processor Module

This module handles text extraction from PDF and image documents using:
- pdfplumber (primary PDF extraction)
- PyPDF2 (fallback PDF extraction)
- Tesseract OCR (pre-trained CNN-based text detection for scanned/image documents)

Pre-trained Model: Tesseract OCR
Data Domain: Image (optical character recognition)
"""

import os
import PyPDF2
import pdfplumber
import logging
import base64
import traceback
from typing import Optional, Union, Dict, Any
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as a string
    """
    extracted_text = ""
    
    # First try with pdfplumber which handles complex PDFs better
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                extracted_text += page_text + "\n\n"
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed, trying PyPDF2: {str(e)}")
        
        # Fallback to PyPDF2
        try:
            with open(pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text() or ""
                    extracted_text += page_text + "\n\n"
        except Exception as e2:
            raise Exception(f"PDF extraction failed: {str(e2)}")
    
    if not extracted_text.strip():
        raise Exception("No text could be extracted from the PDF.")
    
    return extracted_text

def encode_file_to_base64(file_path: str) -> str:
    """
    Encode any file (image, PDF, etc.) to base64 string for AI vision models.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Base64 encoded string of the file
    """
    try:
        with open(file_path, "rb") as file:
            return base64.b64encode(file.read()).decode('utf-8')
    except Exception as e:
        raise Exception(f"Failed to encode file to base64: {str(e)}")
        
# Keep for backwards compatibility
def encode_image_to_base64(image_path: str) -> str:
    """
    Encode an image file to base64 string for AI vision models.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Base64 encoded string of the image
    """
    return encode_file_to_base64(image_path)

def extract_text_from_image(image_path: str) -> str:
    """
    Process an image and extract text content for AI processing.
    This doesn't do OCR but prepares the image for AI vision model.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Metadata about the image that will be used for AI processing
    """
    try:
        # For images, we'll return metadata to indicate this is an image
        # The actual processing will be handled by the AI model
        file_name = Path(image_path).name
        # No need to perform OCR here as we'll send the base64 image to AI
        # Just return metadata to indicate this is an image
        return f"IMAGE INVOICE: {file_name}\nPlease extract invoice information from this image."
    except Exception as e:
        raise Exception(f"Image processing failed: {str(e)}")

def extract_text_from_document(file_path: str) -> str:
    """
    Extract text from either a PDF file or image file.
    
    Args:
        file_path: Path to the file (PDF or image)
        
    Returns:
        Extracted text as a string or image metadata
    """
    file_extension = Path(file_path).suffix.lower()
    
    if file_extension in ['.pdf']:
        return extract_text_from_pdf(file_path)
    elif file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif']:
        return extract_text_from_image(file_path)
    else:
        raise Exception(f"Unsupported file type: {file_extension}")

def extract_text_from_multiple_documents(file_paths: list) -> dict:
    """
    Extract text from multiple files (PDFs or images).
    
    Args:
        file_paths: List of paths to files
        
    Returns:
        Dictionary mapping file paths to extracted text or image data
    """
    results = {}
    
    for file_path in file_paths:
        try:
            extracted_text = extract_text_from_document(file_path)
            results[file_path] = extracted_text
        except Exception as e:
            logger.error(f"Error processing {os.path.basename(file_path)}: {str(e)}")
            traceback.print_exc()  # Add detailed error trace
            results[file_path] = None
    
    return results

def extract_text_with_ocr(file_path: str, languages: str = "eng") -> str:
    """
    Extract text from an image or scanned PDF using Tesseract OCR.

    This function uses the Tesseract OCR engine, a pre-trained CNN-based
    text detection model, to extract text from document images. It operates
    on pixel data rather than using language understanding, making it
    fundamentally different from LLM-based extraction.

    Args:
        file_path: Path to the image or PDF file
        languages: Tesseract language codes (e.g., 'eng', 'eng+fra', 'eng+deu').
                  Defaults to 'eng' for English.

    Returns:
        Extracted text as a string. Returns empty string if OCR fails.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning(
            "pytesseract or Pillow not installed. "
            "Install with: pip install pytesseract Pillow"
        )
        return ""

    if not os.path.exists(file_path):
        logger.error(f"File not found for OCR: {file_path}")
        return ""

    file_extension = Path(file_path).suffix.lower()
    extracted_text = ""

    try:
        if file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif']:
            # Direct image OCR
            image = Image.open(file_path)
            extracted_text = pytesseract.image_to_string(image, lang=languages)
            logger.info(f"OCR extracted {len(extracted_text)} chars from image: {os.path.basename(file_path)}")

        elif file_extension == '.pdf':
            # Convert PDF pages to images, then OCR each
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                page_texts = []

                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    # Render page at 300 DPI for OCR quality
                    pix = page.get_pixmap(dpi=300)
                    img_data = pix.tobytes("png")

                    from io import BytesIO
                    image = Image.open(BytesIO(img_data))
                    page_text = pytesseract.image_to_string(image, lang=languages)
                    page_texts.append(page_text)

                doc.close()
                extracted_text = "\n\n".join(page_texts)
                logger.info(f"OCR extracted {len(extracted_text)} chars from {len(page_texts)} PDF pages")

            except ImportError:
                logger.warning("PyMuPDF not available for PDF-to-image conversion during OCR")
                return ""

        else:
            logger.warning(f"OCR not supported for file type: {file_extension}")
            return ""

    except Exception as e:
        # Check specifically for Tesseract not installed
        error_str = str(e)
        if "tesseract" in error_str.lower() and ("not installed" in error_str.lower() or "not found" in error_str.lower()):
            logger.warning(
                "Tesseract OCR is not installed on this system. "
                "Install from: https://github.com/UB-Mannheim/tesseract/wiki"
            )
        else:
            logger.warning(f"OCR extraction failed for {os.path.basename(file_path)}: {error_str}")
        return ""

    return extracted_text.strip()


def get_ocr_info() -> Dict[str, Any]:
    """
    Get information about the Tesseract OCR installation.

    Returns:
        Dictionary with OCR availability and version info
    """
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        languages = pytesseract.get_languages()
        return {
            'available': True,
            'version': str(version),
            'languages': languages,
            'engine': 'Tesseract OCR'
        }
    except Exception as e:
        return {
            'available': False,
            'error': str(e),
            'engine': 'Tesseract OCR'
        }


# Keep backward compatibility
def extract_text_from_multiple_pdfs(pdf_paths: list) -> dict:
    """
    Extract text from multiple PDF files (backward compatibility).
    
    Args:
        pdf_paths: List of paths to PDF files
        
    Returns:
        Dictionary mapping file paths to extracted text
    """
    return extract_text_from_multiple_documents(pdf_paths)
