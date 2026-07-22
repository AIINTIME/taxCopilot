FROM python:3.12-slim

# openssl/ca-certificates are required by the Prisma Python client's query-engine binary
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# public/uploads/profiles and uploads/ are also created lazily at runtime by the app,
# this just guarantees they exist (and are writable) before any volume is mounted over them.
RUN mkdir -p public/uploads/profiles uploads \
    && python -m prisma generate --schema prisma/schema.prisma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
