# InvoiceAI - AI-Powered Invoice Management & Financial Processing System

## Motivation

Manual invoice processing is tedious, error-prone, and time-consuming. A typical small or medium business receives invoices in a variety of formats — digital PDFs, scanned paper documents, photographed receipts — each requiring a human to read, interpret, and manually key data into a spreadsheet or accounting system. This process does not scale, and mistakes in data entry (wrong amounts, misspelled supplier names, missed VAT) lead to financial discrepancies that are costly to reconcile.

InvoiceAI was built to solve this problem by orchestrating multiple pre-trained AI models into a unified pipeline that can:

- **Read** any invoice format (PDF, scanned image, photograph) using OCR and vision models
- **Extract** structured financial data (supplier, amounts, VAT, dates, currency) using large language models
- **Classify** documents automatically to route them to the correct processing path
- **Transcribe** voice memos into text notes attached to invoices
- **Match** bank statement transactions to invoice records for reconciliation

The system is designed to work **with or without internet access** — cloud AI models provide the highest accuracy, but a fully local fallback chain (Tesseract OCR + Ollama LLM) ensures the application remains functional offline.

## Purpose

InvoiceAI is a Flask-based web application that demonstrates the orchestration of **six pre-trained AI/ML models** across **four data domains** (text, vision, image classification, audio) to automate financial document processing. It serves as both a functional invoice management tool and a university project showcasing multi-model AI integration, evaluation, and software engineering best practices.

---

## AI/ML Models

### Cloud Models (Require API Keys)

| Model | Architecture | Data Domain | Role in System | Provider |
|-------|-------------|-------------|----------------|----------|
| **Gemini 3 Flash Preview** | Multimodal LLM | Vision + Text | Primary invoice field extraction — processes PDF pages and images directly using vision capabilities, extracts all structured fields (supplier, date, amounts, VAT, currency, invoice number) | Google AI |
| **Mistral Medium** | Large Language Model | Text + Vision | Payee name specialist — independently extracts the supplier/vendor name and acts as a "judge" to validate or override Gemini's payee extraction using a confidence-based voting system | Mistral AI |

### Local Models (Run Offline, No API Keys Needed)

| Model | Architecture | Data Domain | Role in System | Source |
|-------|-------------|-------------|----------------|--------|
| **Ollama Phi-3.5** | Small Language Model (SLM) | Text | Offline fallback extractor — processes OCR text when cloud models are unavailable, extracts the same structured fields as Gemini but from plain text input | Microsoft (via Ollama) |
| **Tesseract OCR** | CNN-based text detection | Image to Text | Optical character recognition — converts scanned documents and photographs into machine-readable text, feeds extracted text into LLM extractors | Google (open source) |
| **DiT (RVL-CDIP)** | Vision Transformer (ViT) | Image Classification | Document type classifier — categorises uploaded documents as invoice, receipt, bank statement, credit note, or other using a model trained on 400,000 document images across 16 categories | Microsoft |
| **OpenAI Whisper** | Encoder-Decoder Transformer | Audio to Text | Speech-to-text — transcribes voice memos and audio recordings into text, which can be attached as notes to invoice records | OpenAI (open source) |

### Model Summary by Data Domain

| Data Domain | Models Used | Input | Output |
|-------------|------------|-------|--------|
| **Vision + Text** | Gemini 3 Flash Preview, Mistral Medium | PDF pages, images | Structured JSON (supplier, amounts, dates, etc.) |
| **Image to Text** | Tesseract OCR | Scanned documents, photos | Raw text string |
| **Image Classification** | DiT (RVL-CDIP) | Document images | Document type + confidence score |
| **Audio to Text** | OpenAI Whisper | MP3, WAV, M4A, OGG, FLAC, WebM | Transcribed text + detected language |
| **Text (Local LLM)** | Ollama Phi-3.5 | Plain text (from OCR) | Structured JSON (same fields as cloud models) |

---

## Extraction Pipeline & Fallback Logic

When a user uploads an invoice, the system processes it through a multi-stage pipeline with automatic fallback at each stage. This ensures maximum accuracy when cloud models are available and continued functionality when they are not.

```
                         Upload Invoice (PDF / Image)
                                    |
                                    v
                    +-------------------------------+
                    |   Document Classification     |
                    |   (DiT Vision Transformer)    |
                    |   Classifies: invoice,        |
                    |   receipt, bank statement,     |
                    |   credit note, other           |
                    +-------------------------------+
                                    |
                                    v
                    +-------------------------------+
                    |   Text Extraction              |
                    |   PDF: pdfplumber -> PyPDF2    |
                    |   Image: Tesseract OCR         |
                    +-------------------------------+
                                    |
                                    v
              +-----------------------------------------+
              |        Processing Mode Selection         |
              |   (User selects: Auto / Cloud / Local)   |
              +-----------------------------------------+
                    |               |              |
                  Auto           Cloud           Local
                    |               |              |
                    v               v              v
        +------------------+  +-----------+  +-----------+
        | Step 1: Cloud AI |  | Cloud AI  |  | Skip      |
        | (Gemini Vision)  |  | Only      |  |           |
        +------------------+  +-----------+  +-----------+
            |       |              |              |
         Success  Fail          Success/Fail      |
            |       |              |              |
            v       v              v              v
        +------------------+                +-----------+
        | Step 2: Text +   |                | Ollama    |
        | Gemini (from OCR)|                | Phi-3.5   |
        +------------------+                | (Local)   |
            |       |                       +-----------+
         Success  Fail                          |
            |       |                        Success/Fail
            v       v                           |
        +------------------+                    v
        | Step 3: Ollama   |              +----------+
        | Local Fallback   |              | Results  |
        +------------------+              +----------+
            |
            v
        +----------+
        | Results  |
        +----------+
```

### Detailed Fallback Chain (Auto Mode)

| Step | Model(s) | What Happens | Fallback Trigger |
|------|----------|-------------|------------------|
| **1. Vision Extraction** | Gemini 3 Flash Preview + Mistral Medium | Gemini receives the full PDF page or image and extracts all fields. Simultaneously, Mistral independently extracts the payee/supplier name. A "judge" comparison validates the payee — if both models agree, that name is used; if they disagree, Mistral's extraction takes priority (specialised for payee detection). | Gemini API quota exceeded (429), API key missing, network error |
| **2. Text + Cloud AI** | Gemini 3 Flash Preview (text mode) | Falls back to sending the OCR-extracted plain text (from Tesseract or pdfplumber) to Gemini as a text prompt instead of a vision request. This uses less API quota and works when vision fails but text is available. | Same as Step 1 — Gemini text also fails |
| **3. Local Extraction** | Ollama Phi-3.5 | Sends OCR text to the locally-running Ollama server. If a payee name was already extracted by Mistral in Step 1 (preserved via the `mistral_payee` dict pattern), it is passed as a hint and forcibly applied to the results, ensuring payee accuracy even when the local model hallucinates. | Ollama server not running, model not installed |

### Processing Modes

Users can explicitly control which models run via the Processing Mode selector on the upload page:

| Mode | Cloud Models (Gemini + Mistral) | Local Models (Ollama + Tesseract) | Use Case |
|------|-------------------------------|----------------------------------|----------|
| **Auto** (default) | Yes — tried first | Yes — used as fallback | Best accuracy with offline resilience |
| **Cloud AI Only** | Yes — only option | Skipped entirely | Fast processing when API keys are available |
| **Local Only** | Skipped entirely | Yes — only option | Offline use, no API keys needed, privacy-sensitive documents |

### Model Status Panel

The upload page displays real-time availability of all five models via an AJAX call to `/api/model_status`. Each model shows a green (ready) or red (unavailable) indicator with Cloud/Local badges, so users can see at a glance which processing modes will work before uploading.

---

## Application Flow

```
User opens InvoiceAI (http://localhost:5000)
         |
         v
+-------------------+     +--------------------+     +---------------------+
|   Upload Page     |---->|   Results Page      |---->|   Invoice List      |
|   /upload         |     |   /results          |     |   /invoices         |
|                   |     |                     |     |   /income           |
|  - Drag & drop    |     |  - Extracted data   |     |                     |
|  - Browse files   |     |  - DiT class result |     |  - Search/filter    |
|  - Select mode    |     |  - Confidence score |     |  - View details     |
|  - Model status   |     |  - Edit before save |     |  - Edit/delete      |
+-------------------+     +--------------------+     +---------------------+
                                                              |
                  +-------------------------------------------+
                  |               |                |
                  v               v                v
         +-------------+  +-------------+  +------------------+
         | Invoice      |  | Edit Invoice|  | Supplier         |
         | Details      |  | /edit_inv.. |  | Management       |
         | /invoice_..  |  |             |  | /suppliers       |
         |              |  | - Voice note|  |                  |
         | - View PDF   |  |   upload    |  | - Categories     |
         | - Amounts    |  | - Currency  |  | - Transaction    |
         | - Currency   |  |   preview   |  |   types          |
         |   conversion |  |             |  | - VAT numbers    |
         +-------------+  +-------------+  +------------------+

         +------------------+     +---------------------+     +------------------+
         | Bank Statements  |     | Export & Reports     |     | Model Evaluation |
         | /process_bank_.. |     | /export              |     | /model_evaluation|
         |                  |     | /comprehensive_report|     |                  |
         | - Upload Excel   |     |                      |     | - Benchmark all  |
         | - Auto-detect    |     | - Monthly reports    |     |   models         |
         |   columns        |     | - Excel exports      |     | - Ground truth   |
         | - Match to       |     | - Invoice/supplier   |     |   comparison     |
         |   invoices       |     |   data exports       |     | - Accuracy stats |
         +------------------+     +---------------------+     +------------------+

         +------------------+
         | Currency Settings|
         | /currency_settings|
         |                  |
         | - EUR/USD/BGN    |
         |   to PKR rates   |
         | - Live updates   |
         +------------------+
```

---

## Key Features

### Invoice Processing
- Upload PDF or image invoices (JPG, PNG) via drag-and-drop or file browser
- AI extracts: supplier name, invoice number, date, net amount, VAT, total, currency
- Automatic supplier matching against existing database using fuzzy matching
- Supports both text-based PDFs and scanned/photographed documents

### Document Classification
- Every uploaded document is automatically classified by the DiT Vision Transformer
- Categories: invoice, receipt, bank statement, credit note, other
- Classification confidence score displayed on results page

### Voice Notes (Whisper)
- Upload audio recordings (MP3, WAV, M4A, OGG, FLAC, WebM) on the invoice edit page
- Whisper transcribes the audio and appends the text to the invoice's notes field
- Standalone voice memos can also create new invoice entries

### Bank Statement Reconciliation
- Upload any bank statement Excel file (not limited to a specific bank format)
- System auto-detects column mappings using fuzzy header matching
- Matches transactions to invoices by amount, date proximity, and supplier name
- Manual column mapping UI if auto-detection fails

### Multi-Currency Support
- Supports EUR, USD, BGN, and PKR with configurable exchange rates
- Live currency conversion preview on invoice edit forms
- Exchange rates stored in `exchange_rates.json` and editable via `/currency_settings`

### Financial Reporting
- Comprehensive monthly financial reports with income/expense breakdown
- Excel exports for invoices, suppliers, and combined financial data
- Filterable invoice lists with date range and transaction type filters

### Model Evaluation
- Built-in benchmarking framework at `/model_evaluation`
- Compares extraction accuracy across all models using ground truth data
- Measures processing time, field-level accuracy, and failure rates

---

## Project Structure

```
InvoiceAI/
├── app_flask.py                # Main Flask app (27 routes, all views and business logic)
├── ai_extractor.py             # Gemini + Mistral + Ollama extraction pipeline
├── audio_processor.py          # Whisper speech-to-text wrapper
├── bank_statement_converter.py # Generic bank statement format converter
├── currency_manager.py         # Multi-currency conversion functions
├── document_classifier.py      # DiT document image classifier
├── excel_exporter.py           # Excel/financial report generation
├── excel_import.py             # Excel data import utilities
├── invoice_manager.py          # SQLite invoice CRUD (InvoiceManager)
├── model_evaluation.py         # Model benchmarking engine (ModelEvaluator)
├── pdf_processor.py            # PDF text extraction + Tesseract OCR
├── supplier_manager.py         # JSON-based supplier CRUD (SupplierManager)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── exchange_rates.json         # Configurable currency exchange rates
├── benchmarks/
│   ├── ground_truth.json       # Annotated test data for model evaluation
│   └── sample_invoices/        # Sample documents for benchmarking
├── static/
│   ├── css/styles.css          # Custom application styles
│   ├── js/main.js              # Client-side JS (drag-drop, AJAX)
│   └── img/                    # Static images
├── templates/                  # 17 Jinja2 templates (all extend base.html)
│   ├── base.html               # Base layout with navigation
│   ├── index.html              # Dashboard / home page
│   ├── upload.html             # Invoice upload with mode selector
│   ├── results.html            # Extraction results display
│   ├── invoices.html           # Invoice list (expenses)
│   ├── income.html             # Income transaction list
│   ├── invoice_details.html    # Single invoice detail view
│   ├── edit_invoice.html       # Invoice edit form + voice notes
│   ├── suppliers.html          # Supplier management
│   ├── edit_supplier.html      # Supplier edit form
│   ├── export.html             # Export options
│   ├── import_excel.html       # Excel import interface
│   ├── process_bank_statements.html  # Bank statement upload
│   ├── bank_statement_results.html   # Statement matching results
│   ├── currency_settings.html  # Exchange rate configuration
│   ├── comprehensive_report.html     # Financial reports
│   └── model_evaluation.html  # Model benchmarking dashboard
├── tests/                      # Pytest test suite
│   ├── conftest.py             # Shared fixtures
│   ├── test_invoice_manager.py
│   ├── test_supplier_manager.py
│   ├── test_currency_manager.py
│   ├── test_pdf_processor.py
│   ├── test_document_classifier.py
│   ├── test_audio_processor.py
│   └── test_bank_statement_converter.py
└── uploads/                    # Uploaded files (PDFs, images)
    └── voice_notes/            # Audio uploads for Whisper
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web Framework** | Flask 3.1.0 | HTTP routing, templating, file uploads |
| **Frontend** | Bootstrap 5.3 + Bootstrap Icons | Responsive UI, components |
| **Templating** | Jinja2 | Server-side HTML rendering |
| **Database** | SQLite | Invoice storage (via `InvoiceManager`) |
| **Data Files** | JSON | Suppliers, exchange rates, ground truth |
| **PDF Processing** | pdfplumber + PyPDF2 + PyMuPDF | Text extraction from PDFs |
| **Data Analysis** | pandas + openpyxl | Excel I/O, financial reports |
| **Testing** | pytest + pytest-cov | Unit and integration tests |

---

## Installation

### Prerequisites

- Python 3.11+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (for image text extraction)
- [FFmpeg](https://ffmpeg.org/download.html) (for Whisper audio decoding)
- [Ollama](https://ollama.com/) (optional, for local LLM fallback — install and run `ollama pull phi3.5`)

### Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys (optional for local-only mode)
   ```

   | Variable | Required? | Description |
   |----------|-----------|-------------|
   | `GOOGLE_API_KEY` | Optional | Google Gemini API key — enables cloud vision extraction |
   | `MISTRAL_API_KEY` | Optional | Mistral AI API key — enables payee verification |

   **Note:** Both API keys are optional. Without them, the system automatically falls back to local models (Tesseract + Ollama). You can also select "Local Only" processing mode on the upload page.

3. Run the application:
   ```bash
   python app_flask.py
   ```
   The app will start on `http://localhost:5000`.

### Running Without API Keys (Fully Offline)

The application works entirely offline with local models:

1. Install and start Ollama: `ollama serve`
2. Pull the Phi-3.5 model: `ollama pull phi3.5`
3. Ensure Tesseract OCR is installed and on your system PATH
4. Run the app and select **Local Only** processing mode on the upload page

---

## Testing

The project includes a comprehensive **pytest** test suite with **105 test functions** across 8 test modules, covering all core managers, processors, and AI model wrappers.

### Running Tests

```bash
# Run full test suite with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=. --cov-report=term-missing

# Run a specific test module
pytest tests/test_invoice_manager.py -v

# Run a single test
pytest tests/test_currency_manager.py::test_usd_to_eur -v
```

### Test Modules

| Test Module | Tests | What It Covers |
|-------------|-------|---------------|
| `test_invoice_manager.py` | 16 | CRUD operations (add, get, update, delete), date range filtering, year/month filtering, income/expense separation, transactor search, edge cases (nonexistent records, delete-all) |
| `test_supplier_manager.py` | 15 | Add/update/delete suppliers, duplicate handling, name normalisation, case-insensitive lookup, category tracking, filtering by category and transaction type |
| `test_currency_manager.py` | 16 | EUR/USD/BGN conversions, comma decimal parsing, string amount parsing, currency formatting (comma vs dot separators), passthrough for base currency, unsupported currency handling |
| `test_pdf_processor.py` | 5 | Base64 file encoding, unsupported format detection, image metadata extraction, OCR info reporting |
| `test_document_classifier.py` | 8 | DiT model initialisation, RVL-CDIP label to app type mapping, supported document types, model info reporting, nonexistent file handling |
| `test_audio_processor.py` | 13 | Whisper model initialisation (default/custom/fallback), supported format validation (MP3, WAV, M4A, OGG, FLAC, WebM), unsupported format rejection, model info, available models listing, error handling for missing files |
| `test_bank_statement_converter.py` | 9 | Column auto-detection (standard and alternative header names), Excel format detection, conversion to standard format, transaction-to-invoice matching by amount, empty invoice edge case |

### Test Fixtures (conftest.py)

Shared fixtures provide isolated test environments:

| Fixture | Purpose |
|---------|---------|
| `temp_db` | Fresh SQLite database file in a temporary directory per test |
| `invoice_manager` | `InvoiceManager` instance connected to the temp database |
| `supplier_manager` | `SupplierManager` instance with a temporary JSON file |
| `sample_invoice_data` | Standard invoice dict with all required fields |
| `sample_supplier_data` | Standard supplier dict with name, category, transaction type, VAT number |
| `sample_exchange_rates` | Temporary exchange rates JSON file with default EUR/USD/BGN rates |

### Testing Approach

- **Unit tests** use isolated temporary files and databases — no shared state between tests
- **AI model tests** validate initialisation, input validation, and error handling without requiring actual model inference (no API keys or GPU needed to run tests)
- **Manager tests** verify full CRUD lifecycles: create a record, read it back, update it, delete it, confirm deletion
- **Edge cases** are explicitly tested: nonexistent files, duplicate entries, invalid inputs, empty datasets, unsupported formats

---

## Model Evaluation Framework

InvoiceAI includes a built-in benchmarking system (`model_evaluation.py`) for systematically evaluating and comparing all pre-trained models against annotated ground truth data.

### How It Works

1. **Ground truth data** is stored in `benchmarks/ground_truth.json` — each entry contains a test file name, the expected extracted fields, and the expected document type
2. The `ModelEvaluator` class runs each model against the test files, compares outputs to ground truth, and calculates metrics
3. Results are displayed on the `/model_evaluation` web page and can be exported to `benchmarks/results.json`

### Evaluation Types

The framework supports three distinct evaluation methods, one for each model category:

| Evaluation Method | Models Evaluated | Metrics Produced |
|-------------------|-----------------|-----------------|
| `evaluate_extraction_model()` | Gemini, Mistral, Ollama | Overall accuracy, per-field accuracy, avg processing time, failure rate |
| `evaluate_classification_model()` | DiT (RVL-CDIP) | Classification accuracy, per-file confidence scores, avg processing time |
| `evaluate_transcription_model()` | Whisper | Word Error Rate (WER), transcription accuracy (1 - WER), avg processing time |

### Field-Level Accuracy Scoring

Extraction evaluation uses intelligent comparison methods tailored to each field type:

| Field Type | Comparison Method | Scoring |
|-----------|-------------------|---------|
| **Amounts** (amount, vat, total) | Numeric comparison with tolerance | 1.0 if ≤0.1% diff, 0.8 if ≤5%, 0.5 if ≤10%, 0.0 otherwise |
| **Dates** | Date parsing across 5 formats (YYYY-MM-DD, DD/MM/YYYY, etc.) | 1.0 if exact match, 0.8 if ≤1 day off, 0.5 if ≤7 days, 0.0 otherwise |
| **Supplier names** | Fuzzy token-based matching (Jaccard similarity) | 0.0 to 1.0 based on token overlap between predicted and expected names |
| **Other text fields** | Exact match + substring containment | 1.0 if exact, 0.8 if one contains the other, 0.0 otherwise |

### Word Error Rate (WER) for Whisper

Audio transcription is evaluated using WER, calculated via dynamic programming (Levenshtein edit distance at the word level):

```
WER = (Insertions + Deletions + Substitutions) / Total Reference Words
```

A WER of 0.0 means perfect transcription; 1.0 means completely wrong.

### Model Comparison

After evaluating individual models, `compare_models()` generates a comparative summary that ranks models across three dimensions:

| Ranking | Criterion | Best For |
|---------|-----------|----------|
| **Best Accuracy** | Highest overall accuracy score | Choosing the most reliable extractor |
| **Fastest** | Lowest average processing time | Optimising for throughput |
| **Most Reliable** | Lowest failure rate | Ensuring consistent results |

### Ground Truth Data

The ground truth file (`benchmarks/ground_truth.json`) contains annotated test samples:

```json
{
    "file": "sample_invoice_001.pdf",
    "expected": {
        "transactor": "Acme Corp",
        "invoice_number": "INV-2024-001",
        "date": "2024-01-15",
        "amount": 250.00,
        "vat": 50.00,
        "currency": "EUR"
    },
    "expected_type": "invoice"
}
```

Each entry specifies:
- **file** — the test document filename (stored in `benchmarks/sample_invoices/`)
- **expected** — the ground truth field values for extraction evaluation
- **expected_type** — the ground truth document category for classification evaluation

### Running Evaluations

Via the web UI:
1. Navigate to `/model_evaluation`
2. Select which models to benchmark
3. View results with accuracy tables, processing times, and per-file breakdowns

Programmatically:
```python
from model_evaluation import ModelEvaluator

evaluator = ModelEvaluator(benchmarks_dir="benchmarks")
evaluator.load_ground_truth()

# Evaluate an extraction model
result = evaluator.evaluate_extraction_model(
    model_name="Gemini 3 Flash Preview",
    extract_fn=my_extraction_function
)

# Compare all evaluated models
comparison = evaluator.compare_models()

# Export results to JSON
evaluator.export_results("benchmarks/results.json")
```

---

## Usage

1. **Upload Invoices** — Navigate to `/upload`, select PDF or image files, choose a processing mode (Auto/Cloud/Local), and the system will classify, OCR, and extract invoice data
2. **Review Results** — Check extracted fields on the results page, edit if needed before saving
3. **Manage Invoices** — View, search, edit, and delete invoices at `/invoices` (expenses) and `/income`
4. **Manage Suppliers** — View and edit supplier records at `/suppliers`
5. **Bank Statements** — Upload Excel bank statements at `/process_bank_statements` for automatic transaction matching
6. **Voice Notes** — Upload audio recordings on invoice edit pages for Whisper transcription
7. **Reports & Export** — Generate financial reports and Excel exports at `/export` and `/comprehensive_report`
8. **Model Evaluation** — Compare model performance at `/model_evaluation`
9. **Currency Settings** — Configure exchange rates at `/currency_settings`

---

## License

This project was developed as a university submission for CM3020 Artificial Intelligence, demonstrating the orchestration of multiple pre-trained AI models across different data domains to solve a real-world document processing problem.
