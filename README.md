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
- **Processing Mode selector**: choose Auto (full fallback chain), Cloud AI Only (Gemini + Mistral), or Local Only (Tesseract + Ollama) on the upload page
- **Model Status panel**: real-time green/red availability indicators for all 5 models via AJAX, visible before uploading
- **Real-time upload progress**: live progress bar with per-file status updates during multi-file batch uploads via AJAX polling

### Document Classification
- Every uploaded document is automatically classified by the DiT Vision Transformer
- Categories: invoice, receipt, bank statement, credit note, other
- Classification confidence score displayed on results page

### Voice Notes (Whisper)
- Upload audio recordings (MP3, WAV, M4A, OGG, FLAC, WebM) on the invoice edit page
- Whisper transcribes the audio and appends the text to the invoice's notes field
- Standalone voice memos can also create new invoice entries

### Bank Statement Reconciliation
- Upload any bank statement in Excel (.xlsx, .xls) or CSV format — not limited to a specific bank
- System auto-detects column mappings using regex-based header matching (supports English, Greek, German, Spanish, French column names)
- Handles metadata rows automatically — skips account info, opening/closing balance rows to find the real transaction header
- Supports two amount formats: separate Debit/Credit columns (e.g., Pakistani banks) and single Amount + Sign column with D/C indicator (e.g., Alpha Bank Greece)
- Currency-aware matching algorithm converts invoice amounts to the bank statement's currency before comparing
- Confidence score (0-100%) shown for each matched transaction
- Exported results include: matched supplier, invoice number, confidence, converted amounts, and match details

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
- Comparison table evaluates 4 models individually across different data domains:
  - **Gemini 3 Flash Preview** — LLM Vision + Text
  - **Phi 3.5 via Ollama** — Local LLM (Text), shows "Skipped" status if Ollama is unavailable
  - **Tesseract OCR** — Image OCR
  - **DiT Document Classifier** — Image Classification (Vision Transformer)
- Measures processing time, field-level accuracy, and failure rates

---

## Bank Statement Matching Algorithm

The bank statement reconciliation system uses a multi-factor scoring algorithm to match bank transactions against invoice records. This is particularly challenging for international transactions where currency conversion, transfer fees, and varying bank formats must be handled.

### Format Auto-Detection

When a bank statement is uploaded, the system:

1. **Scans rows 0-9** for the header row, skipping metadata (account number, opening/closing balance, currency info)
2. **Validates headers** by requiring at least 3 columns including a date column AND a financial column (debit/credit/amount)
3. **Maps columns** using regex patterns that support multiple languages and naming conventions:

| Standard Field | Example Column Names Matched |
|---------------|------------------------------|
| Date | `Date`, `Booking Date`, `Transaction Date`, `Valeur`, `Ημερομηνία` |
| Description | `Description`, `Details`, `Narrative`, `Reference Number`, `Περιγραφή` |
| Reference | `Doc No`, `Transaction number`, `Ref`, `Check No` |
| Debit | `Debit`, `Withdrawal`, `Charge`, `Χρέωση` |
| Credit | `Credit`, `Deposit`, `Πίστωση`, `Income` |
| Amount | `Amount`, `Sum`, `Value`, `Ποσό` |
| Amount Sign | `Amount Sign`, `D/C`, `DR/CR`, `Sign` |
| Balance | `Balance`, `Available Balance`, `Υπόλοιπο` |

### Amount + Sign Splitting

European bank statements (e.g., Alpha Bank Greece) often use a single `Amount` column with a separate `Amount Sign` column containing `D` (debit) or `C` (credit). The converter detects this pattern and automatically splits into separate debit/credit columns.

### Currency-Aware Matching

Before comparing amounts, the algorithm converts all invoice amounts to the bank statement's currency using the configured exchange rates:

```
Invoice: 520.89 USD × 278.50 (USD_TO_PKR rate) = 145,067.87 PKR
Bank transaction: 139,898.58 PKR (credit)
Difference: 3.56% (accounted for by SWIFT transfer fee ~$18.56)
```

### Scoring System

Each bank transaction is scored against every invoice using four weighted criteria:

| Criterion | Max Weight | Priority | Description |
|-----------|-----------|----------|-------------|
| **Amount Closeness** | 0.55 (55%) | Highest | Compares currency-converted invoice amount against bank transaction amount. Allows up to 15% deduction for international transfer fees (SWIFT, intermediary charges, local taxes). |
| **Date Proximity** | 0.20 (20%) | Medium | How close the transaction date is to the invoice date. Uses a step function with up to 30-day tolerance for international transfers. |
| **Supplier Name** | 0.15 (15%) | Lower | Checks if the supplier name (or significant words from it) appears in the bank transaction description or reference. |
| **Invoice Number** | 0.10 (10%) | Lowest | Checks if the invoice number appears in the transaction description or reference. |

### Gross Amount Matching

The algorithm first attempts to match using the **gross amount** (net amount + VAT) from each invoice. If the invoice has both `amount` and `vat` fields, their sum is used as the comparison amount — this reflects how bank payments typically represent the full invoice total including tax. If no VAT is recorded, the net amount is used.

### Amount Scoring Detail

The amount scoring accounts for the fact that international transfers typically **lose** money to fees — the received amount is always slightly less than the converted invoice amount. The scoring is **direction-aware**:

**Credit transactions (money received):**

| Condition | Score | Interpretation |
|-----------|-------|---------------|
| Bank amount > 102% of converted invoice | 0.00 | Cannot receive more than owed (2% rounding buffer) |
| Difference ≤ 0.5% | 0.55 | Near-exact match |
| Difference ≤ 5% | 0.50 | Small bank fee deduction |
| Difference ≤ 15% | 0.45 → 0.20 (linear decay) | Larger deductions (SWIFT fees, intermediary charges) |
| Difference > 15% | 0.00 | Too large a discrepancy |

**Debit transactions (money paid out):**

| Condition | Score | Interpretation |
|-----------|-------|---------------|
| Bank amount > 110% of converted invoice | 0.00 | Allows up to 10% overage for bank charges added on top |
| Difference ≤ 0.5% | 0.55 | Near-exact match |
| Difference ≤ 5% | 0.50 | Small fee added |
| Difference ≤ 15% | 0.45 → 0.20 (linear decay) | Larger surcharges |
| Difference > 15% | 0.00 | Too large a discrepancy |

### Date Scoring Detail

| Days Apart | Score | Typical Scenario |
|-----------|-------|-----------------|
| 0 days | 0.20 | Same-day settlement |
| 1-3 days | 0.18 | Domestic transfer |
| 4-7 days | 0.15 | Standard international transfer |
| 8-14 days | 0.10 | Delayed processing |
| 15-30 days | 0.05 | Significant delay |
| > 30 days | 0.00 | Unlikely to be related |

### Directional Matching

The algorithm respects transaction direction:
- **Credit transactions** (money in) are first matched against income invoices, then fall back to expense invoices if no income match is found
- **Debit transactions** (money out) are first matched against expense invoices, then fall back to income invoices

This fallback ensures matching works even when invoices are not explicitly marked as income/expense.

### Match Threshold

A minimum score of **0.30 (30%)** is required to accept a match. The highest-scoring invoice for each transaction is selected as the best match.

### Output Columns

The processed bank statement Excel file includes these enrichment columns:

| Column | Description |
|--------|-------------|
| `matched_supplier` | Supplier name from the matched invoice |
| `matched_invoice_number` | Invoice number of the matched invoice |
| `match_confidence` | 0-100% confidence score |
| `match_method` | Which scoring criteria contributed (e.g., `close_amount+date_proximity`) |
| `converted_invoice_amount` | Invoice amount converted to the bank statement's currency |
| `amount_difference_pct` | Percentage difference between converted invoice and bank transaction |
| `match_details` | Human-readable breakdown (e.g., "Invoice 2026: 520.89 USD = 145,067.87 PKR, bank: 139,898.58 PKR (diff: 3.6%)") |

### Tested Bank Formats

| Bank | Country | Format | Amount Style | Verified |
|------|---------|--------|-------------|----------|
| Alfalah Bank | Pakistan | CSV with 4 metadata rows | Separate Debit + Credit columns | Yes |
| Alpha Bank | Greece | Excel | Single Amount + Amount Sign (D/C) | Yes |

The generic column detection supports any bank statement that uses recognisable column names in English, Greek, German, Spanish, or French.

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
│   ├── test_bank_statement_converter.py
│   └── test_model_evaluation.py
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

The project includes a comprehensive **pytest** test suite with **132 test functions** across 8 test modules, covering all core managers, processors, AI model wrappers, and the model evaluation framework.

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
| `test_bank_statement_converter.py` | 13 | Column auto-detection (standard and alternative header names), Excel format detection, conversion to standard format, currency-aware cross-currency matching (USD→PKR with SWIFT fee tolerance), directional matching (debit→expense, credit→income with fallback), no-match when bank exceeds invoice, output column validation, empty invoice edge case |
| `test_model_evaluation.py` | 46 | Evaluator init, ground truth loading (valid/missing), field accuracy (exact/case-insensitive/numeric/date/fuzzy/substring/missing), AI key normalisation (capitalised keys mapped to snake_case ground truth keys), list-to-string description handling, description fuzzy matching, numeric comparison (tolerance bands, zero handling, invalid input, absolute value for credit notes), date comparison (same/cross-format, proximity scoring), fuzzy string matching (Jaccard similarity, edge cases), Word Error Rate (WER) calculation, extraction model evaluation (mock extract, no ground truth, failing model, missing files), model comparison rankings (best accuracy, fastest, most reliable), empty result structure validation |

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
3. **Key normalisation** maps AI output keys (e.g., `"Transactor"`, `"Invoice Date"`, `"Tax Amount"`) to ground truth keys (`"transactor"`, `"date"`, `"vat"`), and list values (e.g., `["Service A", "Service B"]`) are joined into strings before comparison
4. Results are displayed on the `/model_evaluation` web page and can be exported to `benchmarks/results.json`

### Evaluation Types

The framework evaluates 4 models individually in the comparison table, plus supports classification and transcription evaluation:

| Model in Comparison Table | Domain | Evaluation Method | Metrics Produced |
|---------------------------|--------|-------------------|-----------------|
| **Gemini 3 Flash Preview** | LLM Vision + Text | `evaluate_extraction_model()` | Overall accuracy, per-field accuracy, avg processing time, failure rate |
| **Phi 3.5 via Ollama** | Local LLM (Text) | `evaluate_extraction_model()` | Same as above; shows "Skipped" status if Ollama is not running |
| **Tesseract OCR** | Image (OCR) | `evaluate_extraction_model()` | Overall accuracy, avg processing time, failure rate |
| **DiT Document Classifier** | Image Classification | `evaluate_classification_model()` | Classification accuracy, per-file confidence scores, avg processing time |

Additional evaluation methods available:

| Evaluation Method | Models | Metrics Produced |
|-------------------|--------|-----------------|
| `evaluate_transcription_model()` | Whisper | Word Error Rate (WER), transcription accuracy (1 - WER), avg processing time |

### Field-Level Accuracy Scoring

Extraction evaluation uses intelligent comparison methods tailored to each field type:

| Field Type | Comparison Method | Scoring |
|-----------|-------------------|---------|
| **Amounts** (amount, vat, total) | Numeric comparison with tolerance, absolute values for credit notes | 1.0 if ≤0.1% diff, 0.8 if ≤5%, 0.5 if ≤10%, 0.0 otherwise |
| **Dates** | Date parsing across 5 formats (YYYY-MM-DD, DD/MM/YYYY, etc.) | 1.0 if exact match, 0.8 if ≤1 day off, 0.5 if ≤7 days, 0.0 otherwise |
| **Supplier names** | Fuzzy token-based matching (Jaccard similarity) | 0.0 to 1.0 based on token overlap between predicted and expected names |
| **Descriptions** | Fuzzy token-based matching (Jaccard similarity) | 0.0 to 1.0 — handles AI paraphrasing of invoice descriptions |
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

### Benchmark Results

Evaluation against 6 sample invoices (EUR, USD, PKR, BGN currencies including a credit note and receipt):

| Model | Domain | Accuracy | Avg Time | Failure Rate |
|-------|--------|----------|----------|-------------|
| **Gemini 3 Flash Preview** | LLM Vision + Text | 87.1% | ~2-4s | 0% |
| **Phi 3.5 via Ollama** | Local LLM (Text) | 84.7% | ~3-6s | 0% |
| **DiT (RVL-CDIP)** | Image Classification | 66.7% | ~1s | 0% |
| **Tesseract OCR** | Image (OCR) | 0.0% | <1s | 0% |

**Notes:**
- Tesseract's 0% accuracy is expected — it outputs raw OCR text, not structured field extraction, so field-level comparison scores zero
- DiT's 66.7% = 4 of 6 documents correctly classified (document type classification, not field extraction)
- Gemini and Phi scores reflect field-level accuracy across all ground truth fields (amounts, dates, supplier names, descriptions, currency)

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
5. **Bank Statements** — Upload Excel or CSV bank statements at `/process_bank_statements` for automatic currency-aware transaction matching with confidence scores
6. **Voice Notes** — Upload audio recordings on invoice edit pages for Whisper transcription
7. **Reports & Export** — Generate financial reports and Excel exports at `/export` and `/comprehensive_report`
8. **Model Evaluation** — Compare model performance at `/model_evaluation`
9. **Currency Settings** — Configure exchange rates at `/currency_settings`

---

## License

This project was developed as a university submission for CM3070 Final Project, demonstrating the orchestration of multiple pre-trained AI models across different data domains to solve a real-world document processing problem.
