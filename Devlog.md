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

---

## 2026-08-03 — 🎉 Primer e2e verde en la NUC (Fase 1+2 con stack real)

Primer flujo RAG completo funcionando end-to-end en la NUC Ubuntu con el stack real
(pgvector sembrado + Ollama/Qwen2.5-1.5B-Instruct + FastAPI). **Hito.**

### Setup validado
- **Ingesta real:** `python -m ingest.run` → `db/dump.sql` + `db/snapshot.jsonl` (**178 chunks / 34 posts**,
  28 EN + 6 ES). Deps de ingesta en el venv (`requirements-ingest.txt`).
- **DB:** contenedor `pgvector/pgvector:pg16` (`rag/rag/rag` @ 5432), sembrado con el dump.
- **LLM:** Ollama nativo, `qwen2.5:1.5b-instruct` (tag confirmado válido contra el registry).
- **App:** `python -m uvicorn app.main:app --host 0.0.0.0 --port 8080` en el venv.

### Resultado del `curl POST /chat` ("What are activation functions?")
- ✅ **sources**: recuperó los 2 posts correctos (EN *Activation Functions* + ES *Funciones de
  Activación*) → **retrieval cross-lingual** OK; citas con título/url/lang/fecha, dedupe por post.
- ✅ **streaming SSE**: tokens uno a uno, cerrado con `event: done`.
- ✅ **grounded**: respuesta anclada al contenido real (ω/weights, sigmoid, ReLU, Swish, backprop).
- ✅ **idioma**: pregunta EN → respuesta EN.

### Notas / benignos (confirmados)
- `HF_TOKEN unauthenticated` y `Token indices (510 > 128)` → **ruido**, no errores (el embedder parte
  en ventanas ≤128 + mean-pooling; el run completa y escribe 178 chunks). Silenciable con
  `TRANSFORMERS_VERBOSITY=error`.
- Posts con "1 chunk" → verificado que son cortos de verdad (video/how-tos), no fuga del extractor.
- **Aprendizajes de entorno (NUC):** correr desde la raíz del repo + venv (`python -m uvicorn`,
  no `uvicorn` suelto, para no caer al Python de conda base); `psycopg[binary,pool]` incluye
  `psycopg_pool`; tras reboot `docker start rag-pg` (no `docker run`).

### Pendiente (no bloquea)
- Calibrar `SIMILARITY_THRESHOLD` (0.30 placeholder) con más preguntas reales, incl. fuera de corpus
  (verificar rehúso grounded) y una pregunta ES.

---

## 2026-08-03 — Fase 3 (UI de chat en `/`)

### Hecho
- UI single-page vanilla en `app/static/`: `index.html`, `styles.css`, `app.js`.
- **Streaming token a token** consumiendo el SSE de `POST /chat` con `fetch()` + `ReadableStream`
  (parser SSE manual; `EventSource` no sirve porque el endpoint es POST). Maneja los eventos
  `sources` / `token` / `error` / `done`.
- **Historial en el cliente** (`history[]`), se reenvía completo en cada turno (server stateless).
- **Tema del sitio en vivo**: `<link href="https://alexisalulema.com/demo-theme.css">`; estilos con
  `var(--token, fallback)` → **degradación elegante** si el tema no carga (no se hardcodea la paleta).
  **Dark por defecto + light por `prefers-color-scheme`**; toggle propio con `data-theme` en `<html>`
  (localStorage; los demos no comparten el toggle del sitio).
- **Citas** bajo cada respuesta (título enlazado a `alexisalulema.com/blog/…` + badge de idioma).
- **UX de rehúso/cierre**: sin `sources` no se muestra bloque de citas; si el stream se corta antes de
  `done` (teardown/expiración de sesión) → aviso elegante y re-habilita el input.
- `app/main.py`: sirve `index.html` en `/` (reemplaza el placeholder) + monta `/static`.

### Decisiones
- **Markdown-lite seguro** en el render: se escapa HTML y luego se resaltan `**negrita**` e `code`
  inline (evita XSS; el resto se muestra con `white-space: pre-wrap`).
- **Assets estáticos** vía `StaticFiles` en `/static`; `/` con `FileResponse` (no hornear HTML en
  Python). Servir desde la raíz cumple el contrato del gateway.

### Validación
- ruff + **35 tests** (incluye `/` sirve la UI —tema + composer, sin placeholder— y `/static/*` 200).
- Smoke de serving con TestClient (sin lifespan → sin torch/psycopg): `/`, `/static/app.js`,
  `/static/styles.css`, `/healthz` → 200 con content-types correctos; checks de HTML/JS OK.

### Pendiente (en NUC, con el stack arriba)
- Prueba visual en navegador (`http://localhost:8080`): streaming, citas clicables, tema dark/light,
  rehúso grounded, y corte de stream elegante.

### Siguiente
- **Fase 4 — Contenedores y e2e**: `Dockerfile` (app, hornea embeddings), `Dockerfile.ollama`
  (Qwen), `Dockerfile.db` (postgres+pgvector+dump), `docker-compose` (3 servicios) y e2e en la NUC.

---

## 2026-08-04 — Calibración de `SIMILARITY_THRESHOLD` (harness)

### Contexto
El umbral decide el **rehúso grounded**: la app responde solo si el **top-1** de similitud coseno
supera `SIMILARITY_THRESHOLD` (hoy 0.30, placeholder). Elegirlo bien requiere **datos reales**
(distribución de scores dentro vs fuera del corpus), que dependen del pgvector sembrado + embeddings
(torch) → corre en la NUC.

### Hecho
- `tools/calibrate_threshold.py`: harness reproducible. Batería etiquetada de preguntas —**in-corpus
  EN/ES**, **cross-lingual** y **out-of-corpus**— contra el pgvector sembrado; imprime top-1 por
  pregunta y **recomienda un umbral**.
- Lógica pura `recommend_threshold(in_top1, out_top1)`: si hay **separación limpia** (min_in > max_out)
  → umbral en el hueco (`margin_frac`); si hay **solapamiento** → umbral que maximiza la precisión de
  clasificación (responder in / rehusar out) y reporta los mal clasificados.
- `tests/test_calibrate.py` (5 tests de la lógica pura). Total suite: **40 tests**, ruff limpio.

### Decisiones
- Calibrar sobre **top-1** (no top-k): el rehúso se dispara cuando el mejor chunk cae bajo el umbral
  (si el top-1 no pasa, ninguno pasa → lista vacía → rehúso). Coincide con `Retriever`.
- Harness en `tools/` (no runtime del demo); reusa `app.embeddings`/`app.retrieval`.

### Pendiente (correr en la NUC, con Postgres sembrado + venv)
- `python -m tools.calibrate_threshold` → pegar salida. Con el umbral recomendado, actualizar el
  default en `app/config.py` y `.env.example`, y anotar el valor + evidencia aquí.

### Siguiente
- Fijar el umbral con los datos de la NUC → luego **Fase 4** (contenedores + e2e).
