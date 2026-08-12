# rag-blogposts

Chatbot **RAG** *grounded* sobre los posts del blog de
[alexisalulema.com](https://alexisalulema.com): responde preguntas **fundamentado en los posts**,
con **citas/enlaces** al post fuente. Bilingüe (EN/ES). Es uno de los **demos efímeros** del sitio:
se provisiona on-demand, corre un rato y se destruye solo.

> **Stack 100% OSS · $0 de API de pago · sin tecnología Microsoft en el stack interno ·
> self-contained** (sin secretos en runtime, sin llamadas externas en producción).

## Documentos clave

- **`CLAUDE.md`** — plan del proyecto (fuente de verdad del stack y la arquitectura).
- **`DEMO_INTEGRATION.md`** — contrato de integración con la infra de demos efímeros.
- **`Devlog.md`** — bitácora viva (actividades, decisiones, desafíos, avances).

## Stack

| Capa | Tecnología |
|---|---|
| App | FastAPI (Python 3.13), UI de chat en `/` + streaming **SSE** |
| LLM | **Qwen2.5-1.5B-Instruct** vía **Ollama**, local (opción 7B por env) |
| Embeddings | `sentence-transformers` `paraphrase-multilingual-MiniLM-L12-v2` (384-d) |
| Vector store | Postgres 16 + **pgvector**, efímero, sembrado desde `dump.sql` horneado |

## Arquitectura (runtime)

Un Container App con **3 contenedores** que comparten `localhost`:
`app` (FastAPI `:8080`, ingress interno) · `ollama` (`:11434`) · `db` (postgres+pgvector `:5432`).

## Desarrollo

- **Autoría de código:** máquina Windows (con el asistente).
- **Docker / Ollama / Postgres / e2e:** NUC Ubuntu (64 GB RAM).

> **Aislamiento:** en local usa un **venv** (no el Python del sistema/conda). En el contenedor
> del demo (Fase 4) se instala en el Python del sistema — ahí el contenedor **es** el sandbox.

### Lint + tests (autoría)

```bash
python -m venv .venv && .\.venv\Scripts\activate   # Windows (Linux/mac: source .venv/bin/activate)
pip install -r requirements.txt
pip install ruff pytest                             # herramientas de dev
ruff check . && ruff format --check .
pytest
```

### Ejecución y pruebas e2e (local, en la NUC)

Requiere Docker + Ollama. Los defaults de `app/config.py`
(`DB_DSN=postgresql://rag:rag@localhost:5432/rag`, `OLLAMA_HOST=http://localhost:11434`,
`LLM_MODEL=qwen2.5:1.5b-instruct`) coinciden con estos comandos, así que **no hay que tocar env**.

```bash
# 0) venv + deps (desde la raíz del repo)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt                 # app (FastAPI + torch para embed de la query)

# 1) Corpus → db/dump.sql (si aún no existe)
pip install -r requirements-ingest.txt          # deps de ingesta (requests, bs4, lxml, …)
python -m ingest.run                            # genera db/dump.sql + db/snapshot.jsonl
#   python -m ingest.run --dry-run --limit 3    # chequeo rápido sin embeddings

# 2) Postgres + pgvector (Docker) y sembrado del corpus
docker run -d --name rag-pg \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  -p 5432:5432 pgvector/pgvector:pg16
docker exec -i rag-pg psql -U rag -d rag < db/dump.sql
docker exec -it rag-pg psql -U rag -d rag -c "SELECT count(*) FROM chunks;"
#   tras un reboot: docker start rag-pg   (NO repetir docker run)

# 3) Ollama + modelo (nativo o en Docker). Debe escuchar en localhost:11434
ollama pull qwen2.5:1.5b-instruct

# 4) App (ingress interno, sin TLS/auth — los pone el gateway en prod)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 5) Probar el endpoint SSE (otra terminal)
curl -N -X POST localhost:8080/chat -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"What are activation functions?"}]}'
#   respuesta esperada: event: sources (citas) → event: token* → event: done
```

Health check: `curl localhost:8080/healthz` → `{"status":"ok"}`.

### Calibrar el umbral grounded (opcional, en la NUC con pgvector sembrado)

`SIMILARITY_THRESHOLD` decide el rehúso *grounded* (responder solo si el top-1 de similitud
coseno lo supera). Para recomendarlo con datos reales:

```bash
python -m tools.calibrate_threshold        # batería in/out-of-corpus → umbral recomendado
```

### Local e2e con contenedores (Fase 4+)

```bash
docker compose up -d --build      # app + ollama + db juntos → http://localhost:8080
```

## Estado

En construcción por fases (ver `Devlog.md`): **Fase 0 (scaffold)** ✅ · **Fase 1 (ingesta)** ✅ ·
**Fase 2 (app + RAG core)** ✅ — *primer e2e verde en la NUC* · Fase 3 (UI) → Contenedores/e2e →
CI → Hand-off.
