# syntax=docker/dockerfile:1

FROM python:3.12-slim

# We need build tools for spaCy and torch, possibly
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set a working directory
WORKDIR /app

# Copy our requirements file first
COPY requirements.txt /app/

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of our app
COPY . /app

# If you want to download or link the spaCy model explicitly, do that here
# e.g. for a direct pipeline: RUN python -m spacy download en_core_web_trf
# If you pinned it in requirements.txt, it might already be installed.

# Expose the port for FastAPI (default 80 or 8000)
EXPOSE 80

# By default, run the app with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
