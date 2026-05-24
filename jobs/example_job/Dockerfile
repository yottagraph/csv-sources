# Cloud Run Jobs container. The deploy script auto-generates a Dockerfile
# matching this template if one is missing — only override here if your job
# needs system packages, custom base image, or non-standard entrypoint.
FROM python:3.12-slim

WORKDIR /app

# System deps occasionally needed by data-processing libs (psycopg, pyarrow, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run Jobs invokes the container's CMD/entrypoint; no port binding.
CMD ["python", "main.py"]
