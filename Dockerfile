FROM python:3.11-slim

# System deps for lxml / BeautifulSoup
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY main.py .

# Data directories — these will be bind-mounted or managed as volumes
RUN mkdir -p data/chroma data/memory

ENTRYPOINT ["python", "main.py"]
CMD ["chat"]
