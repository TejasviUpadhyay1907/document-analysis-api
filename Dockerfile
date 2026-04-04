FROM python:3.11-slim

# Install system dependencies: Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy application source
COPY . .

# Render sets PORT dynamically
ENV PORT=8000

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port $PORT"]
