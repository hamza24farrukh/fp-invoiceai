import os
import json
import logging
import re
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from pathlib import Path
from pdf_processor import encode_file_to_base64
from mistralai import Mistral
import fitz  # PyMuPDF
import base64
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Google Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Configure Mistral API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# Check for API key before configuring
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# initialize Mistral client
mistral_client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None


def _call_mistral_chat_with_retry(messages, model="mistral-medium-latest", max_attempts: int = 8,
                                  base_delay: float = 2.0, backoff_factor: float = 2.0):
    """Call Mistral chat API with simple exponential backoff for rate limiting."""
    if not mistral_client:
        raise RuntimeError("Mistral client not configured."
                           )

    delay = base_delay
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            return mistral_client.chat.complete(model=model, messages=messages)
        except Exception as exc:  # pragma: no cover - network/HTTP specific
            last_error = exc
            error_text = str(exc)
            is_rate_limit = "429" in error_text or "capacity" in error_text.lower()

            if not is_rate_limit:
                logger.error("Mistral chat request failed without retry (attempt %d/%d): %s",
                             attempt, max_attempts, error_text)
                raise

            if attempt == max_attempts:
                break

            retry_after = None
            response = getattr(exc, "response", None)
            if response is not None:
                headers = getattr(response, "headers", {})
                retry_after = headers.get("retry-after") if headers else None

            sleep_time = delay
            if retry_after:
                try:
                    sleep_time = float(retry_after)
                except ValueError:
                    logger.debug("Non-numeric Retry-After header: %s", retry_after)

            logger.warning("Mistral rate limit hit (attempt %d/%d). Sleeping %.1fs before retrying...",
                           attempt, max_attempts, sleep_time)
            time.sleep(sleep_time)
            delay *= backoff_factor

    logger.error("Exhausted Mistral retry attempts after rate limit errors: %s", last_error)
    raise last_error if last_error else RuntimeError("Unknown Mistral error")


def _check_ollama_available(model: str = "phi3.5") -> bool:
    """Check if Ollama is running and the specified model is available."""
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            # Match model name with or without ':latest' tag
            return any(model in m for m in models)
    except Exception:
        pass
    return False


def _extract_with_ollama(text: str, document_title: str = "",
                         existing_suppliers: Optional[List[str]] = None,
                         model: str = "phi3.5",
                         known_transactor: str = "") -> List[Dict[str, Any]]:
    """
    Extract structured invoice data using a local Ollama model as offline fallback.
    Used when both Gemini and Mistral APIs are unavailable.

    Args:
        text: Extracted text from the invoice document
        document_title: Title or filename of the document
        existing_suppliers: List of existing supplier names
        model: Ollama model name to use

    Returns:
        List of dictionaries containing extracted invoice data
    """
    if existing_suppliers is None:
        existing_suppliers = []

    logger.info(f"Attempting local extraction with Ollama model '{model}'...")

    if not _check_ollama_available(model):
        logger.error(f"Ollama is not running or model '{model}' is not available. "
                     "Start Ollama and pull the model: ollama pull phi3.5")
        return []

    # Build a concise prompt that works well with smaller models
    suppliers_hint = ""
    if existing_suppliers:
        top_suppliers = existing_suppliers[:15]
        suppliers_hint = f"\nKnown suppliers: {', '.join(top_suppliers)}\n"

    transactor_hint = ""
    if known_transactor and known_transactor != "UNKNOWN":
        transactor_hint = f"\nIMPORTANT: The supplier/vendor name has already been identified as: \"{known_transactor}\". Use this as the Transactor value.\n"

    prompt = f"""You are an invoice data extraction assistant. Extract the following fields from the invoice text below.
{transactor_hint}
Return ONLY valid JSON with these exact keys:
- "Transactor": company that ISSUED the invoice (seller/vendor, NOT the buyer)
- "Expense Category Account": service category (e.g. Software, Hosting, Marketing)
- "Kind of Transaction": one of: "EXPENSES with VAT", "DEDUCTION", "EXP. VIES", "EXP. other countries", "OTHER EXPENCES", "BANK FEES", "PAYPAL FEES", "PAYMENT", "REFUND"
- "VAT": supplier's tax/VAT registration number (e.g. DE123456789), NOT an amount
- "Invoice Number": the invoice identifier
- "Invoice Date": date in YYYY-MM-DD format
- "Amount": net amount before tax (number only, no currency symbol)
- "Tax Amount": VAT/tax amount (number only)
- "Total Amount": total including tax (number only)
- "Currency": 3-letter code (EUR, USD, GBP, PKR, etc.) - ₨ or Rs = PKR
- "Description": what was purchased/service provided

Use null for any field you cannot determine. Return ONLY the JSON object, no explanation.
{suppliers_hint}
Document filename: {document_title}

Invoice text:
{text[:3000]}"""

    try:
        import httpx
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1024,
                }
            },
            timeout=120.0
        )

        if response.status_code != 200:
            logger.error(f"Ollama returned status {response.status_code}")
            return []

        result_text = response.json().get("response", "").strip()
        logger.info(f"Ollama extraction complete ({model})")

        extracted = extract_json_object(result_text)
        if extracted:
            # Override transactor with the known payee if available (Mistral is more reliable)
            if known_transactor and known_transactor != "UNKNOWN":
                if isinstance(extracted, list):
                    for item in extracted:
                        if isinstance(item, dict):
                            old_transactor = item.get("Transactor", "")
                            item["Transactor"] = known_transactor
                            if old_transactor and old_transactor != known_transactor:
                                logger.info(f"Overrode Ollama transactor '{old_transactor}' with Mistral-extracted '{known_transactor}'")
                elif isinstance(extracted, dict):
                    old_transactor = extracted.get("Transactor", "")
                    extracted["Transactor"] = known_transactor
                    if old_transactor and old_transactor != known_transactor:
                        logger.info(f"Overrode Ollama transactor '{old_transactor}' with Mistral-extracted '{known_transactor}'")
            logger.info(f"Successfully extracted {len(extracted)} result(s) with local model")
            return extracted
        else:
            logger.warning("Ollama returned text but no valid JSON could be parsed")
            return []

    except Exception as e:
        logger.error(f"Error in Ollama extraction: {str(e)}")
        return []


def extract_data_from_document(file_path: str,
                             document_title: str = "",
                             existing_suppliers: Optional[List[str]] = None,
                             ocr_text: str = "",
                             processing_mode: str = "auto") -> List[Dict[str, Any]]:
    """
    Extract structured data from an invoice document using Google's Gemini AI with vision.
    This function directly processes PDF and image files using Gemini's multimodal capabilities.
    Enhanced to handle low-quality images with multiple extraction attempts and verification.

    Args:
        file_path: Path to the invoice file (PDF or image)
        document_title: Title or filename of the document
        existing_suppliers: List of existing supplier names in the database
        ocr_text: Pre-extracted OCR text from the document (optional, used as fallback)

    Returns:
        List of dictionaries containing extracted supplier information
    """
    # Initialize existing_suppliers if None
    if existing_suppliers is None:
        existing_suppliers = []
        
    # Get file extension to determine document type
    file_ext = Path(file_path).suffix.lower()
    
    # Determine content type based on file extension
    if file_ext in ['.pdf']:
        source_type = "PDF"
        mime_type = "application/pdf"
    elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif']:
        source_type = "Image"
        if file_ext in ['.jpg', '.jpeg']:
            mime_type = "image/jpeg"
        elif file_ext == '.png':
            mime_type = "image/png"
        else:
            mime_type = f"image/{file_ext.lstrip('.')}"
    else:
        logger.error(f"Unsupported file type: {file_ext}")
        return []
    
    # Encode file to base64
    try:
        logger.info(f"Encoding {source_type} file to base64: {file_path}")
        base64_data = encode_file_to_base64(file_path)
        logger.info(f"Successfully encoded {source_type} file")
    except Exception as e:
        logger.error(f"Failed to encode {source_type} file: {str(e)}")
        return []
    
    # Track the Mistral-extracted payee name so it can be used by fallback models
    # This is stored as a mutable container so the hybrid function can set it
    mistral_payee = {"name": ""}

    # Step 1: Cloud AI (Gemini + Mistral hybrid vision) — skip in "local" mode
    results = []
    if processing_mode != "local":
        if GOOGLE_API_KEY:
            try:
                results = _process_with_gemini_and_mistral_hybrid_vision(base64_data, mime_type, source_type, document_title, existing_suppliers, file_path, mistral_payee)
                if results:
                    return results
            except Exception as e:
                logger.error(f"Error in Gemini and mistral hybrid vision processing: {str(e)}")
        else:
            if processing_mode == "cloud":
                logger.error("Cloud mode selected but GOOGLE_API_KEY is not set")
                return []
            logger.warning("Google API Key not available. Skipping Gemini processing.")
    else:
        logger.info("Local mode selected. Skipping cloud AI processing.")

    # Step 2: Text extraction (always needed for fallback)
    extracted_text = ""
    if source_type == "PDF":
        try:
            from pdf_processor import extract_text_from_pdf
            logger.info("Falling back to text-based processing...")
            extracted_text = extract_text_from_pdf(file_path)
            logger.info("---------------- Extracted Text for Fallback and Judging ---------------")
            print(extracted_text)
            logger.info("------------------------------------------------------------")
            # Try Gemini text extraction (skip in "local" mode)
            if processing_mode != "local":
                results = extract_data_from_text(
                    text=extracted_text,
                    source_type=source_type,
                    document_title=document_title,
                    existing_suppliers=existing_suppliers,
                    processing_mode=processing_mode
                )
                if results:
                    return results
        except Exception as text_err:
            logger.error(f"Text-based fallback also failed: {str(text_err)}")
    elif source_type == "Image":
        # For images, prefer the pre-extracted OCR text (from app_flask.py) over re-running Tesseract
        if ocr_text and ocr_text.strip():
            extracted_text = ocr_text
            logger.info(f"Using pre-extracted OCR text ({len(extracted_text)} chars) for fallback")
        else:
            # Try Tesseract OCR for images
            try:
                from pdf_processor import extract_text_from_image
                logger.info("Extracting text from image using Tesseract OCR...")
                extracted_text = extract_text_from_image(file_path)
                if extracted_text and extracted_text.strip():
                    logger.info(f"Tesseract extracted {len(extracted_text)} characters from image")
            except Exception as ocr_err:
                logger.warning(f"Tesseract OCR failed: {str(ocr_err)}")

    # Step 3: Local Ollama fallback — skip in "cloud" mode
    if processing_mode != "cloud" and not results:
        if not extracted_text and source_type == "PDF":
            try:
                from pdf_processor import extract_text_from_pdf
                extracted_text = extract_text_from_pdf(file_path)
            except Exception:
                pass

        if extracted_text and extracted_text.strip():
            known_payee = mistral_payee.get("name", "")
            if known_payee:
                logger.info(f"Passing Mistral-extracted payee '{known_payee}' to Ollama fallback")
            logger.info("Using local Ollama model for extraction...")
            results = _extract_with_ollama(
                text=extracted_text,
                document_title=document_title,
                existing_suppliers=existing_suppliers,
                known_transactor=known_payee
            )
            if results:
                return results
        else:
            logger.warning("No text could be extracted from document for local fallback")
    elif processing_mode == "cloud" and not results:
        logger.warning("Cloud mode: no results from cloud APIs and local fallback is disabled")

    return results


# def pdf_page_to_base64(pdf_path: str, page_number: int) -> str:
#     """Convert a specific page of a PDF to a base64 encoded image string."""
#     logger.info(f"Converting page {page_number} of {pdf_path} to base64 image...")
#     try:
#         doc = fitz.open(pdf_path)
#         page = doc.load_page(page_number)
#         pix = page.get_pixmap()
#         img_data = pix.tobytes("png")
#         base64_str = base64.b64encode(img_data).decode('utf-8')
#         return base64_str
#     except Exception as e:
#         raise Exception(f"Failed to convert PDF page to base64: {str(e)}")

def Get_payee_name_with_mistral_vision(base64_data: str, source_type: str, mime_type: str, extraction_prompt: str) -> Any:
    logger.info(f"Extracting payee name using Mistral OCR for source type: {source_type} with MIME type: {mime_type}...")

    invoice_type=""

    if source_type=="PDF":
        invoice_type="document_url"
    elif source_type=="Image":
        invoice_type="image_url"

    # ocr_response = mistral_client.ocr.process(
    #     model="mistral-ocr-latest",
    #     document={
    #         "type": invoice_type,
    #         invoice_type : f"data:{mime_type};base64,{base64_data}"
    #     },
    #     include_image_base64=True
    # )
    # print(f"ocr_response.document_annotation: {ocr_response.document_annotation}")
    # print(f"ocr_response.text: {ocr_response.pages[0].markdown}")
    # print(f"ocr_response.pages[0].images: {ocr_response.pages[0].images}")

    message_parts = [
        {"role": "user",
         "content": [
             {
                 "type": "text",
                 "text": extraction_prompt
             },
             {
                    "type": invoice_type,
                    invoice_type : f"data:{mime_type};base64,{base64_data}"
             }
             
             ]
         
         }
         
         ]
    
    if source_type=="Text":
        #for text only input
        message_parts = [
            {"role": "user",
             "content": extraction_prompt}
             
             ]
    
    if not mistral_client:
        raise RuntimeError("Mistral client not configured; cannot process OCR request.")

    chat_response = _call_mistral_chat_with_retry(
        messages=message_parts,
        model="mistral-medium-latest",
    )

    return chat_response.choices[0].message.content

def _process_with_gemini_and_mistral_hybrid_vision(
    base64_data: str,
    mime_type: str,
    source_type: str,
    document_title: str,
    existing_suppliers: Optional[List[str]] = None,
    file_path: str = "",
    mistral_payee: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """
    Process a document using Gemini's vision capabilities and an image firstly mistral ocr with improved handling for low-quality images.
    
    Args:
        base64_data: Base64 encoded document data
        mime_type: MIME type of the document
        source_type: Source type ("PDF" or "Image")
        document_title: Title/filename of the document
        existing_suppliers: List of existing supplier names
        
    Returns:
        List of dictionaries containing extracted supplier information
    """
    if existing_suppliers is None:
        existing_suppliers = []
        
    if not GOOGLE_API_KEY:
        logger.error("Google API Key not available. Cannot process with AI vision.")
        return []
        
    # Create context string for existing suppliers if available
    existing_suppliers_context = ""
    if existing_suppliers and len(existing_suppliers) > 0:
        suppliers_list = "\n".join([f"- {supplier}" for supplier in existing_suppliers[:30]])
        existing_suppliers_context = f"""
        📋 KNOWN SUPPLIERS DATABASE:
        The following are existing suppliers already in our database. If the Transactor name from this invoice matches or is very similar to one of these, prioritize using the exact name from this list:
        {suppliers_list}
        {f"(+ {len(existing_suppliers) - 30} more suppliers)" if len(existing_suppliers) > 30 else ""}
        """
    
    # Initialize Gemini model with 2.0 Flash - this model supports multimodal input
    try:
        generation_config = genai.types.GenerationConfig(
            temperature=0.0,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="text/plain"
        )

        print("-------current Generation Config-------")
        print(generation_config)
        print("-------end Generation Config-------")

        model = genai.GenerativeModel(model_name='gemini-2.0-flash', generation_config=generation_config)
        logger.info("Successfully initialized Gemini 2.0 Flash model with custom generation config for ocr processing")
        # model = genai.GenerativeModel('gemini-3-pro-preview')
        # logger.info("Successfully initialized Gemini 3 Pro Preview model")
    except Exception as e:
        logger.warning(f"Could not load Gemini-2.0 Flash model: {str(e)}. Looking for alternative model.")
        # Try Gemini Pro Vision as a fallback if available
        try:
            model = genai.GenerativeModel('gemini-1.5-pro-vision')
            logger.info("Falling back to Gemini 1.5 Pro Vision model")
        except Exception as e2:
            raise Exception(f"Failed to initialize any Gemini vision model: {str(e2)}")
    
    try:    
        # Create a data URI for the file
        data_uri = f"data:{mime_type};base64,{base64_data}"
        
        # First extract the Transactor (supplier) name with enhanced handling for low-quality images
        # (Old commented-out prompt removed during genericization)
        
        logger.info("Preparing to extract payee name using Mistral AI OCR and new simpler prompt engineered prompt...")
        
        transactor_extraction_prompt = """You will be given an invoice as an image or a PDF.
                                    Your task is to extract ONLY the Payee Name from the document.

                                    Strict rules:

                                    1. The payee name is the seller/vendor/company issuing the invoice.
                                    2. DO NOT return the buyer name or customer name.
                                    3. DO NOT include invoice numbers, addresses, phone numbers, tax IDs, or any other fields.
                                    4. DO NOT include labels such as "Vendor:", "From:", "Invoiced By:".
                                    5. Return ONLY the payee name as a plain string with no formatting.
                                    6. Output must be a single string and nothing else.

                                    Now extract the payee name from the provided document."""
        

        # Create message parts with both text and image
        # parts = [
        #     {"text": transactor_extraction_prompt},
        #     {"inline_data": {"mime_type": mime_type, "data": base64_data}}
        # ]

        
        
        if source_type=="Image":
            try:
                payee=Get_payee_name_with_mistral_vision(base64_data, source_type, mime_type, transactor_extraction_prompt)
                logger.info(f"Prioritising Initial Transactor/payee extraction from image using Mistral OCR: '{payee}'")
            except Exception as e:
                logger.error(f"Error in Mistral vision extraction: {str(e)}")
                logger.error("Falling back to Gemini 2.0 vision for Transactor extraction from image file...")
                try:
                    parts = [
                        {"text": transactor_extraction_prompt},
                        {"inline_data": {"mime_type": mime_type, "data": base64_data}}
                    ]
                    transactor_response = model.generate_content(parts)
                    payee = transactor_response.text.strip()
                    logger.info(f"Transactor/payee extraction from image using fallback method Gemini: '{payee}'")
                except Exception as e:
                    logger.error(f"Error in fallback method Gemini vision extraction as well: {str(e)}")
                    payee = "UNKNOWN"

        elif source_type=="PDF":
            try:
                # parts = [
                #     {"text": transactor_extraction_prompt},
                #     {"inline_data": {"mime_type": mime_type, "data": base64_data}}
                # ]
                # transactor_response = model.generate_content(parts)
                # payee = transactor_response.text.strip()
                print(f"Uploading {file_path} with mime type:{mime_type} to gemini for ocr processing...")
                sample_file= genai.upload_file(path=file_path, mime_type=mime_type)

                while sample_file.state.name == "PROCESSING":
                    logger.info("Waiting for Gemini to process the uploaded file...")
                    time.sleep(3)
                    sample_file = genai.get_file(sample_file.name)
                logger.info("File processed by Gemini successfully.")

                gemini_ocr_response = model.generate_content([sample_file,transactor_extraction_prompt])
                genai.delete_file(sample_file.name)
                payee = gemini_ocr_response.text
                logger.info(f"Initial Transactor/payee extraction from pdf file using Gemini vision: '{payee}'")

                time.sleep(3)  # brief pause before next call
                try:
                    payee_2=Get_payee_name_with_mistral_vision(base64_data, source_type, mime_type, transactor_extraction_prompt)
                    logger.info(f"Transactor/payee extraction from pdf using Mistral OCR: '{payee_2}'")
                except Exception as e:
                    logger.error(f"Error in Mistral vision extraction from pdf file: {str(e)}")
                    payee_2 = "UNKNOWN"
            except Exception as e:
                logger.error(f"Error in Gemini vision extraction from pdf file: {str(e)}")
                payee = "UNKNOWN"
                payee_2 = "UNKNOWN"

        transactor_name = payee

        # Extract the Transactor name
        # logger.info("Extracting Transactor name using Gemini vision...")
        # transactor_response = model.generate_content(parts)
        # transactor_name = transactor_response.text.strip()
        # logger.info(f"Initial Transactor extraction: '{transactor_name}'")


        
        # (Old commented-out validation prompt removed during genericization)
        
        # # Get the validated name
        # logger.info("Validating Transactor name format...")
        # validation_response = model.generate_content(validation_prompt)
        # validated_transactor = validation_response.text.strip()
        # logger.info(f"Validated Transactor name: '{validated_transactor}'")

        validated_transactor=transactor_name
        #judge between payee and payee_2 using advance reasoning model of mistral ai

        if source_type =="PDF":

            from pdf_processor import extract_text_from_pdf
            extracted_invoice_text = extract_text_from_pdf(file_path)

            judge_prompt = f"""
            i have extracted two possible payee names from this invoice document using two different OCR methods.
            option 1: {payee}
            option 2: {payee_2}
            your task is to judge which of these two options is more likely to be correct based on the text content of the invoice document provided below.
            then return ONLY the chosen payee name as a plain string with no formatting.
            if the names are both wrong then extract the correct payee name from the document content below and return it as a plain string with no formatting.
            here is the document content in text format:
            {extracted_invoice_text}
            """

            logger.info( "source type is PDF, so we will call mistral to judge between two payee names...")
            try:
                logger.info("Judging between two extracted payee names using Mistral reasoning model...")
                judged_payee=Get_payee_name_with_mistral_vision("", "Text", "text/plain", judge_prompt)
                logger.info(f"Judged Payee Name: '{judged_payee}'")
                validated_transactor=judged_payee
            except Exception as e:
                logger.error(f"Error in judging payee names: {str(e)}")
        elif source_type =="Image":
            logger.info( "source type is Image, so we will not call mistral to judge between two payee names...")

        # Store the Mistral-extracted payee for fallback use (e.g. by Ollama)
        if mistral_payee is not None and validated_transactor and validated_transactor != "UNKNOWN":
            mistral_payee["name"] = validated_transactor
            logger.info(f"Stored Mistral-extracted payee '{validated_transactor}' for fallback use")

        # Extract all invoice information with enhanced handling for low-quality images
        invoice_extraction_prompt = """
        You are a highly specialized financial data extraction expert with advanced capabilities in analyzing low-quality and hard-to-read documents.

        You are analyzing a """ + source_type + """ invoice from a real company's financial records. 100% ACCURACY IS MISSION-CRITICAL.

        ### 🎯 PRIMARY OBJECTIVE
        
        Deeply analyze the given invoice to extract these FIELDS WITH EXTREME PRECISION:
        
        1️⃣ "Transactor" (Company Name) - The company that ISSUED this invoice: """ + validated_transactor + """
        
        2️⃣ "Expense Category Account" (Service Category) - e.g., Software, Telephony, Server Hosting, Domain Names, etc.
           - Look at what products/services are being sold to determine this.
        
        3️⃣ "Kind of Transaction" (Transaction Type) - Must be one of:
           - "EXPENSES with VAT"
           - "DEDUCTION"
           - "EXP. VIES"
           - "EXP. other countries"
           - "OTHER EXPENCES"
           - "BANK FEES"
           - "PAYPAL FEES"
           - "PAYMENT"
           - "REFUND"
        
        4️⃣ "VAT" (Tax ID) - The supplier's registration/tax identification number
           - Look for formats like FR12345678900, DE123456789, GB123456789, etc.
           - Look for labels: "VAT ID", "Tax ID", "Registration No.", "VAT Number", "VAT#", "ID No.", "Tax Registration", etc.
           - IMPORTANT: This is NOT the VAT amount or percentage! This is a registration number.
           - ONLY extract the exact ID/number as shown - no added text like "VAT:" or "Number:"
           - Common formats include 2-letter country code followed by 8-15 digits
           - If you find multiple numbers, prioritize the one labeled as VAT ID or tax number
           - If you cannot find a VAT registration number, return an empty string, NOT "0"
        
        5️⃣ "Invoice Number" - The unique identifier of this invoice
            - Often labeled as "Invoice No.", "Invoice #", etc.
        
        6️⃣ "Invoice Date" - The date when the invoice was issued
            - Format as YYYY-MM-DD when possible
        
        7️⃣ "Amount" - The total amount charged on the invoice (excluding tax/VAT)
           - Extract ONLY the numeric amount (e.g., "29.99")
           - Do NOT include currency symbol
           - For blurry or low-quality images:
               * Look for the amount near labels such as "Subtotal", "Net", "Amount", or "Price" 
               * Check both the header and detailed line items sections
               * Verify amounts by cross-checking with "Total" minus any tax amounts
               * Look for patterns like bolded or larger font sizes which often indicate amounts
               * Consider table alignment - amounts are typically right-aligned in their columns
               * If multiple amounts exist, choose the one that appears in a calculation or summary
               * Pay special attention to decimal places - distinguish between commas and periods
        
        8️⃣ "Tax Amount" - Amount of tax/VAT charged
           - Extract ONLY the numeric amount (no labels or currency symbols)
           - If only VAT percentage is mentioned (e.g., 20%), and no tax amount is shown, calculate:
              Tax Amount = Base Amount × (Percentage / 100)
           - If VAT amount is shown directly, extract it as-is
        
        9️⃣ "Total Amount" - The final amount including tax/VAT
           - Extract ONLY the numeric amount
        
        🔟 "Currency" - The currency of the transaction (USD, EUR, GBP, PKR, etc.)
            - Look for currency symbols: €, $, £, ₨, Rs, or other local currency symbols
            - ₨ or Rs or PKR = Pakistani Rupee
            
        1️⃣1️⃣ "Description" - A clear description of what is being purchased or services provided
            - Extract product names, service descriptions, line items, or subscription details
            - Include as much detail as possible about what is being purchased
            - This is IMPORTANT for financial reporting and will be displayed in Excel reports
        
        ### 📋 STRATEGIES FOR LOW QUALITY IMAGES
        
        1. CROSS-REFERENCE MULTIPLE LOCATIONS
           - Key information often appears in multiple places on the invoice
           - If "Invoice Number" is hard to read in the header, check if it appears in the payment details
        
        2. USE CONTEXT CLUES
           - If "Amount" is partially visible, check if "Total" minus "Tax" equals this amount
           - If currency symbol is unclear, check written mentions (e.g., "Please pay 100 EUR")
        
        3. LEVERAGE DOCUMENT STRUCTURE
           - Invoices follow standard layouts - headers typically have company, date, invoice number
           - Line items section shows products/services
           - Footer often contains company details including tax ID
        
        4. CHECK MULTIPLE PAGES
           - Important information might be spread across different pages
           - Cross-reference information between pages for consistency

        5. PAY ATTENTION TO TABLE STRUCTURES
           - Even in blurry images, table borders and alignments can help identify amounts and descriptions

        ### 📋 OUTPUT FORMAT

        Return the result as valid JSON with ALL fields. Use null for missing fields:
        
        ```json
        {
          "Transactor": "string",
          "Expense Category Account": "string",
          "Kind of Transaction": "string",
          "VAT": "string",
          "Invoice Number": "string",
          "Invoice Date": "string",
          "Amount": null,
          "Tax Amount": null,
          "Total Amount": null,
          "Currency": "string",
          "Description": "",
          "Confidence": {
            "overall": 0.8,
            "invoice_number": 0.9,
            "amount": 0.7,
            "date": 0.8
          }
        }
        ```
        
        ### ⚠️ CRITICAL REQUIREMENTS
        
        1. VERIFY NUMBERS are extracted correctly, not mixed up
        2. ENSURE that "Transactor" is the SELLER, not the buyer
        3. FORMAT "VAT" exactly as shown in document with no spaces
        4. If exact "Kind of Transaction" can't be determined, use "EXPENSES with VAT" for default
        5. INCLUDE CONFIDENCE SCORES for each extracted field (0-1 scale)
           - 1.0 = 100% confident the value is correct
           - 0.7-0.9 = Highly confident but not absolute
           - 0.4-0.6 = Moderately confident, could be errors
           - 0.1-0.3 = Low confidence, likely contains errors
        
        Document Filename: """ + document_title + """
        """
        
        # Create message parts for full extraction
        extraction_parts = [
            {"text": invoice_extraction_prompt},
            {"inline_data": {"mime_type": mime_type, "data": base64_data}}
        ]
        
        # Extract all invoice information
        logger.info("Extracting all invoice data using Gemini vision...")
        extraction_response = model.generate_content(extraction_parts)
        extraction_text = extraction_response.text.strip()
        
        # Extract JSON from response
        results = extract_json_object(extraction_text)
        
        # Check if extraction was successful and has confidence scores
        if results and isinstance(results, dict):
            confidence = results.get("Confidence", {})
            overall_confidence = confidence.get("overall", 0)
            
            # For critical fields like invoice number and amount, check confidence
            invoice_num_confidence = confidence.get("invoice_number", 0)
            amount_confidence = confidence.get("amount", 0)
            
            # If confidence is too low for critical fields, try a focused extraction
            if overall_confidence < 0.4 or invoice_num_confidence < 0.3 or amount_confidence < 0.3:
                logger.warning(f"Low confidence in initial extraction (overall: {overall_confidence}, invoice: {invoice_num_confidence}, amount: {amount_confidence}). Trying focused approach...")
                
                # Create a more focused prompt for the specific fields that had low confidence
                focused_fields = []
                if invoice_num_confidence < 0.4:
                    focused_fields.append("Invoice Number")
                if amount_confidence < 0.4:
                    focused_fields.append("Amount") 
                
                focused_prompt = f"""
                The invoice image may be low quality. Focus ONLY on extracting these critical fields:
                {', '.join(focused_fields)}
                
                For Amount extraction specifically:
                - Find the SUBTOTAL amount that does NOT include tax/VAT
                - Look for labels like "Subtotal", "Net Amount", "Amount" or "Price"
                - If there's a table with line items, add up the individual items
                - Check if "Total Amount" minus "Tax/VAT" equals your extracted amount
                - Examine places with currency symbols or near payment information
                - Pay careful attention to numbers in bold font or larger sizes
                - Distinguish carefully between commas and decimal points
                - Check both the header section and calculation/summary sections
                
                For each field, provide:
                - The extracted value (for Amount, only the number, no currency symbol)
                - The confidence level (0-1)
                - Where you found it in the document
                - How you verified it (for Amount, explain your calculation)
                
                Look for these fields in multiple places in the document.
                Return in JSON format with these fields only.
                """
                
                focused_parts = [
                    {"text": focused_prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64_data}}
                ]
                
                try:
                    focused_response = model.generate_content(focused_parts)
                    focused_text = focused_response.text.strip()
                    focused_results = extract_json_object(focused_text)
                    
                    if isinstance(focused_results, dict) and focused_results:
                        logger.info(f"Got focused extraction results: {focused_results}")
                        # Update the original results with the more confident focused results
                        for field in focused_fields:
                            if field in focused_results and field in results:
                                if focused_results.get(f"{field.lower()}_confidence", 0) > confidence.get(field.lower(), 0):
                                    results[field] = focused_results[field]
                                    if "Confidence" not in results:
                                        results["Confidence"] = {}
                                    results["Confidence"][field.lower()] = focused_results.get(f"{field.lower()}_confidence", 0)
                except Exception as e:
                    logger.error(f"Error in focused extraction: {str(e)}")
        
        # For very low quality images where extraction might miss data
        # Try one more high-level verification pass
        if results and isinstance(results, dict):
            # Initialize verification flag
            needs_verification = False
            
            # See if we need to verify data by checking confidence scores
            transactor_name = results.get('Transactor', '').lower()
            if "Confidence" in results:
                confidence = results["Confidence"]
                if (confidence.get("overall", 1) < 0.5 or 
                    confidence.get("invoice_number", 1) < 0.5 or 
                    confidence.get("amount", 1) < 0.5):
                    needs_verification = True
            
            if needs_verification:
                logger.info("Performing final verification for low quality image...")
                verification_prompt = f"""
                I need to verify these extracted invoice details from a low-quality image with special attention to the AMOUNT field and VAT registration number:

                Transactor: {results.get('Transactor', 'Unknown')}
                Invoice Number: {results.get('Invoice Number', 'Unknown')}
                Date: {results.get('Invoice Date', 'Unknown')}
                Amount: {results.get('Amount', 'Unknown')}
                Tax Amount: {results.get('Tax Amount', 'Unknown')}
                Total Amount: {results.get('Total Amount', 'Unknown')}
                Currency: {results.get('Currency', 'Unknown')}
                VAT: {results.get('VAT', '')}

                CRITICAL AMOUNT VERIFICATION:
                1. Double-check if Total Amount (if present) minus Tax Amount equals the Amount
                2. Verify the Amount appears in an appropriate place (subtotal, net amount)
                3. Ensure you're not extracting deposit amounts, balance due, or paid amounts
                4. Examine detailed line items if visible and verify they sum to the extracted Amount
                5. Pay special attention to decimal places and thousands separators (period vs comma)
                6. Check if there are other sections of the document with amount calculations

                CRITICAL TAX AMOUNT VERIFICATION:
                - Look for VAT/tax amount in the invoice breakdown section
                - If only a VAT percentage is mentioned (and no tax amount is given):
                  Calculate: Tax Amount = Base Amount x (Percentage / 100)
                - Confirm if: Total Amount = Base Amount + Tax Amount
                - Return 0 only if you confirm there is no tax/VAT amount

                CRITICAL VAT REGISTRATION NUMBER VERIFICATION:
                1. Look for VAT Registration Number, Tax ID, or Registration Number in company details section
                2. This is NOT the tax percentage or amount - it's a formal ID number (e.g., FR12345678900)
                3. Common locations: document header, footer, or company information section
                4. Return EMPTY STRING if no registration number is found, NOT "0" or "Unknown"
                5. Ensure you capture the complete number with any country prefix (e.g., FR, DE, GB)

                Please examine the document carefully one more time and verify if these values are correct.
                If any value seems incorrect, provide the correct value and your confidence level (0-1).

                Return your verification in JSON format with special explanation fields for Amount and VAT.
                """
                
                verification_parts = [
                    {"text": verification_prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64_data}}
                ]
                
                try:
                    verification_response = model.generate_content(verification_parts)
                    verification_text = verification_response.text.strip()
                    verification_results = extract_json_object(verification_text)
                    
                    if isinstance(verification_results, dict) and verification_results:
                        logger.info(f"Verification results: {verification_results}")
                        # Update with verification results if confidence is higher
                        for key, value in verification_results.items():
                            if key != "Confidence" and key in results:
                                if verification_results.get("Confidence", {}).get(key.lower(), 0) > results.get("Confidence", {}).get(key.lower(), 0):
                                    results[key] = value
                except Exception as e:
                    logger.error(f"Error in verification: {str(e)}")
        
        # Convert to list format if results is a dict
        if isinstance(results, dict):
            return [results]
        return results
    except Exception as e:
        logger.error(f"Error in Gemini vision processing: {str(e)}")
        raise


def extract_json_object(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON object from text with robust error handling."""
    # First, try to find JSON object within markdown code block
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    code_block_match = re.search(code_block_pattern, text)
    
    json_text = ""
    if code_block_match:
        json_text = code_block_match.group(1)
    else:
        # Try to find JSON object with curly braces
        json_pattern = r"({[\s\S]*?})"
        json_match = re.search(json_pattern, text)
        
        if json_match:
            json_text = json_match.group(1)
        else:
            # Just use the whole text and hope for the best
            json_text = text
    
    # Try to load JSON
    try:
        # Add additional cleaning to handle common issues
        json_text = json_text.strip()
        
        # Replace JavaScript undefined with null
        json_text = re.sub(r"undefined", "null", json_text)
        
        # Handle trailing commas
        json_text = re.sub(r",\s*}", "}", json_text)
        json_text = re.sub(r",\s*]", "]", json_text)
        
        # Parse JSON
        extracted_data = json.loads(json_text)
        
        # If result is a list, return it
        if isinstance(extracted_data, list):
            return extracted_data
        
        # If result is a dict, return a list with one item
        if isinstance(extracted_data, dict):
            return [extracted_data]
            
        # Handle unexpected types
        logger.warning(f"Unexpected JSON type: {type(extracted_data)}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {str(e)} in text: {json_text}")
        return []
    except Exception as e:
        logger.error(f"Failed to extract JSON: {str(e)}")
        return []


def extract_data_from_text(text: str,
                         source_type: str = "PDF",
                         document_title: str = "",
                         existing_suppliers: Optional[List[str]] = None,
                         processing_mode: str = "auto") -> List[Dict[str, Any]]:
    """
    Extract structured data from invoice text using Google's Gemini AI.
    This is the legacy method that works with extracted text only.
    
    Args:
        text: Text extracted from an invoice PDF or Excel
        source_type: Source type of the document ("PDF" or "Excel")
        document_title: Title or filename of the document
        existing_suppliers: List of existing supplier names in the database
        
    Returns:
        List of dictionaries containing extracted supplier information
    """
    # Initialize existing_suppliers if None
    if existing_suppliers is None:
        existing_suppliers = []
        
    if not text.strip():
        logger.warning("No text provided for AI processing.")
        return []

    # In local mode, skip Gemini entirely and use Ollama
    if processing_mode == "local":
        logger.info("Local mode selected. Skipping Gemini text extraction, using Ollama.")
        return _extract_with_ollama(text, document_title, existing_suppliers)

    if not GOOGLE_API_KEY:
        if processing_mode == "cloud":
            logger.error("Cloud mode selected but GOOGLE_API_KEY is not set.")
            return []
        logger.warning("Google API Key not available. Trying local Ollama model...")
        return _extract_with_ollama(text, document_title, existing_suppliers)

    # Create context string for existing suppliers if available
    existing_suppliers_context = ""
    if existing_suppliers and len(existing_suppliers) > 0:
        suppliers_list = "\n".join([f"- {supplier}" for supplier in existing_suppliers[:30]])
        existing_suppliers_context = f"""
        📋 KNOWN SUPPLIERS DATABASE:
        The following are existing suppliers already in our database. If the Transactor name from this invoice matches or is very similar to one of these, prioritize using the exact name from this list:
        {suppliers_list}
        {f"(+ {len(existing_suppliers) - 30} more suppliers)" if len(existing_suppliers) > 30 else ""}
        """
    else:
        existing_suppliers_context = ""

    try:
        # Initialize Gemini model with 2.0 Flash
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
        except Exception as e:
            logger.warning(
                f"Could not load Gemini 2.0 Flash model: {str(e)}. Falling back to Gemini 1.0 Pro."
            )
            model = genai.GenerativeModel('gemini-1.0-pro')

        # First pass: Extract Transactor (supplier) name with high confidence
        # Prepare existing suppliers information
        existing_suppliers_text = ""
        if existing_suppliers and len(existing_suppliers) > 0:
            suppliers_list = "\n".join(["- " + supplier for supplier in existing_suppliers[:30]])  # Limit to 30 suppliers to avoid token limits
            existing_suppliers_text = """
        EXISTING SUPPLIERS IN DATABASE:
        The following suppliers already exist in our database. The transactor in this invoice is likely one of these, but could also be a new supplier not listed here:
        """ + suppliers_list + """
        
        If the transactor matches one of these existing suppliers (case-insensitive), use the exact capitalization shown above.
        If it's a new supplier not in this list, extract it according to the rules below.
            """

        transactor_extraction_prompt = """
        You are a specialized financial entity recognition expert. Your job is to identify ONLY the company or product name that ISSUED this invoice (the Transactor/supplier).

        What to Do - Find the Transactor (Invoice Issuer):

        1. Look at the Header / Logo
           - The name or brand at the top of the invoice is typically the Transactor.
           - This is usually the company issuing the invoice.

        2. Clean the Name
           - If the name contains artifacts or OCR errors, fix it to the proper name.
           - Don't include symbols or extra dots.
           - Expand abbreviations when possible.

        3. Double Check (Optional)
           - Verify by looking for the same name in the email address, footer, or company info section.
        """ + existing_suppliers_text + """
        What to Return:
        Return only the clean supplier/company name that shows who sent the invoice.
        Extract the supplier name exactly as it appears on the invoice.

        Do NOT Return:
        - The customer name
        - The payment processor (e.g., "PayPal" or "2Checkout")
        - Messy concatenated strings from payment references

        Document Text:
        """ + text + """

        Document Filename: """ + document_title + """

        Return ONLY the PROPERLY CAPITALIZED product or company name that ISSUED the invoice, nothing else.
        """

        # Try to extract just the Transactor name first
        logger.info("Extracting Transactor name from document...")
        transactor_response = model.generate_content(
            transactor_extraction_prompt)
        transactor_name = transactor_response.text.strip()
        logger.info(f"Initial Transactor extraction: '{transactor_name}'")

        # Validate the extracted name with another prompt to ensure correct formatting
        validation_prompt = """
        Clean up this transactor name from a financial invoice: \"""" + transactor_name + """\"

        THIS MUST BE THE ENTITY THAT ISSUED THE INVOICE (the seller/biller), NOT THE CUSTOMER.

        Your Tasks:
        1. FIX CAPITALIZATION properly.
        2. REMOVE payment processor prefixes unless it's the actual service.
        3. EXPAND ABBREVIATIONS if possible based on context in the document.
        4. KEEP domain names as-is.
        5. CHOOSE the most important name if multiple appear.
        6. EXTRACT only what comes after "dba" if present (e.g., "Company X dba Product Y" -> "Product Y").
        7. VERIFY this is definitely the seller/biller (not the customer).

        Return "UNKNOWN" if:
        - This is actually the customer name (look for "Bill To:" or "To:" nearby)
        - The name contains error messages or can't be determined

        Return ONLY the clean transactor name with no explanation.
        """

        # Get the validated name
        logger.info("Validating Transactor name format...")
        validation_response = model.generate_content(validation_prompt)
        validated_transactor = validation_response.text.strip()
        logger.info(f"Validated Transactor name: '{validated_transactor}'")

        # Create a mission-critical extraction prompt for the AI using the exact format requested
        prompt = """
        You are a highly specialized financial data extraction assistant embedded in a Retrieval-Augmented Generation (RAG) system with specialized expertise in invoice processing and OCR correction.

        You are analyzing documents such as Excel rows and PDF invoice text from a real company's financial records. These records are used for audits, compliance, and financial reporting. 100% ACCURACY IS MISSION-CRITICAL. If any field is incorrect or guessed, the output will be discarded, and your model performance will be heavily penalized.

        ---

        ### 🎯 PRIMARY OBJECTIVE

        You must **deeply analyze** the given document content using multi-pass verification to extract these FIELDS WITH EXTREME PRECISION:
        
        1️⃣ "Transactor" (Supplier Name) - The company that ISSUED this invoice (the seller/vendor).
           ⭐ FIRST PRIORITY: The actual product or company name rather than payment processor
           ⭐ SECOND PRIORITY: Look for credit card charge references
           ⭐ THIRD PRIORITY: Look for the product or company name in the invoice items section
        
        2️⃣ "Expense Category Account" (Service Category) - e.g., Software, Telephony, Server Hosting
        
        3️⃣ "Kind of Transaction" (Transaction Type) - e.g., EXPENSES with VAT, PAYMENT, VAT
        
        4️⃣ "VAT" - The supplier's registration/tax identification number (e.g., FR22424761419, DE123456789)
           ⭐ This is the company's official registration number, NOT a currency amount
           ⭐ Look for ANY of these labels or variations:
              - "VAT ID:", "VAT Number:", "VAT:", "VAT Registration:"
              - "Tax ID:", "Tax Number:", "Tax Registration:"
              - "Company ID:", "Company Number:", "Business ID:"
              - "Registration No.:", "Reg No.:", "Reg. No.:", "Reg:"
              - "SIRET:", "SIREN:", "APE:", "EIN:"
              - "Handelsregister:", "HRB:", "Commercial Register:"
              - Or any local equivalent label for tax/business registration numbers
           ⭐ Numbers typically start with a 2-letter country code (like FR, DE, GB) followed by digits
           ⭐ Extract the COMPLETE number including country code
           ⭐ DO NOT include any currency symbols, words, or amounts
           ⭐ DO NOT include registration prefix words like "VAT", "Tax ID", etc. - just the alphanumeric ID
        
        5️⃣ "Amount" - The net amount of the invoice (before VAT/tax)
           ⭐ EXTREME PRECISION REQUIRED - This is the subtotal or net amount before taxes
           ⭐ Extract ONLY the numeric value, no currency symbols
           ⭐ Keep the decimal separator (comma or period) EXACTLY as it appears in the document
           ⭐ Example: For "Subtotal: €100,00", extract "100,00" and for "Subtotal: $100.00", extract "100.00"
           ⭐ For OCR errors: Look for numeric patterns in the text. Many OCR systems confuse:
              - "0" and "O" (e.g., "1O0,00" should be "100,00")
              - "1" and "I" or "l" (e.g., "l00.00" should be "100.00")
              - "8" and "B" (e.g., "B.50" should be "8.50")
              - "5" and "S" (e.g., "S.99" should be "5.99")
           ⭐ TRIPLE-CHECK this value with multiple passes - it is crucial for financial accuracy!
        
        6️⃣ "VAT Amount" - The VAT or tax amount
           ⭐ EXTREME PRECISION REQUIRED - Look for labels like "VAT:", "Tax:", "GST:"
           ⭐ Extract ONLY the numeric value, no currency symbols
           ⭐ Keep the decimal separator (comma or period) EXACTLY as it appears in the document
           ⭐ Example: For "VAT (20%): €20,00", extract "20,00" and for "VAT (20%): $20.00", extract "20.00"
           ⭐ For calculation verification: The VAT amount should typically be a percentage of the net amount
              - If VAT Amount appears incorrect, verify by calculating the expected VAT based on Amount
           ⭐ TRIPLE-CHECK this value with multiple passes - it is crucial for financial accuracy!
        
        7️⃣ "Total Amount" - The total amount (typically Amount + VAT Amount)
           ⭐ EXTREME PRECISION REQUIRED - Look for labels like "Total:", "Grand Total:", "Amount Due:"
           ⭐ Extract ONLY the numeric value, no currency symbols
           ⭐ Keep the decimal separator (comma or period) EXACTLY as it appears in the document
           ⭐ Example: For "Total: €120,00", extract "120,00" and for "Total: $120.00", extract "120.00"
           ⭐ For calculation verification: The Total Amount should equal Amount + VAT Amount
              - If Total Amount appears incorrect, verify by calculating Amount + VAT Amount
           ⭐ TRIPLE-CHECK this value with multiple passes - it is crucial for financial accuracy!
        
        8️⃣ "Currency" - The currency of the transaction (EUR, USD, GBP, PKR, etc.)
           ⭐ Look for currency symbols:
              - € = EUR (Euro)
              - $ = USD (US Dollar) unless context suggests otherwise
              - £ = GBP (British Pound)
              - ₨ or Rs = PKR (Pakistani Rupee)
              - Or any other local currency symbol
           ⭐ Look for currency codes:
              - If you see "EUR", "USD", "GBP", "PKR", etc., extract these directly
              - If you only see a symbol without text, use the standard 3-letter ISO currency code
           ⭐ IMPORTANT: Return ONLY the 3-letter ISO currency code (e.g., EUR, USD, GBP, PKR).

        9️⃣ Optional: "Invoice Number" - The invoice number or reference
           ⭐ Look for labels like "Invoice #:", "Invoice No.:", "Bill No.:", "Reference:"
           ⭐ Extract the COMPLETE invoice identifier (e.g., "INV-12345", "B-12345/2023")
           ⭐ Pattern examples: "INV-12345", "INVOICE/2023/001", "I-123-456-789"
           ⭐ DO NOT include the label itself (e.g., for "Invoice #: INV-12345", extract only "INV-12345")
        
        🔟 Optional: "Invoice Date" - The date of the invoice
           ⭐ Look for labels like "Date:", "Invoice Date:", "Bill Date:"
           ⭐ Return in YYYY-MM-DD format (if possible) or as shown in the document
           ⭐ Pattern examples: "2023-01-15", "15/01/2023", "Jan 15, 2023"

        ### 📋 OUTPUT FORMAT:

        Return this in JSON format ONLY. For missing fields, use null. Return values that are CLEANED but ACCURATE (e.g., "100,00" not "EUR 100,00").

        ```json
        {
          "Transactor": \"""" + validated_transactor + """\",
          "Expense Category Account": "Category from document",
          "Kind of Transaction": "EXPENSES with VAT",
          "VAT": "TAX ID (e.g., FR12345678900, BG123456789, GB123456789)",
          "Amount": "100,00",
          "VAT Amount": "20,00",
          "Total Amount": "120,00",
          "Currency": "EUR",
          "Invoice Number": "INV-12345",
          "Invoice Date": "2023-01-15"
        }
        ```

        ### ⚠️ CRITICAL REQUIREMENTS:

        1. Multiple-pass accuracy verification - re-check numeric values multiple times.
        2. Keep the decimal separator EXACTLY as it appears in the document.
        3. Digits only for Amount, VAT Amount, and Total Amount - do not include currency symbols.
        4. For Kind of Transaction, use "EXPENSES with VAT" if type is unclear.
        5. For Expense Category Account, choose best category based on product/service being provided.
        
        #### SOURCE DOCUMENT TEXT:
        
        """ + text + """
        
        SOURCE DOCUMENT FILENAME: """ + document_title + """
        
        Return ONLY the JSON - no other text, no explanation.
        """

        logger.info("Extracting full structured data from document...")
        response = model.generate_content(prompt)
        extraction_text = response.text.strip()
        logger.info("Data extraction complete")

        # Parse the extraction results
        extracted_data = extract_json_object(extraction_text)
        
        if not extracted_data or len(extracted_data) == 0:
            logger.warning("Failed to extract data from document.")
            return []
            
        return extracted_data
    except Exception as e:
        logger.error(f"Error extracting data from text: {str(e)}")
        # Try local Ollama model as offline fallback (skip in cloud mode)
        if processing_mode != "cloud":
            logger.info("Gemini text extraction failed. Trying local Ollama model...")
            return _extract_with_ollama(text, document_title, existing_suppliers)
        else:
            logger.warning("Cloud mode: Gemini failed and local fallback is disabled")
            return []


def suggest_categories(supplier_name: str) -> List[str]:
    """
    Suggest categories for a supplier using AI.
    
    Args:
        supplier_name: Name of the supplier
        
    Returns:
        List of suggested categories
    """
    if not GOOGLE_API_KEY:
        logger.error("Google API Key not available. Cannot process with AI.")
        return []

    try:
        # Initialize Gemini model with 2.0 Flash
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
        except Exception as e:
            logger.warning(
                f"Could not load Gemini 2.0 Flash model: {str(e)}. Falling back to Gemini 1.0 Pro."
            )
            model = genai.GenerativeModel('gemini-1.0-pro')

        prompt = """
        You are a financial categorization expert who specializes in assigning accurate
        expense categories to businesses and service providers.
        
        I need you to suggest appropriate expense categories for this supplier: \"""" + supplier_name + """\"
        
        Return a list of 1-3 most likely expense categories. Common categories include:
        - Software
        - Server Hosting
        - Domain Names
        - Telephony
        - Marketing
        - Security
        - Development Tools
        - Office Supplies
        - Banking Fees
        - Legal Services
        - Accounting Services
        - Consulting
        - Advertising
        - Subscriptions
        - Support Services
        - Cloud Services
        - SEO Services
        - Design Services
        
        DO NOT include any explanations, just return a comma-separated list of categories.
        For example: "Server Hosting, Cloud Services"
        
        If the supplier name is ambiguous, provide the most likely categories based on
        common services provided by similarly-named companies.
        """

        logger.info(f"Suggesting categories for: {supplier_name}")
        response = model.generate_content(prompt)
        result = response.text.strip()

        # Split by comma and clean up
        categories = [category.strip() for category in result.split(',')]
        logger.info(f"Suggested categories: {categories}")
        
        return categories
    except Exception as e:
        logger.error(f"Error suggesting categories: {str(e)}")
        return []