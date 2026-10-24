FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
WORKDIR /app/backend

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/ ./
COPY config/ /app/config/

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
