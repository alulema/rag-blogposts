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
### Resultado (NUC, corpus de 178 chunks) — 2026-08-12
`python -m tools.calibrate_threshold --json`:
```json
{ "threshold": 0.321, "separated": true, "in_min": 0.4379, "out_max": 0.2047,
  "gap": 0.2332, "misclassified_in": [], "misclassified_out": [] }
```
- **Separación limpia** (gap ≈ 0.233): in-corpus min ≈ **0.438** vs out-of-corpus max ≈ **0.205**;
  **0 mal clasificados** en ambos grupos (incl. cross-lingual).
- **Decisión:** `SIMILARITY_THRESHOLD = 0.32` (redondeo legible del 0.321, al medio del hueco
  0.205–0.438 → ~0.11 de margen a cada lado: robusto sin ser frágil). Fijado en `app/config.py`
  y `.env.example`; test de default actualizado.

### Siguiente
- **Fase 4** (contenedores + docker-compose + e2e en la NUC).

---

## 2026-08-12 — Fase 4 (contenedores + docker-compose)

### Hecho
- **`Dockerfile`** (app): `python:3.13-slim`; **torch CPU-only** (índice `download.pytorch.org/whl/cpu`
  → imagen mucho más liviana), deps, y **modelo de embeddings horneado** en build-time; runtime
  **OFFLINE** (`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`). COPY selectivo (`app/` + `db/schema.sql`;
  **no** `dump.sql`). `libgomp1` para torch.
- **`Dockerfile.ollama`**: base `ollama/ollama` con **Qwen horneado** (`ollama serve &` → espera →
  `ollama pull`); `OLLAMA_HOST=0.0.0.0:11434` para que `app` lo alcance.
- **`db/Dockerfile.db`**: `pgvector/pgvector:pg16` + `dump.sql` en `/docker-entrypoint-initdb.d`
  (siembra al primer init; contenedor efímero sin volumen → re-siembra siempre).
- **`docker-compose.yml`**: 3 servicios con **healthchecks** (db `pg_isready`, ollama `ollama list`,
  app `/healthz`) y **orden de arranque** (`app` depends_on db+ollama `service_healthy`). Solo
  publica **8080** (db/ollama internos → no chocan con los sueltos de la NUC).
- **`.dockerignore`**: excluye `.venv`/tests/tools/caches/docs; conserva `app/` y `db/*.sql`.
- **Resiliencia de arranque** (`app/main.py`): `_wait_for_db` reintenta la conexión a Postgres antes
  de crear el pool/schema → tolera que los 3 contenedores arranquen a la vez (ACA) o que el seed de
  la DB aún no termine. `DB_WAIT_RETRIES` por env.

### Decisiones
- **Imágenes GHCR nombradas** `ghcr.io/alulema/rag-demo-{app,ollama,db}:latest` (etiqueta puesta en
  compose; el push a GHCR es Fase 5).
- **Credenciales `rag/rag`** en la imagen db: no son secreto (DB efímera interna, datos públicos);
  coinciden con `DB_DSN` por defecto.
- Torch **CPU-only** explícito: cumple "sin GPU" y reduce el tamaño de imagen drásticamente.

### Validación (autoría)
- ruff + **42 tests** (nuevos: `test_startup.py` para `_wait_for_db`, con `psycopg` falso inyectado).
- `docker-compose.yml` parseado (estructura: 3 servicios, depends_on healthy, healthchecks, solo 8080).
- **Build/e2e reales NO se corren aquí** (Docker vive en la NUC, por el split de entorno acordado).

### Pendiente (en la NUC)
- `docker compose up -d --build` → validar e2e en `http://localhost:8080` + medir arranque en frío.
  Requiere `db/dump.sql` (ya generado).

### ✅ e2e con contenedores VERDE (NUC) — 2026-08-12
- `docker compose ps`: **los 3 contenedores `healthy`** (app :8080, db, ollama) → build de las 3
  imágenes OK, healthchecks OK, `_wait_for_db`/schema/embedder OK dentro del contenedor.
- `curl POST /chat` ("What are activation functions?"): **`event: sources`** con las 2 citas
  correctas (EN + ES) → **`event: token`** en streaming. Flujo RAG completo **dentro de los 3
  contenedores**, self-contained (embeddings + Qwen + corpus horneados). **Fase 4 cerrada.**
- Nota: el primer intento falló por un typo del comando (`"messages">` en vez de `":"`, el `>` del
  prompt de continuación de bash) — la app respondió con validación JSON correcta (no era bug).

### Siguiente
- **Fase 5 — CI/GHCR**: workflows de build+push de las 3 imágenes (públicas) + `refresh-corpus.yml`.

---

## 2026-08-12 — Fase 5 (CI/GHCR)

### Decisión (dueño no disponible → seguí `CLAUDE.md`)
`db/dump.sql` se **commitea** al repo; el build hornea el dump commiteado (rápido, sin torch),
y `refresh-corpus.yml` es quien lo **regenera + commitea + rebuild/push** de la imagen `db`. Es
exactamente lo que dice `CLAUDE.md` ("commitea snapshot + dump") y coincide con el `.gitignore`
(dump.sql NO ignorado).

### Hecho
- **`.github/workflows/build-images.yml`** (push a `main` + `workflow_dispatch`): matrix
  `[app, ollama, db]` → build+push a `ghcr.io/<owner>/rag-demo-*:{latest,sha}`. Login con
  `GITHUB_TOKEN` (`packages: write`), buildx + caché gha por servicio, paso de "free disk space"
  (torch/Qwen son grandes), `concurrency` con cancel-in-progress.
- **`.github/workflows/refresh-corpus.yml`** (`workflow_dispatch`, `schedule` comentado): setup
  Python 3.13 → `requirements-ingest.txt` → `python -m ingest.run` → commit de `dump.sql`+`snapshot`
  si cambiaron (`git status --porcelain`, con trailer Co-authored-by) → rebuild+push de la imagen
  `db`. Pasos condicionados a `steps.commit.outputs.changed`.

### Notas / decisiones
- Imágenes con `ghcr.io/${{ github.repository_owner }}/rag-demo-*` (owner=alulema, lowercase).
- Pushes con `GITHUB_TOKEN` **no** disparan otros workflows → refresh-corpus rebuildea la imagen
  `db` él mismo (sin bucles), consistente con el diseño.
- **Bootstrap pendiente:** `db/dump.sql` **aún no está commiteado** → el job `db` de build-images
  fallará hasta commitear el dump (generado en la NUC) o correr `refresh-corpus` una vez.

### Validación (autoría)
- Ambos YAML parseados (triggers, permisos, matrix, pasos). ruff + 42 tests siguen verdes (sin
  cambios de código). **Los runs reales corren en GitHub Actions** (no aquí).

### Pendiente (dueño)
- Commitear `db/dump.sql` (+ `snapshot.jsonl`) generado en la NUC.
- Merge a `main` → primer run de `build-images` → marcar los 3 packages **Public** en GHCR.

### Siguiente
- **Fase 6 — Hand-off**: manifest para la infra + `README` final + comandos git.

---

## 2026-08-12 — Modelo de freshness del corpus (decisión)

**Pregunta del dueño:** ¿regenerar `dump.sql` en cada deploy a Azure (para captar posts nuevos)?

**Decisión: NO regenerar en provisión/deploy.** Rompería pilares del proyecto:
- **Arranque rápido / teardown abrupto** (sesión ~20 min): re-ingerir + embeddings (torch) en cada
  provisión gastaría minutos del ciclo de vida del demo.
- **Self-contained / sin llamadas externas en prod**: la ingesta trae posts de `alexisalulema.com`
  → es actividad **build-time**, no runtime. Regenerar en provisión = llamadas externas en vivo.
- **Non-goal explícito** (`CLAUDE.md`): "sin reindex en runtime (corpus fijo por imagen)".
- Fiabilidad/costo: si el sitio cambia o está caído en provisión, el demo se rompería.

**Modelo correcto (2 niveles):** el corpus se refresca al **construir la imagen**, no al desplegarla.
1. **Periódico (hecho):** activé el `schedule` semanal en `refresh-corpus.yml` → re-indexa y
   republica la imagen `db`; el **próximo demo provisionado** usa el corpus fresco. Tunable + dispatch manual.
2. **Event-driven (pendiente, requiere infra):** que el pipeline de publicación del sitio dispare
   `refresh-corpus` (p.ej. `repository_dispatch`) al publicar un post → freshness exacta. Necesita
   coordinación con `personal-website` (relay).

**Preguntas abiertas para la infra (`personal-website`, vía relay):**
- ¿La provisión **siempre** hace pull de `ghcr.io/alulema/rag-demo-db:latest` (fresco), o pinea/cachea
  un digest? (determina si la imagen recién republicada llega sola a los nuevos demos).
- ¿Puede el flujo de publicación del sitio disparar `refresh-corpus` vía `repository_dispatch`
  (+ token)? → freshness event-driven en vez de polling semanal.
- (Las respuestas de alcance general se capturan en `DEMO_INTEGRATION.md`.)

### Resolución (relay respondido) — 2026-08-12
La infra confirmó: **(1)** provisión siempre jala `:latest` fresco (RG+revisión nuevos = pull nuevo)
→ imagen republicada llega sola al próximo demo, cero acción; demos en vuelo no cambian. **(2)**
`repository_dispatch` (Opción A) viable; me pasaron su workflow turnkey. Respuestas capturadas en
`DEMO_INTEGRATION.md` (§Notas capturadas del relay).
- **Cableé mi lado:** `refresh-corpus.yml` ahora escucha `repository_dispatch: types:[refresh-corpus]`
  (+ `schedule` semanal como red de seguridad), `concurrency` con `cancel-in-progress: true` (debounce)
  y un paso "Log trigger" (event/source/commit del `client_payload`).
- **Insight de timing (avisado a la infra):** ingerimos del **sitemap público en vivo** → el dispatch
  debe salir **tras** el deploy del sitio (si no, no-op). Drafts se auto-excluyen (no están en el sitio).
- **Pendiente del dueño (acción manual):** mintar un **fine-grained PAT** scoped a `alulema/rag-blogposts`
  (**Contents: R/W**) y pasárselo a Alexis como secret `RAG_DISPATCH_TOKEN` en `personal-website`.
- **Decisión client_payload:** ping "rebuild-all" (el pipeline re-ingiere todo el sitemap; incremental
  no aporta para 34 posts) + `source`/`commit` para trazabilidad.

### Aclaración: ¿dónde corre el schedule/CI? (no en el demo)
Confusión común entre dos capas homónimas:
- **Repo `alulema/rag-blogposts` (GitHub):** siempre existe en github.com; sus **GitHub Actions**
  (schedule / repository_dispatch / workflow_dispatch) corren en **runners de GitHub**,
  independientes de si hay un demo provisionado. Aquí se (re)construye y publica la imagen `db` a GHCR.
- **Demo provisionado (Azure Container App):** efímero ~20 min; solo **consume** la imagen ya
  horneada de GHCR. No corre CI ni ingesta.
→ El `schedule` semanal lo corre **rag-blogposts en GitHub Actions**, NO el demo ni personal-website.
Mantener `refresh-corpus` en este repo es correcto (separación de concerns): personal-website solo
**notifica** (dispatch). Con el event-driven cableado, el schedule queda como **red de seguridad**.
- **Caveat GitHub:** los workflows con `schedule` se **auto-desactivan tras 60 días sin actividad**
  del repo (público). Los dispatches al publicar posts cuentan como actividad; si el corpus no
  cambia en 60 días, reactivar es un clic (o un keepalive).

---

## 2026-08-13 — Fix: `refresh-corpus` fallaba en CI (dep faltante) + bumps de acciones

**Test e2e de la infra (¡el trigger funciona!):** al mergear a `main`, personal-website mandó el
`repository_dispatch(refresh-corpus)` y disparó nuestro workflow (run real, event=`repository_dispatch`)
→ **token `RAG_DISPATCH_TOKEN` y wiring confirmados end-to-end.** El camino event-driven está vivo.

**Bug encontrado por ese run:** el paso *Re-ingest corpus* falló con
`ModuleNotFoundError: No module named 'pydantic_settings'`.
- **Causa raíz:** `ingest/run.py` importa `app.config` (reutiliza chunk size / embed model / DSN),
  que usa `pydantic-settings`. Ese paquete estaba solo en `requirements.txt` (runtime), **no en
  `requirements-ingest.txt`** — y `refresh-corpus.yml` instala solo este último. Local pasaba
  desapercibido porque el venv tenía ambos (gap "funciona en mi máquina").
- **Fix:** añadí `pydantic-settings>=2.3` a `requirements-ingest.txt` (mismo pin, con comentario del
  porqué). **Validado** con venv aislado: instalando SOLO `pydantic-settings`, `from app.config
  import get_settings` importa limpio (era la única dep externa que faltaba).
- **Bonus (hygiene, no bloqueaba):** bump `actions/checkout@v4→v5` y `actions/setup-python@v5→v6`
  en ambos workflows (Node20 deprecado → Node24), como sugirió la infra. YAML re-validado.
- Suite: ruff + **42 tests** verdes.

**Re-test (dueño):** Actions → *Refresh corpus* → **Run workflow** (dispatch manual; NO "Re-run jobs"
del run viejo). Esperado PASS; probable "corpus sin cambios → nada que commitear" (el dump ya se
horneó en `f3917c9`), lo cual es correcto: prueba el pipeline limpio de punta a punta.

---

## 2026-08-14 — Fase 6 (hand-off) + verificación de readiness para provisión

**Infra confirmó que completó su lado** → se procede a provisionar el demo en un subdominio.
Verifiqué el estado real antes del hand-off:
- `origin/main` head = `da5ab5e chore(corpus): refresca dump.sql + snapshot` → **el bot de
  `refresh-corpus` corrió VERDE** (hotfix #12 funcionó; re-ingirió y commiteó). Pipeline e2e vivo.
- **Las 3 imágenes están PÚBLICAS y jalables en GHCR** (verificado con token anónimo → HTTP 200 en
  `rag-demo-{app,ollama,db}:latest`). Sin credenciales, justo lo que la infra necesita.
- Nada bloqueante del lado del código/imágenes.

**Entregable:** `HANDOFF.md` — manifest completo para la infra:
- Tabla manifest (projectId `rag-demo`, 3 imágenes públicas, puerto 8080 interno sin auth,
  shareable true, secretos ninguno, SSE, sidecars, `/healthz`).
- **Dato crítico de provisión:** en **ACA multi-contenedor los 3 comparten `localhost`** → la app
  usa sus **defaults** (`localhost:5432` / `localhost:11434`), **cero env overrides**. Los
  `environment:` del `docker-compose.yml` (nombres de servicio `db`/`ollama`) son SOLO de Compose;
  no aplican en ACA. (Punto fácil de confundir → lo dejé explícito.)
- Recursos sugeridos (~3.5 vCPU / ~6 GiB; Qwen es el que más pesa), arranque/health/cold-start,
  teardown, freshness, overrides opcionales, y checklist de provisión.

**Estado del proyecto:** Fases 0–6 ✅. Del lado de rag-blogposts, **listo para provisionar**.
Pendientes = acciones de la infra (registrar `rag-demo` con las 3 imágenes y enrutar a `app:8080`).

### Nota de proceso — recuperación de un enredo de git (CRLF)
El commit de Fase 6 inicial (`2e7d1c6`) capturó solo `HANDOFF.md`; las ediciones de `Devlog.md` y
`README.md` quedaron atrapadas en un `git stash` (el `stash pop` falló por conflicto CRLF de
`db/dump.sql`). Se recuperaron re-aplicándolas. **Causa raíz recurrente:** git de Windows
(`core.autocrlf=true`) vs git de WSL sobre el mismo working tree `/mnt/c` → phantoms de line-ending.
**Fix recomendado:** `.gitattributes` (`* text=auto eol=lf`) + `core.autocrlf false` en Windows.

---

## 2026-08-15 — Optimización de performance (feedback de la infra)

El demo provisionado corre pero **lento**: Qwen 1.5B en CPU, 1 stream por usuario. La infra ya
sesgó el CPU hacia `ollama` (1.5 de 2 vCPU) y confirmó que el cap de **ACA Consumption = 2 vCPU /
4 GiB** (no escala más; horizontal no ayuda porque es latencia de un solo stream en CPU). **Los
levers efectivos son de mi lado (imagen/app).** Aplicados:

1. **Modelo más chico = el win grande:** default `qwen2.5:1.5b-instruct` → **`qwen2.5:0.5b-instruct`**
   (verificado en el registry de Ollama). En CPU la velocidad de tokens escala ~inverso al tamaño →
   **~3× más rápido**. Horneado vía `ARG LLM_MODEL` en `Dockerfile.ollama`; también en
   `docker-compose.yml`, `app/config.py`, `.env.example`. 1.5B/7B siguen disponibles por env.
2. **`MAX_OUTPUT_TOKENS` 512 → 256:** menos tokens = proporcionalmente menos espera.
3. **Streaming token-a-token:** ya implementado (Fase 3, `app.js` con `fetch()`+`ReadableStream`) →
   baja mucho la latencia percibida. Confirmado, sin cambios.
4. `TOP_K` (5) y chunk size sin tocar por ahora (afectan grounding/calidad); quedan como levers
   futuros si hace falta acortar el prefill.

- **HANDOFF.md** actualizado: recursos con 0.5B y **corregido al cap real 2 vCPU / 4 GiB** (antes
  decía ~3.5/6, que excede el plan Consumption); overrides con el nuevo default.
- Validación: ruff + **42 tests**; tag `0.5b-instruct` consistente en los 5 sitios.
- **Decisión (para confirmar):** 0.5B prioriza velocidad sobre calidad; es grounded (contexto dado)
  así que la tarea principal es sintetizar+citar, que 0.5B multilingüe maneja. **Fácilmente
  revertible** a 1.5B (o `1.5b-instruct-q3_K_M`) si la calidad se queda corta — el dueño lo valida
  al ver el demo. `CLAUDE.md` NO se tocó (nombra 1.5B; es doc "fijado" → cambio de default a
  criterio del dueño).

**Siguiente:** republicar `rag-demo-ollama:latest` (build-images) con 0.5B horneado → avisar a la
infra el tag/modelo para que ajuste `LLM_MODEL` en el bicep y re-optimice el split 2/4.

---

## 2026-08-16 — Fix RAG: preguntas "meta" del blog (resumen sintético en la ingesta)

**Síntoma (demo en vivo):** «¿De qué temas habla el blog de Alexis?» → rehúso grounded
(«Solo puedo responder preguntas sobre los posts…»). Pregunta trivial que debería contestarse.

**Causa raíz:** ningún chunk **real** resume el corpus — cada chunk es un fragmento de un post
concreto. Una pregunta meta no se parece lo suficiente a ningún fragmento → todos caen bajo el
umbral `SIMILARITY_THRESHOLD=0.32` → `retrieve()` devuelve `[]` → `main.py` rehúsa sin llamar al
LLM. No es un bug del umbral (bajarlo rompería el grounding), sino una **laguna del corpus**.

**Fix (build-time, como intuyó el dueño):** nuevo `ingest/overview.py` que genera, por idioma
presente, un `Post` **sintético de resumen** cuyo texto enumera los **títulos** de los posts (que
*son* los temas) con encuadre explícito + sinónimos (topics/subjects/areas · temas/asuntos/áreas)
para maximizar recall. Fluye por el pipeline normal (chunk → embed → dump/snapshot), así que se
recupera como cualquier chunk y el LLM responde fundamentado. La **cita** apunta al índice del blog
(`/blog/` o `/es/blog/`, páginas reales). Cableado en `ingest/run.py` tras recolectar los posts.

**Propiedades:**
- **Determinista** (títulos ordenados por fecha desc, dedupe) → no ensucia el diff del
  `refresh-corpus`; solo cambia al añadir/renombrar/eliminar posts (justo cuando debe actualizarse).
- **Bilingüe:** un resumen EN (títulos EN) y uno ES (títulos ES) → responde en el idioma y cita el
  índice correcto. El resumen sintético también entra al `snapshot.jsonl` (consistencia chunk↔fuente).
- **No contamina retrieval específico:** cada título es una oración diluida en el vector del
  resumen; una consulta concreta (p.ej. «activation functions») sigue rankeando más alto los chunks
  reales y densos del post.

**Validación:** ruff limpio + **48 tests** (6 nuevos en `tests/test_overview.py`, sin torch).
Smoke offline: el `Post` sintético trocea a 1 chunk/idioma, orden más-reciente-primero correcto.

**Para publicar al demo (acción del dueño):** regenerar el corpus para que `dump.sql` incluya los
chunks de resumen. Recomendado: (1) validar local en la NUC (`python -m ingest.run` → `docker
compose up` → probar la pregunta meta), luego (2) commit del código + merge a `main`, y (3) un clic
en **refresh-corpus** (`workflow_dispatch`) → regenera `dump.sql` con el resumen → rebuild de
`rag-demo-db:latest` → el próximo demo provisionado ya contesta las preguntas meta.

---

## 2026-08-16 — Perf II: `TOP_K` 5→3 (recorta TTFT; prefill del prompt RAG en CPU)

**Medición de la infra en el nodo real (demo01), 0.5B:** generación ✅ **~25 tok/s** (el ~3× de la
Perf I se cumplió), **pero** el nuevo cuello es el **TTFT ~14–21 s** = *prefill* del prompt RAG en
CPU (confirmado en caliente, con el modelo ya cargado). `ollama` ya está al tope del split de CPU
(1.5/2 vCPU) en ACA Consumption → el lever no es más CPU, sino **prompt más corto**.

**Aplicado (lever primario, solo app/runtime):** `TOP_K` **5 → 3**. El contexto recuperado es la
parte grande y variable del prompt; con 3 chunks (en vez de 5) el prefill baja ~40 % → **TTFT ~½**.
Bajo riesgo: `SIMILARITY_THRESHOLD=0.32` sigue filtrando el grounding, las citas dedupean por URL
(2–3 fuentes basta), y el resumen meta (1 chunk) sigue siendo top-hit. Solo toca `app/config.py`
(default), `.env.example`, `tests/test_config.py`, `HANDOFF.md`. Se publica al reconstruir la
imagen `app` (build-images en push a `main`); la infra usa defaults (no hace falta env override).

**NO bundleado (siguiente lever, si TOP_K no basta): `CHUNK_TOKENS` 600→~400.** Es lado-ingesta:
requiere **re-ingesta** (regenera `dump.sql`) y **recalibrar** el umbral (el 0.32 se calibró a 600
tokens; chunks más chicos cambian la densidad de similitud). Mezclarlo con TOP_K enturbiaría la
atribución del TTFT y cualquier regresión de calidad. Plan si se necesita: bajar `CHUNK_TOKENS` en
`app/config.py` + `.env.example` → `python -m ingest.run` en la NUC → `python -m
tools.calibrate_threshold` para confirmar/ajustar el umbral → `refresh-corpus` (rebuild `db`).

**Sin tocar:** `MAX_OUTPUT_TOKENS=256` y la generación (están bien, dice la infra). `CLAUDE.md` NO
se toca (doc "fijado"; su tabla dice k=5 — cambio de default a criterio del dueño, igual que con el
modelo en Perf I). **Validación:** ruff limpio + **48 tests** (ajustado `test_defaults`).

**Siguiente:** publicar imagen `app` con `TOP_K=3` → avisar a la infra para **re-medir TTFT**; si
sigue alto, activar el lever `CHUNK_TOKENS` con recalibración.

---

## 2026-08-17 — Perf III: `CHUNK_TOKENS` 600→400 (+ recalibración del umbral)

**Medición de la infra con `TOP_K=3` (nodo real, prompts nuevos = usuario real):** **TTFT ~9–11 s**
(prom 10.1), **−40 %** desde ~17.6 s con `TOP_K=5`, y consistente. Generación ~28 tok/s ✅. (Nota:
repetir la MISMA pregunta da ~1 s por el KV cache de ollama; el número real se mide con preguntas
nuevas/frías.) ~10 s aún se siente lento → la infra pidió activar **Perf III**.

**Aplicado (lado ingesta):** `CHUNK_TOKENS` **600 → 400**. Menos tokens por chunk → con `TOP_K=3`
el prompt baja de ~1800 a ~1200 tokens → **TTFT estimado ~6–7 s**. Toca `app/config.py` (default) y
`.env.example`. `CHUNK_OVERLAP` se deja en 80 (una sola variable de ingesta cambia → medición limpia).

**Recalibración del umbral (obligatoria, no bundleable en autoría):** el `SIMILARITY_THRESHOLD=0.32`
se calibró a 600 tokens; chunks más chicos cambian la densidad de similitud (in-corpus tiende a
*subir* al estar más focalizado). El valor óptimo depende de los embeddings del corpus re-troceado,
que **solo se generan en la NUC** (torch). Flujo: re-ingesta a 400 → sembrar pgvector local →
`python -m tools.calibrate_threshold --json` (top-1, independiente de `TOP_K`) → fija el umbral que
imprime (`separated:true` → punto medio del hueco; `separated:false` → hay solape, **no publicar**,
revisar). Hasta esa medición dejo `0.32` como default seguro (sigue en medio del hueco de 600).

**Sin tocar:** generación / `MAX_OUTPUT_TOKENS=256` (ok, dice la infra). `CLAUDE.md` NO se toca (doc
"fijado"; su diseño dice ~600 tokens y k=5 — la divergencia de defaults se acumula: modelo, top-k y
ahora chunk → conviene un commit de *doc-sync* del dueño cuando quiera). **Validación (autoría):**
ruff limpio + **48 tests** (sin asserts de valor sobre `chunk_tokens`).

**Siguiente (dueño, en la NUC):** re-ingesta 400 → recalibrar → commitear `config`+`.env.example`+
`db/dump.sql`+`db/snapshot.jsonl`(+umbral si cambió)+`Devlog` → PR a `main` → refresh-corpus/build
publican `db`+`app` → **pedir demo nuevo a la infra y re-medir TTFT (frío + repetido)**.

**Resultado calibración (2026-08-17, corpus 400-token): separated:true**, in_min=0.425, out_max=0.356,
gap=0.069 → **umbral 0.32→0.39**. A 400 tokens el out_max subió (0.20→0.356) y el hueco se estrechó
(0.23→0.069) vs 600 → grounding con menos margen; si en vivo se cuela algo off-topic, subir umbral o
chunck size.

---

## 2026-08-17 — Handoff a Claude Code (NUC): nota de continuidad

Nota puente para retomar el proyecto desde **Claude Code en la NUC** (u otra instancia/sesión). El
contexto completo vive en este Devlog + `CLAUDE.md` (plan), `DEMO_INTEGRATION.md` (contrato infra) y
`HANDOFF.md` (manifest de provisión). Esto es el resumen operativo.

### Estado actual (desplegado en GHCR)
Cadena de performance **cerrada**: **Perf I** (LLM `qwen2.5:0.5b-instruct`, `MAX_OUTPUT_TOKENS=256`) ·
**Perf II** (`TOP_K=3`; TTFT ~17.6→~10.1 s medido por la infra) · **Perf III** (`CHUNK_TOKENS=400`,
`SIMILARITY_THRESHOLD=0.39`, dump de **278 chunks** 400-token). `build-images` republica
`rag-demo-{app,ollama,db}:latest` en cada merge a `main`. **Pendiente:** la infra provisiona un demo y
re-mide el TTFT (estimado ~6–7 s).

### Convenciones (respetarlas aunque el agente tienda a lo contrario)
- **NUNCA auto-commitear.** Preparar los comandos git para que el dueño los corra (identidad personal).
  Trailer en cada commit: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- Una rama por concern; refactors separados de cambios de comportamiento. Repo público → **sin secretos**.
- Mantener **este Devlog** al día en cada cambio.
- `CLAUDE.md` es doc "fijado": no cambiar stack/modelos sin consultar. Sus defaults ya divergen del código
  (modelo 0.5B, top_k=3, chunk=400) → un commit de *doc-sync* queda a criterio del dueño.

### Topología de máquinas (clave)
- **NUC (Linux nativo):** máquina de **procesamiento** — docker, torch, pgvector, ingesta, embeddings,
  calibración. Deps ya instaladas (venv `rag-ingest` + `psycopg`). Git limpio, **sin CRLF**.
- **Windows/WSL (`/mnt/c`):** clon de autoría/git-gate; sufre **CRLF thrash** (`core.autocrlf=true`) →
  `git status` marca decenas de archivos ` M` sin cambio real (verificar con `git diff --ignore-cr-at-eol`).
  Pendiente opcional: `.gitattributes` (`* text=auto eol=lf`) + `git add --renormalize .` para cerrarlo.

### Recalibrar el umbral (al cambiar chunk / embeddings / corpus)
Sembrar un pgvector desechable con `db/dump.sql` y correr `python -m tools.calibrate_threshold --json`
(top-1, independiente de `TOP_K`). Fijar el `threshold` impreso; si `separated:false`, **no publicar**.
**Ojo:** a 400 tokens el margen de grounding es fino (gap 0.069, out_max 0.356) → vigilar fugas off-topic
en vivo; si aparecen, subir el umbral o el chunk size.

### Gotchas capturados esta sesión
- `ingest.run` y `calibrate_threshold` necesitan `requirements-ingest.txt` **+ `psycopg[binary]`** (este
  último NO está en ese archivo; vive en `requirements.txt`).
- Cambiar `SIMILARITY_THRESHOLD` obliga a actualizar `tests/test_config.py` (`test_defaults` asserta el valor).
- Cambiar el modelo de embeddings ⇒ re-ingesta + re-calibración + revisar el cap de 128 tokens (mean-pooling
  en `ingest/embed.py`).
- El dump/ingesta se generan **en la NUC** (torch); commitear esos artefactos desde ahí. El código puede
  commitearse desde el git-gate (WSL).
- Nit cosmético pendiente: el comentario de `chunk_tokens` en `app/config.py` aún dice "recalibrar umbral".

---

## 2026-08-17 — Perf III medido en vivo: fuga React/Vue, umbral 0.39→0.42

La infra provisionó el demo con Perf III y midió: **TTFT frío ~5.7 s** de media (2.5/6.2/8.3 s),
gen ~30-31 tok/s — cumple el estimado ~6-7 s, baja ~44% vs Perf II. **Perf III se queda.** Pero de
9 preguntas fuera de corpus probadas en vivo, 2 se colaron: `useState`/`useEffect` de React
generaron respuesta real (256 tok) en vez de rehusar. Kubernetes, Vue, Angular, Tailwind, JSX
rehusaron bien en esa prueba. Smoking gun: `useEffect` recuperó un chunk irrelevante de
"Funciones de Activación en TensorFlow" que apenas pasó 0.39.

**Verificación local (NUC, esta sesión):** antes de tocar el umbral, sembré un pgvector desechable
con la imagen `rag-demo-db:latest` real (278 chunks, la misma que probó la infra — hubo que
`docker pull` porque la cache local estaba 2 días vieja) y reproduje el retrieval directo. La
batería `OUT_CORPUS` de `tools/calibrate_threshold.py` no tenía ningún negativo "cercano"
(frameworks frontend ausentes del blog) — solo temas obviamente ajenos (Francia, pizza, Taylor
Swift) — así que la calibración original nunca vio venir esta fuga. Al agregar sondas de
React/Vue/Angular/Tailwind/JSX/Kubernetes:

- **Vue.js composition API sola pega top1=0.492** — por encima de todo el rango 0.42–0.44 que
  pidió la infra; subir ahí no la cierra.
- React `useState`=0.475, `useEffect`=0.458, hooks=0.388, JSX=0.336.
- El piso in-corpus real es la pregunta de **Levenshtein en JavaScript, top1=0.425** — por
  *debajo* de Vue. **No hay separación limpia posible**: es solape real de embeddings a 400
  tokens entre un post JS/algoritmos legítimo y frameworks frontend adyacentes, no un umbral mal
  puesto.

**Nota sobre la recomendación automática del harness:** con la batería endurecida, `calibrate_threshold`
recomienda por accuracy **0.577** (12/14 in-corpus + 15/15 out-corpus correctos) — pero eso rehusaría
"How do transformers work internally?" (0.572), el tema más central del blog. Se descarta esa
recomendación a propósito: maximizar accuracy del harness no es el objetivo si el costo es un tema
core.

**Decisión (dueño):** preservar Levenshtein/JS respondible > cerrar la fuga de frameworks
adyacentes. **`SIMILARITY_THRESHOLD` 0.39→0.42** (aprieta el margen contra negativos no probados
sin refusar ningún tema real del corpus; el piso sigue en 0.425). React/Vue/Angular/Kubernetes
quedan como **fuga conocida y aceptada**, no un bug pendiente. Harness actualizado: `OUT_CORPUS`
en `tools/calibrate_threshold.py` ahora incluye esos negativos "cercanos" para que una futura
recalibración (otro modelo de embeddings, otro chunk size) no repita el punto ciego.

**Siguiente:** republicar (`build-images` en merge a `main`) y pedir a la infra reconfirmar las 2
preguntas de React (documentar la fuga como aceptada, no reabrir) + que las on-topic sigan
respondiendo.

---

## 2026-08-17 — Resumen del blog: de títulos a tags reales + chip de UI

Idea del dueño: sugerir en la UI, desde el arranque del chat, la pregunta "¿cuáles son los temas
que trata el blog de Alexis?" — no solo por descubribilidad, sino como mitigación de producto al
mismo problema que veníamos persiguiendo con umbral/gate léxico (React/Vue): si el chat le muestra
al usuario el alcance real desde el primer segundo, hay menos incentivo a preguntar fuera de tema.

El resumen sintético (`ingest/overview.py`, desde 2026-08-16) respondía esa pregunta enumerando
**títulos** de posts ("Alexis Alulema escribe sobre «DDD Clean Architecture Template»."). Un
título no siempre dice la tecnología (ese post es sobre C#/DDD/CQRS, no lo dice el título). Antes
de inventar extracción de keywords, se inspeccionó el HTML real del sitio: cada post ya trae
`<div class="post-tags"><span class="badge">…</span></div>` — tags curados a mano por el autor al
publicar (`machine-learning`, `python`, `transformers`, `c#`, `cqrs`, `ddd`...), que
`ingest/clean.py` nunca scrapeaba. Es mejor fuente que cualquier heurística: metadata real, no
inferida.

**Cambios:**
- `ingest/clean.py`: `Post` gana `tags: tuple[str, ...]`, scrapeado de `.post-tags .badge` (fuera
  de `.post-content`, no contamina el cuerpo del chunk).
- `ingest/overview.py`: el resumen ahora enumera el **set de tags únicos** por idioma (orden
  alfabético — determinista, no depende de fechas ni del orden de fetch) en vez de títulos. Un
  post sin tags simplemente no aporta; si un idioma no tiene ningún tag, no se genera resumen para
  ese idioma (mismo fallback que antes).
- Re-ingesta real (NUC, 34 posts): confirma que **todo** el corpus actual trae tags. `dump.sql`
  regenerado — diff mínimo: solo las 3 líneas del resumen cambian, los 275 chunks reales quedan
  byte-idénticos (embeddings determinísticos, nada más tocó su contenido).
- Validado contra pgvector real: "¿Cuáles son los temas que trata el blog de Alexis?" recupera el
  resumen con top1=0.694 (holgado sobre el umbral 0.42); variantes EN también pasan (0.446-0.465).
  Recalibración completa (`tools/calibrate_threshold.py`, batería endurecida) da los mismos
  números que antes (in_min=0.425, out_max=0.492) — el cambio no afecta el resto del corpus.
- `app/static/index.html`: nuevo chip de sugerencia ("What topics does this blog cover?", en
  inglés — la formulación que se validó contra pgvector, top1=0.465), primero en la lista;
  se retira el chip de asyncio para dejar espacio. Sin cambios en `app.js` (el handler de `.chip`
  ya es genérico).
- Tests: `tests/test_clean.py` (tags extraídos, lowercased, fuera del cuerpo, ausentes sin
  romper) y `tests/test_overview.py` reescrito para tags (alfabético, dedupe case-insensitive,
  posts sin tags no aportan, fallback sin resumen si no hay tags). 53 tests + ruff limpios.

---

## 2026-08-19 — "No hay memoria": el bug real era el retrieval, no el historial

**Reporte del dueño:** probando el chat a mano, los follow-ups ("¿y en Python?") se sienten sin
memoria — pide agregar una ventana de contexto de ~5 turnos.

**Diagnóstico:** el historial **ya existía** end-to-end y sin capar — `app.js` lo mantiene
client-side y lo reenvía completo (`history[]`), `main.chat` lo pasa a `rag.build_messages`, que
arma `system + historial + pregunta` para Ollama (esto es justo lo que dice `CLAUDE.md` §Flujo
RAG). El bug no estaba ahí. Estaba en `Retriever.retrieve`: embebe **solo** la última pregunta,
sin historial. Un follow-up dependiente de contexto por sí solo no trae señal suficiente para
pasar `SIMILARITY_THRESHOLD=0.42`, así que `chunks` sale vacío — y `main.chat` rehúsa con el
mensaje enlatado **sin llamar al LLM en absoluto**, ignorando que el historial sí traía el
contexto necesario. De ahí la sensación de "no memoria": no es que el LLM lo olvide, es que el
retrieval nunca le da la oportunidad de usarlo.

**Fix (dos cambios independientes, cada uno resuelve una mitad del reporte):**
1. **Ventana de contexto real** (lo que pidió el dueño): `app.js` acota `history[]` a las
   últimas `MAX_HISTORY_TURNS=5` vueltas (`trimHistory()`, tras cada push). Antes crecía sin
   límite durante toda la sesión — con sesiones de hasta ~20 min eso engordaba el prompt (y el
   TTFT, ya ajustado con lupa en Perf II/III) sin necesidad real.
2. **Retrieval retry con contexto** (el bug de fondo): `rag.contextualize_query(question,
   history)` antepone el último turno de *usuario* del historial a la pregunta, solo para el
   embed de retrieval — nunca se le manda así al LLM (`build_messages` sigue usando el
   historial real, turno a turno). `main.chat` lo usa como **fallback**: si el retrieval con la
   pregunta sola sale vacío y hay historial, reintenta una vez con la query contextualizada
   antes de rehusar. El caso normal (primera pregunta, o pregunta ya autocontenida) no cambia —
   sigue exactamente igual al `Retriever.retrieve(question)` de siempre, así que no debería
   tocar la calibración de `SIMILARITY_THRESHOLD` para ese camino.
- **Riesgo conocido, no cerrado:** el camino de fallback sí cambia el vector embebido (pregunta
  anterior + actual concatenadas) frente al que se usó para calibrar el umbral
  (`tools/calibrate_threshold.py`, preguntas sueltas). No se re-corrió la calibración con pares
  concatenados — el fallback solo dispara cuando la pregunta sola ya fue rechazada, así que el
  peor caso es "sigue rehusando" (no regresión), pero si en producción se ve que el fallback
  nunca gana in situaciones donde debería, vale la pena calibrar aparte ese camino.
- Tests: `tests/test_rag.py` (`contextualize_query`: antepone el turno de usuario más reciente,
  salta roles que no son `user`, no cambia nada sin historial) y `tests/test_api.py`
  (`_FakeContextualRetriever` — verifica que `main.chat` reintenta con la query contextualizada
  y que, si tampoco encuentra nada, rehúsa igual sin loops). 61 tests + ruff limpios.

---

## 2026-08-20 — Dos bugs de la primera prueba real (reporte de Verito)

**Reporte:** Verito (hermana del dueño) probó el demo en vivo. Dos síntomas en la misma sesión:
1. `"Hola"` → rehúso en **inglés** ("I can only answer questions about...").
2. `"Quien es Alexis?"` → empezó a responder ("Alexis Alulema es") y el stream se **cortó**
   ("Conexión interrumpida (la sesión del demo pudo expirar)"). No volvió a intentar.

### Bug 1 — `detect_lang` sin señal para saludos sin tilde (confirmado y arreglado)
`"hola"` no está en `_ES_WORDS` ni `_EN_WORDS` → empate 0-0 → cae al default `"en"`. Mismo problema
con `"Gracias"`, `"Buenas"`, `"Adiós"` (sin tilde) escritos solos, sin ningún carácter que dispare
`_ES_CHARS`. **Fix:** se agregaron saludos/muletillas comunes a `_ES_WORDS` (hola, buenas, buenos,
tardes, noches, gracias, adios, saludos, ayuda, oye, disculpa) y equivalentes EN a `_EN_WORDS`
(hello, hi, hey, thanks, please) — no cambia el default (`"en"` en empate real), solo añade señal
para los casos comunes que antes empataban en 0. Test: `tests/test_rag.py::
test_detect_lang_greeting_without_accents`.

### Bug 2 — hipótesis: primera inferencia real paga la carga en frío del modelo
`/healthz` (`app/main.py`) esperaba a Postgres pero **no a que Ollama tuviera el modelo cargado en
RAM**. El healthcheck de `docker-compose.yml` (`ollama list`) solo confirma que el server responde;
Ollama carga los pesos de forma **perezosa en la primera llamada de inferencia** — el rehúso de
`"Hola"` no cuenta (responde sin llamar al LLM), así que `"Quien es Alexis?"` fue probablemente la
**primera** llamada real a Ollama en ese contenedor recién provisionado. Esa carga (varios segundos,
no reflejados en los TTFT "calientes" medidos por la infra, que reutilizó la misma sesión para 9
preguntas) se sumó al streaming y el gateway cortó por su propio timeout antes de terminar. No
confirmado con logs de la infra (hipótesis razonada desde el código), pero coincide exactamente con
el síntoma: tokens sí llegaron a salir ("Alexis Alulema es") antes del corte.

**Fix (mitigación, en este repo, sin coordinar con la infra):** `app/main.py` gana
`_warm_up_llm(host, model, retries, delay)` en el `lifespan` — dispara un `POST /api/generate` **sin
prompt** (patrón documentado por Ollama para precargar el modelo sin generar texto) con reintentos,
**antes** de que `/healthz` reporte OK. Así el primer usuario real ya no paga la carga en frío: si
`/healthz` es el gate de tráfico (como dice `HANDOFF.md`), el gateway no enruta hasta que Ollama esté
tibio. Tests con `httpx.AsyncClient` falso (reintentos y agotamiento), simétricos a
`test_wait_for_db_*`. **Costo:** el arranque del contenedor tarda unos segundos más (antes de
reportar healthy) — aceptable, mejor que fallar el primer mensaje de un visitante real.

**Validación (autoría):** ruff limpio + **64 tests**. **Pendiente (NUC/demo real):** confirmar que
el arranque en frío no se alarga demasiado con el warm-up incluido, y reconfirmar con la infra si
`/healthz` efectivamente gatea el tráfico entrante (si no, este fix no cierra el síntoma del todo y
haría falta coordinar un timeout de sesión más generoso del lado del gateway).

**Para publicar:** merge a `main` → `build-images` republica `rag-demo-app:latest` → el próximo demo
provisionado ya lleva ambos fixes.

---

## 2026-08-20 — Respuesta amigable a saludos puros

**Idea del dueño:** cuando alguien saluda ("Hola", "Hi"), en lugar de devolver el rechazo enlatado,
el bot debería presentarse y explicar qué puede hacer (mitigación de UX: el usuario entiende el
alcance desde el primer segundo, menos incentivo a preguntas fuera de tema).

**Implementación (puro):**
- `app.rag.is_greeting(text)` → detecta si el texto es **solo palabras de saludo** (sin pregunta
  de fondo). Diferencia "Hola" de "Hola, ¿qué puedes hacer?" o "Hola, ¿cómo funcionan los
  transformadores?". Heurística: palabras extraídas ⊆ {hola, hi, hey, buenas, buenos, ...}.
- `app.rag.greeting_response(lang)` → mensaje de bienvenida bilingüe que presenta el bot, sus
  temas y sugiere preguntas de muestra (p.ej. "¿De qué temas habla el blog?" o "¿Cómo funcionan
  los transformadores?").
- `app.main.chat()` → early-exit si `is_greeting(question)` es True: devuelve el mensaje de
  bienvenida **sin retrieval ni LLM**, directo por SSE (rápido, cero latencia, cero costo).

**Tests (5 nuevos):**
- `tests/test_rag.py`: `test_is_greeting` (casos positivos/negativos), `test_greeting_response`
  (ambos idiomas).
- `tests/test_api.py`: `test_chat_greeting_returns_welcome_message` y `test_chat_greeting_en`
  (verifican que el endpoint devuelve bienvenida sin invocar retriever/ollama).

**Validación:** ruff limpio + **67 tests**. Pendiente (NUC): probar en vivo que "Hola" devuelve
bienvenida amigable.

---

## 2026-08-20 — Redirección amable en vez del rehúso enlatado (Opción B, con LLM)

**Reporte del dueño:** preguntó "¿Qué temas conoces?" (formulación distinta al chip sugerido) y
recibió el mismo mensaje enlatado de siempre — se siente robótico, la misma frase sin importar la
pregunta. Propuso mejorar el "sin contexto" con una respuesta amable que invite a preguntar algo
respondible, en vez de solo rehusar.

**Dos opciones evaluadas con el dueño:**
- **A (determinística, sin LLM):** plantilla rellenada con temas fijos. Cero latencia, pero sigue
  siendo un template, no tan conversacional.
- **B (con LLM, elegida):** llamar a Ollama con un system prompt distinto que reconozca la
  limitación honestamente y sugiera temas reales — más natural, a costa de latencia adicional en
  el camino "sin contexto" (antes instantáneo, sin LLM).

**Implementación (Opción B):**
- `app.rag._no_context_system_prompt(lang)`: prompt bilingüe que instruye al LLM a (1) NO usar
  conocimiento externo para responder la pregunta original, (2) decir amablemente que no tiene esa
  info en el blog, (3) invitar a 2-3 temas reales concretos (lista `_BLOG_TOPICS`: RAG, Python,
  asyncio, transformers, TensorFlow, embeddings), (4) ser cálido y conciso (2-3 frases).
- `app.rag.build_no_context_messages(question, history, lang)`: mismo *shape* que `build_messages`
  (system + historial + pregunta) pero sin chunks — el LLM ve la conversación completa igual que
  en el camino grounded.
- `app.rag.NO_CONTEXT_MAX_TOKENS = 100`: la redirección es corta: no necesita el presupuesto
  completo (`MAX_OUTPUT_TOKENS=256`) que sí necesita una respuesta de contenido real. Mantiene el
  camino "sin contexto" — el más común en preguntas fuera de tema — con la latencia más baja
  posible dado que ahora sí pasa por el LLM.
- `app.ollama_client.OllamaClient.stream_chat()`: gana `max_tokens: int | None = None` opcional
  para poder pasar ese presupuesto reducido sin tocar el default de la instancia.
- `app.main.chat()`: el `event_stream()` se **unificó** — ya no hay una rama "sin LLM"; siempre
  llama a Ollama, solo cambia cómo se arman los mensajes (`build_messages` con chunks vs.
  `build_no_context_messages` sin ellos) y el `max_tokens` pasado.
- `_REFUSAL`/`refusal_message` (el rehúso enlatado) **se mantienen** en `app.rag` — ya no se usan
  en `main.py`, pero quedan como pieza pura testeada, disponible como fallback futuro si se
  necesita degradar sin LLM (p.ej. si el warm-up de Ollama falla).

**Tradeoff aceptado (hablado con el dueño):** el camino "sin contexto" antes era instantáneo (sin
LLM); ahora paga latencia real incluso para preguntas totalmente fuera de tema. Con
`NO_CONTEXT_MAX_TOKENS=100` (vs. 256 del camino grounded) y el warm-up de Ollama de la sesión
anterior, debería seguir sintiéndose rápido, pero **no se ha medido en vivo** — pendiente en la
NUC antes de publicar.

**Tests (6 nuevos):**
- `tests/test_rag.py`: `test_build_no_context_messages_structure` (no incluye "Context:" ni el
  rehúso enlatado literal, preserva historial) y `test_build_no_context_messages_prompt_mentions_
  real_topics_by_lang` (temas reales por idioma, prompt distinto ES/EN).
- `tests/test_api.py`: `_FakeOllama` ahora registra `(messages, max_tokens)` por llamada.
  `test_chat_no_context_gets_friendly_llm_redirect_not_canned_refusal` (reemplaza el test viejo de
  rehúso: verifica que SÍ se llama al LLM, con el system prompt de redirección y
  `max_tokens=NO_CONTEXT_MAX_TOKENS`) y `test_chat_followup_without_context_match_gets_friendly_
  llm_redirect` (mismo caso pero tras el retry de contexto fallido — un solo intento de
  generación, sin loops).

**Validación:** ruff limpio + **73 tests**. **Pendiente (NUC):** medir latencia real del camino
"sin contexto" ahora que pasa por el LLM, y probar a mano que la redirección se siente natural
(no repetitiva) con preguntas variadas fuera de tema.

---

## 2026-08-20 — Opción B revertida: el LLM 0.5B ignora "no uses conocimiento externo" (probado en vivo)

**Antes de mergear a `main`**, se levantó el stack completo con `docker compose up --build` (app +
ollama + db, en esta máquina — Docker/Postgres disponibles aquí) para probar a mano las dos ramas
pendientes (`fix/detect-lang-greeting-llm-warmup` y `feat/greeting-response`). Primer resultado
bueno: **el warm-up de Ollama de la sesión anterior funciona** — log confirmado, `POST
/api/generate` cargó el modelo (1.06 s) **antes** de que `/healthz` reportara `ok`.

**Pero la Opción B (redirección con LLM) falló en vivo, de forma reproducible y seria:**

| Pregunta (fuera de corpus, `SOURCES: []`) | Respuesta del LLM |
|---|---|
| "¿Cuál es la capital de Francia?" | **"La capital de Francia es París."** |
| "¿Cuál es la mejor pizza del mundo?" | Inventó una respuesta sobre "Pizzas al Loto" |
| "¿Quién ganó el mundial 2022?" | **"...ganó Brasil"** (ganó Argentina — dato real, incorrecto) |

El `_no_context_system_prompt` le decía explícitamente "NO uses conocimiento externo para
intentar responder la pregunta original", pero **Qwen2.5-0.5B ignora instrucciones negativas**
cuando la pregunta le resulta "conocida" — un problema documentado de modelos instruct pequeños
(malos siguiendo restricciones tipo "no hagas X", especialmente ante preguntas directas). El
resultado es **peor que el rehúso enlatado que se quería mejorar**: antes el bot nunca alucinaba
fuera de tema; con Opción B, sí — y a veces con datos falsos presentados con confianza. Esto
**rompe grounded-only**, una restricción dura del proyecto (`CLAUDE.md`).

*(Nota aparte, sin relación con Opción B: "¿Cómo funciona React?" cayó en la fuga conocida de
React/Vue del umbral — documentada y aceptada desde el 2026-08-17, no es un hallazgo nuevo.)*

**Decisión (con el dueño, tres opciones evaluadas):** revertir a una versión mejorada de la
Opción A — determinística, sin LLM, pero más amable que el rehúso original. Se descartaron (1)
Opción B con red de seguridad post-hoc (heurística, no elimina el riesgo del todo) y (2) probar
con un modelo más grande solo para este camino (más latencia + segundo modelo horneado — cambio
de arquitectura mayor para un problema que la Opción A resuelve sin riesgo).

**Revert aplicado:**
- `app.rag.no_context_response(lang)` reemplaza el intento con LLM: mensaje determinístico que
  reconoce la limitación + sugiere temas reales del blog (reutiliza `_BLOG_TOPICS`), más cálido
  que `refusal_message` pero **sin ningún riesgo de alucinación** — nunca varía, nunca inventa.
- Se eliminaron `_no_context_system_prompt`, `build_no_context_messages` y `NO_CONTEXT_MAX_TOKENS`
  (código del intento fallido).
- `app.ollama_client.OllamaClient.stream_chat()` vuelve a su firma original (se retira el
  `max_tokens` opcional, sin uso tras el revert).
- `app.main.chat()`: el camino "sin contexto" vuelve a ser sin LLM (streaming palabra por
  palabra de `no_context_response`, como el rehúso original); el camino grounded no cambia.
- `_REFUSAL`/`refusal_message` se mantienen (piezas puras testeadas, sin uso actual en `main.py`).

**Validación (esta sesión, en vivo contra el stack real):** las 3 preguntas de la tabla ya NO
alucinan — responden con `no_context_response`, determinístico. Reconfirmados sin regresión:
saludo ES/EN (`greeting_response`) y pregunta grounded normal (cita ambos posts EN+ES). Suite:
ruff limpio + **72 tests** (ajustados los de `test_api.py`/`test_rag.py` al comportamiento
determinístico; los del intento con LLM se reescribieron o eliminaron).

**Lección para el Devlog:** un demo con LLM local pequeño (0.5B, CPU-only) no puede confiar en
prompts negativos ("no hagas X") para garantías duras como grounded-only — esas garantías deben
vivir en código determinístico (aquí: no llamar al LLM en absoluto sin contexto), no en
instrucciones que el modelo puede ignorar. Vale la pena tenerlo presente para cualquier feature
futura que dependa de que el LLM "se abstenga" de algo.
