FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 are bundled in psycopg2-binary; keep image lean.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Seed the demo data on first build so the app has a rehearsed pair available.
RUN python -m app.seed.generator --out ./data || true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
