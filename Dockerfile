FROM python:3.11-slim

# Install Tesseract OCR + English data in one clean layer
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model (non-fatal)
RUN python -m spacy download en_core_web_sm || true

COPY . .

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]