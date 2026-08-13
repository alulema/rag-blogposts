# Imagen `app` (FastAPI + RAG). CPU-only, self-contained: hornea el modelo de embeddings
# en build-time y corre OFFLINE en runtime (sin llamadas externas en producción).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/models

WORKDIR /app

# libgomp1: runtime de OpenMP que necesita torch (CPU).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# torch CPU-only primero (evita arrastrar las libs CUDA → imagen mucho más liviana);
# luego el resto (sentence-transformers ya ve torch satisfecho).
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY requirements.txt .
RUN pip install -r requirements.txt

# Hornear el modelo de embeddings (~470 MB) en la caché de la imagen.
ARG EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

# A partir de aquí, runtime OFFLINE (self-contained; sin descargas en producción).
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# Solo lo necesario (NO se copia db/dump.sql: eso vive en la imagen `db`).
COPY app/ ./app/
COPY db/schema.sql ./db/schema.sql

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
