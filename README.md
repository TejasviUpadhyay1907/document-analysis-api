# AI-Powered Document Analysis & Extraction API

An intelligent document processing API that accepts PDF, DOCX, and image files, extracts text, and returns structured JSON containing a summary, named entities, sentiment classification, and document-type-specific structured data.

---

## Description

This API was built for **Track 2: AI-Powered Document Analysis & Extraction**. It uses a hybrid approach combining deterministic rule-based processing with an optional LLM layer (OpenRouter) to deliver consistent, high-quality document intelligence.

The system:
- Accepts documents as Base64-encoded strings
- Supports PDF, DOCX, and image (OCR) formats
- Classifies document type automatically (resume, invoice, incident report, article, official letter, notice, identity, general)
- Extracts named entities using spaCy NER + regex
- Generates concise AI-powered summaries
- Classifies sentiment as Positive, Neutral, or Negative
- Returns structured document-specific data depending on document type

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11 |
| Framework | FastAPI |
| PDF Extraction | PyMuPDF (fitz) |
| DOCX Extraction | python-docx |
| Image OCR | Tesseract + pytesseract + Pillow |
| NLP / NER | spaCy (en_core_web_sm) + regex |
| LLM / AI | OpenRouter API (meta-llama, arcee-ai free models) |
| HTTP Client | httpx |
| Deployment | Docker on Render |

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/TejasviUpadhyay1907/document-analysis-api.git
cd document-analysis-api
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install spaCy model

```bash
python -m spacy download en_core_web_sm
```

### 4. Install Tesseract OCR

**Linux / Render:**
```bash
apt-get install -y tesseract-ocr tesseract-ocr-eng
```

**Windows:**
Download from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and set `TESSERACT_CMD` in `.env`.

**macOS:**
```bash
brew install tesseract
```

### 5. Set environment variables

```bash
cp .env.example .env
```

Edit `.env`:
```env
API_KEY=your_secret_api_key
OPENROUTER_API_KEY=your_openrouter_key   # optional
OPENROUTER_MODEL=arcee-ai/trinity-mini:free
```

### 6. Run the application

```bash
uvicorn src.main:app --reload
```

API will be available at: `http://127.0.0.1:8000`

Swagger docs: `http://127.0.0.1:8000/docs`

---

## API Usage

### Endpoint

```
POST /api/document-analyze
```

### Headers

```
x-api-key: your_secret_api_key
Content-Type: application/json
```

### Request Body

```json
{
  "fileName": "sample.pdf",
  "fileType": "pdf",
  "fileBase64": "BASE64_ENCODED_FILE_CONTENT"
}
```

Supported `fileType` values: `pdf`, `docx`, `image`

### Response

```json
{
  "status": "success",
  "fileName": "sample.pdf",
  "documentType": "invoice",
  "summary": "Invoice issued by ABC Pvt Ltd to Ravi Kumar for Rs 10,000 dated 10 March 2026.",
  "entities": {
    "names": ["Ravi Kumar"],
    "organizations": ["ABC Pvt Ltd"],
    "dates": ["2026"],
    "amounts": ["10000 rupees"],
    "emails": [],
    "phones": []
  },
  "sentiment": "Neutral",
  "documentData": {
    "invoice_id": "",
    "vendor": "ABC Pvt Ltd",
    "customer": "Ravi Kumar",
    "date": "10 March 2026",
    "amount": "10000 rupees"
  },
  "extractedText": "..."
}
```

### Test with cURL

```bash
# Encode a file to Base64
base64 -w 0 sample.pdf > encoded.txt

# Send request
curl -X POST https://document-analysis-api-docker.onrender.com/api/document-analyze \
  -H "Content-Type: application/json" \
  -H "x-api-key: your_api_key" \
  -d "{\"fileName\": \"sample.pdf\", \"fileType\": \"pdf\", \"fileBase64\": \"$(cat encoded.txt)\"}"
```

---

## Approach

### Text Extraction

- **PDF**: PyMuPDF iterates all pages and extracts selectable text
- **DOCX**: python-docx extracts paragraph text preserving structure
- **Image**: Tesseract OCR via pytesseract with Pillow for image loading

### Document Classification

Rule-based deterministic classifier detects document type using keyword signals and structural heuristics:
- **Resume**: education/skills/projects sections + contact info
- **Invoice**: invoice keyword + monetary amount
- **Incident Report**: breach/attack/vulnerability keywords
- **Official Letter / Cover Letter**: Dear + Sincerely patterns
- **Notice**: NOTICE keyword + institute/department
- **Identity**: Name/DOB/Blood Group fields
- **Article**: long analytical text with industry/research keywords

### Entity Extraction

Hybrid approach:
- **spaCy NER** (`en_core_web_sm`) for person names and organizations
- **Regex patterns** for emails, phone numbers, dates, and monetary amounts
- **Post-processing filter** removes OCR noise, skill names misclassified as entities, and short fragments

### Summary Generation

Two-layer approach:
1. **LLM (OpenRouter)** — when `OPENROUTER_API_KEY` is configured, sends extracted text to a free LLM model with a structured system prompt for high-quality summaries
2. **Deterministic fallback** — type-aware summary builder generates clean 1-2 sentence summaries when LLM is unavailable or returns weak output

### Sentiment Analysis

- **Incident reports**: always `Negative`
- **Resumes, invoices, notices, letters**: always `Neutral`
- **Articles / general**: LLM-based or keyword scoring (positive/negative word counts)

---

## Deployment

The API is deployed on **Render** using Docker.

Live URL: `https://document-analysis-api-docker.onrender.com`

Note: Free tier instances spin down after inactivity. First request may take 30-60 seconds.

### Docker

```bash
docker build -t document-analysis-api .
docker run -p 8000:8000 \
  -e API_KEY=your_key \
  -e OPENROUTER_API_KEY=your_openrouter_key \
  document-analysis-api
```

---

## Project Structure

```
document-analysis-api/
├── src/
│   ├── main.py                    # FastAPI app + endpoint
│   ├── auth.py                    # API key validation
│   ├── config.py                  # Environment config
│   ├── schemas.py                 # Request/response models
│   ├── extractors/
│   │   ├── pdf_extractor.py       # PyMuPDF extraction
│   │   ├── docx_extractor.py      # python-docx extraction
│   │   └── image_extractor.py     # Tesseract OCR
│   ├── services/
│   │   ├── text_cleaner.py        # Text normalization
│   │   ├── entity_extractor.py    # spaCy + regex NER
│   │   ├── summarizer.py          # Type-aware summarizer
│   │   ├── llm_analyzer.py        # OpenRouter LLM integration
│   │   ├── output_finalizer.py    # Final correction layer
│   │   └── document_parsers/      # Type-specific data builders
│   └── utils/
│       └── file_utils.py          # Base64 decode
├── Dockerfile
├── requirements.txt
└── .env.example
```
