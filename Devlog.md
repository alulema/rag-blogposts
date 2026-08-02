# Devlog — rag-blogposts

Bitácora del proyecto: actividades, decisiones, desafíos y avances. Se actualiza en cada fase;
**los commits relevantes suelen incluir cambios en este archivo**.

---

## 2026-07-31 — Arranque del proyecto y Fase 0 (scaffold y convenciones)

### Contexto y decisiones
- **Objetivo confirmado:** chatbot **RAG grounded** sobre los posts de `alexisalulema.com`,
  bilingüe (EN/ES), con **citas**, como **demo efímero** (multi-contenedor, self-contained,
  $0 API, sin tecnología Microsoft interna). Fuentes de verdad: `CLAUDE.md` (plan) y
  `DEMO_INTEGRATION.md` (contrato de infra).
- **Entorno de trabajo (acordado):** esta máquina **Windows = solo autoría de código** con el
  asistente. **Docker, Ollama, Postgres/pgvector y el e2e corren en la NUC Ubuntu (64 GB RAM).**
- **LLM — Qwen confirmado:** se evaluó **Kimi K3** (2.8T params) como alternativa y **se
  descartó**. En Ollama es esencialmente `kimi-k3:cloud` (llamada externa + cuenta) y el
  self-host exige GPU de datacenter (≥640 GB VRAM / 8× H100) → viola **$0 API**,
  **self-contained**, **CPU-only** y **arranque rápido / teardown abrupto**. Seguimos con
  **Qwen2.5-1.5B-Instruct** (opción 7B por env).

### Hecho en Fase 0
- Estructura de repo: `app/`, `app/static/`, `ingest/`, `db/`, `tests/`, `.github/workflows/`.
- `.gitignore`, `.env.example`, `README.md` (stub).
- `requirements.txt` (app) + `requirements-ingest.txt` (ingesta); **Python 3.13** (local 3.13.14).
- Config **ruff + pytest** en `pyproject.toml`.
- Módulo de configuración por entorno `app/config.py` (pydantic-settings) — **fuente única** de
  parámetros: `OLLAMA_HOST`, `LLM_MODEL`, `EMBED_MODEL`, `DB_DSN`, `TOP_K`,
  `SIMILARITY_THRESHOLD`, `CHUNK_TOKENS/OVERLAP`, `PROJECT_ID`, `DEMO_SLOT`, etc.
- Tests del módulo de config (`tests/test_config.py`).
- Esta bitácora (`Devlog.md`).

### Validación
- `ruff check .`: **All checks passed** (reglas E/F/I/UP/B/SIM).
- `ruff format --check .`: **5 files already formatted** (solo fuentes `.py`).
- `pytest`: **4 passed** (tests de `app.config`).

### Nota / desafío resuelto
- **ruff 0.16 formatea bloques de código Python embebidos en Markdown** → intentaba reformatear
  `DEMO_INTEGRATION.md` (contrato copiado de infra, **no se modifica**). Decisión: excluir `*.md`
  del scope de ruff en `pyproject.toml` (`extend-exclude`); las fuentes `.py` se siguen revisando.

### Desafíos / riesgos anotados (a atacar en fases siguientes)
- **MiniLM cap de ~128 tokens:** `paraphrase-multilingual-MiniLM-L12-v2` trunca la entrada a
  ~128 tokens; el chunk objetivo de `CLAUDE.md` es ~600. En **Fase 1** decidir estrategia
  (chunks alineados al modelo vs. embeber sub-ventanas y mantener ~600 para el contexto del LLM).
- **Tamaño de imágenes** (Qwen + embeddings horneados) vs. arranque en frío: balancear con Q4.
- **Umbral grounded** (`SIMILARITY_THRESHOLD=0.30`): placeholder; calibrar con datos reales (F2).

### Siguiente
- **Fase 1 — Ingesta:** `sitemap-index.xml` → `sitemap-0.xml` (confirmado: un solo sub-sitemap) →
  filtrar `/blog/*` y `/es/blog/*` → limpiar HTML → chunk + embed → `db/dump.sql` de muestra.
  Validar calidad de chunks/metadata.

---

## 2026-07-31 — Fase 1 (ingesta: pipeline + validación de muestra)

### Hecho
- Pipeline modular en `ingest/`: `fetch` (sitemap → URLs → HTML), `clean` (extracción del contenido
  Astro), `tokens` (contador: tokenizer del modelo o heurística), `chunk` (sentence-aware ~600 tokens,
  solape ~80), `embed` (mean-pool de sub-ventanas; NUC), `dump` (`dump.sql` + `snapshot.jsonl`),
  `run` (CLI con `--dry-run`, `--limit`, `--langs`).
- `db/schema.sql`: tabla `chunks (url, title, lang, published, chunk_index, content, embedding vector(384))`
  + índice **HNSW cosine** (se crea tras los INSERT en el dump).
- Tests (**22 total**): fetch (filtro de sitemap), clean (metadata + remoción de ToC/iconos/KaTeX/nbsp +
  código preservado), chunk (solape, código entero, propagación de metadata), dump (schema/escape/vector
  literal/HNSW/snapshot), embed (windowing).

### Hallazgos / desafíos resueltos (sobre datos reales)
- Sitio **Astro**: contenido en `.post-content`; `.post-header`/`.post-footer` son meta/navegación.
  Corpus **~34 posts** (~28 EN + ~6 ES) desde un único `sitemap-0.xml`.
- **Ligaduras de iconos** (Material Symbols, p.ej. `beenhere`) y **Table of Contents** (heading + lista
  de anclas `#`) → removidos del cuerpo.
- **Mojibake**: `requests` adivinaba Latin-1 → se **fuerza UTF-8** en el fetch; `&nbsp;`/zero-width/BOM
  normalizados.
- **KaTeX duplicaba** el texto de las fórmulas (MathML + anotación LaTeX + visual) → se elimina
  `.katex-mathml` y se conserva la visual (`.katex-html`).
- **Decisión — cap de ~128 tokens de MiniLM:** se mantienen chunks ~600 (CLAUDE.md) y el vector
  representa el **chunk completo** vía mean-pooling de sub-ventanas ≤128 tokens (evita pérdida de recall
  por truncado). En `ingest/embed.py`.

### Validación
- `ruff` + `pytest`: OK (22 tests).
- **Dry-run real** (`python -m ingest.run --dry-run`, heurística de tokens): 4 EN + 6 ES; 4–21 chunks
  por post; tamaños ~570 tokens (mediana); sin `beenhere`/ToC; código, acentos y metadata (title/lang/
  date) correctos.

### Pendiente (en NUC/CI, requiere torch)
- Run real con embeddings → `db/dump.sql` + `db/snapshot.jsonl` (corpus completo): `python -m ingest.run`.
  No se ejecuta en la máquina de autoría por el split de entorno acordado.

### Siguiente
- **Fase 2 — App + RAG core:** init pgvector, retrieval top-k (cosine + umbral grounded), armado de
  prompt, cliente Ollama en streaming, endpoint `POST /chat` SSE. Prueba por consola/SSE en el NUC.

---

## 2026-08-02 — Fase 2 (App + RAG core, sin UI)

### Hecho
- `app/embeddings.py`: `Embedder` (query → 384-d normalizado; `sentence-transformers` lazy).
- `app/retrieval.py`: `Retriever` sobre pool inyectado; **top-k coseno** (`<=>`, vector como literal
  `::vector`) + **umbral grounded**; dataclass `RetrievedChunk`.
- `app/rag.py`: system prompt grounded (cita fuentes + responde en el idioma de la pregunta +
  rehúsa fuera de corpus), `build_messages` (system+contexto+historial+pregunta), `citations`
  (dedupe por URL), `detect_lang`, `refusal_message`.
- `app/ollama_client.py`: `OllamaClient.stream_chat` (async httpx, `/api/chat`, relay token a token).
- `app/main.py`: FastAPI + lifespan (pool psycopg + Embedder + ensure schema/índice HNSW);
  `POST /chat` → **SSE** (`sources` → `token`* → `done`; `error` si Ollama falla); `/` placeholder;
  `/healthz`. Sin auth/TLS (gateway). **Grounded-only:** sin contexto no llama al LLM y rehúsa en
  el idioma detectado.
- `requirements.txt`: `psycopg[binary,pool]` (quitado `pgvector`; vectores como literal).

### Decisiones
- **Vectores como literal `::vector`** (sin adaptador pgvector en Python) → menos dependencias.
- **Inyección de dependencias** (retriever/ollama vía `Depends` + `Annotated`) → endpoint testeable
  con TestClient **sin** ejecutar el lifespan (sin torch/psycopg/Ollama).
- **Umbral grounded**: si nada supera `SIMILARITY_THRESHOLD`, rehúso *canned* (sin LLM) en el idioma.

### Validación
- ruff + **34 tests** (rag, retrieval, api). SSE validado con TestClient + retriever/ollama falsos
  (orden `sources/token/done`, rehúso grounded, 400 si el último msg no es `user`, health/placeholder).
- App **importable sin torch/psycopg** (imports pesados lazy) — confirmado por los tests.

### Pendiente (NUC: Postgres+pgvector sembrado + Ollama con Qwen)
- e2e por consola/curl: `uvicorn app.main:app --host 0.0.0.0 --port 8080` →
  `curl -N -X POST localhost:8080/chat -H 'content-type: application/json'
  -d '{"messages":[{"role":"user","content":"What are activation functions?"}]}'`
- Calibrar `SIMILARITY_THRESHOLD` (0.30 es placeholder) con datos reales.

### Siguiente
- **Fase 3 — UI de chat en `/`**: single-page vanilla, SSE con `fetch()`+`ReadableStream`,
  tema del sitio en vivo (`demo-theme.css`), citas y rehúso grounded.
