# Use a stable Python 3.12 base
FROM python:3.12-slim

# Install system dependencies (Replaces your 'brew install' step)
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the specific pyarrow wheels your README mentions
RUN pip install --upgrade pip
RUN pip install --extra-index-url https://pypi.anaconda.org/scientific-python-nightly-wheels/simple pyarrow

# Install Pathway and your requirements
COPY requirements.txt .
RUN pip install -U "pathway[xpack-llm, xpack-llm-docs]" litellm nest_asyncio
RUN pip install -r requirements.txt

# Copy the rest of your code
COPY . .

# Ensure Python can find your 'backend' folder
ENV PYTHONPATH=/app

# Expose the Gradio port
EXPOSE 7860

# Run the frontend script
CMD ["python", "frontend/main.py"]