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

### Comandos (se irán completando por fase)

```bash
# Local e2e (en la NUC) — Fase 4+
docker compose up -d --build      # → http://localhost:8080

# Ingesta local (genera db/dump.sql) — Fase 1+
python ingest/run.py

# Lint + tests (autoría)
ruff check . && ruff format --check .
pytest
```

## Estado

En construcción por fases (ver `Devlog.md`): **Fase 0 (scaffold)** ✅ · Ingesta → App+RAG → UI →
Contenedores/e2e → CI → Hand-off.
