FROM python:3.12-slim

# System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential cmake pkg-config curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Optimized Pip Installs
RUN pip install --upgrade pip
RUN pip install --extra-index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple pyarrow

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -U "pathway[xpack-llm, xpack-llm-docs]" litellm nest_asyncio
RUN pip install -r requirements.txt

# Pre-load the AI Model (Prevents startup timeout)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD python frontend/main.py
