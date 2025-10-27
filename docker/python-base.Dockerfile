# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        gcc \
        libpq-dev \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Configure Poetry to install to the system site-packages (no virtualenv)
RUN poetry config virtualenvs.create false

WORKDIR /app

# Default command is a no-op; per-project images will override
CMD ["python", "-V"]
