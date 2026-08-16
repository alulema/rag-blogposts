# Hand-off manifest — `rag-demo` (rag-blogposts)

Documento para el mantenedor de la infra de demos efímeros (`personal-website`). Contiene todo lo
necesario para **registrar y provisionar** este demo. La infra no toca este repo; solo consume las
imágenes públicas de GHCR. (Complementa `DEMO_INTEGRATION.md`; no lo contradice.)

## Manifest

| Campo | Valor |
|---|---|
| `projectId` (slug) | `rag-demo` |
| Nombre legible | "RAG Chatbot" / "Chatbot RAG del blog" |
| Imágenes GHCR (Públicas ✅) | `ghcr.io/alulema/rag-demo-app:latest` · `ghcr.io/alulema/rag-demo-ollama:latest` · `ghcr.io/alulema/rag-demo-db:latest` |
| Puerto app | **8080** · ingress **interno** · sirve `/` · **sin auth** (la hace el gateway) · sin TLS |
| `shareable` | **true** (stateless: historial en el cliente, corpus read-only) |
| Secretos | **NINGUNO** |
| Streaming | **SSE** (`POST /chat` → `text/event-stream`) |
| Servicios extra | sidecars **ollama** (`:11434`) + **postgres/pgvector** (`:5432`) → **multi-contenedor** |
| Health check | `GET /healthz` → `{"status":"ok"}` |

## Topología multi-contenedor (⚠️ dato crítico de provisión)

Son **3 contenedores en el MISMO Container App**, que **comparten `localhost`** (en ACA multi-
contenedor comparten el network namespace):

- `app` (FastAPI `:8080`) → único con ingress; lo alcanza el gateway.
- `ollama` (`:11434`) → interno.
- `db` (postgres+pgvector `:5432`) → interno; se **siembra al arranque** desde el `dump.sql` horneado.

**La app NO necesita variables de entorno en ACA.** Sus defaults ya apuntan a `localhost`:
`DB_DSN=postgresql://rag:rag@localhost:5432/rag` y `OLLAMA_HOST=http://localhost:11434`.

> ⚠️ **Ignora los `environment:` del `docker-compose.yml`** (`db:5432`, `ollama:11434`): esos nombres
> de servicio son **solo para Docker Compose** (DNS por nombre de servicio). En ACA multi-contenedor
> es `localhost`, que es justo el default de la app. **Cero overrides necesarios.**

## Recursos sugeridos (CPU-only, sin GPU)

| Contenedor | vCPU | Memoria | Nota |
|---|---|---|---|
| `ollama` | ~1.5 | ~1.5–2 GiB | **Qwen2.5-0.5B-Instruct** (Q4) horneado; inferencia CPU — el lever de velocidad |
| `app` | ~0.4 | ~1–1.5 GiB | FastAPI + modelo de embeddings (384-d) horneado |
| `db` | ~0.1 | ~0.5 GiB | pgvector, 178 chunks |

**Cap de ACA Consumption = 2 vCPU / 4 GiB** (máximo del plan). El split lo maneja la infra, sesgado
a `ollama` (~1.5 vCPU). Con el modelo **0.5B** el footprint baja y entra cómodo en el cap; en CPU es
~3× más rápido en tokens/s que 1.5B (el demo es 1 stream por usuario, latencia limitada por CPU).

## Arranque y ciclo de vida

- **Orden:** `app` espera a que `db` acepte conexiones (`_wait_for_db`, reintentos; env opcional
  `DB_WAIT_RETRIES`, default 60×2s) antes de crear el pool + schema. `ollama` (modelo horneado)
  levanta rápido; la app tolera que aún no esté (una 1ª request muy temprana degrada con un evento
  SSE `error`, no crashea).
- **Cold start:** cargar el modelo de embeddings en `app` + seed de `db` desde el dump + carga de
  Qwen en `ollama`. Segundos a decenas de segundos; todo local, sin descargas (imágenes offline).
- **Teardown abrupto** (sesión ~20 min / idle ~8 min / kill-switch): **sin estado que perder**
  (historial en el cliente, corpus read-only). El gateway corta el SSE al expirar; el cliente lo
  maneja con elegancia.

## Freshness del corpus (ya coordinado)

- La imagen `db` hornea el `dump.sql`. Se refresca **al reconstruir la imagen**, no al provisionar.
- `refresh-corpus.yml` (en este repo): `repository_dispatch` desde `personal-website` al publicar un
  post (+ `schedule` semanal de respaldo) → re-ingiere → rebuild+push de `rag-demo-db:latest`.
- Como la provisión jala `:latest` fresco, el **próximo demo** usa el corpus actualizado sin acción
  de la infra. (Detalle en `DEMO_INTEGRATION.md` §Notas capturadas del relay.)

## Overrides opcionales (env, si algún día se quieren)

`LLM_MODEL` (default **`qwen2.5:0.5b-instruct`**, elegido por velocidad en CPU; `qwen2.5:1.5b-instruct`
o `7b-instruct` dan más calidad pero requieren hornear ese modelo en la imagen `ollama` y más
RAM/CPU) · `TOP_K` (default 5) · `SIMILARITY_THRESHOLD` (default 0.32, calibrado) · `MAX_OUTPUT_TOKENS`
(default 256) · `PROJECT_ID` / `DEMO_SLOT` (informativos).

## Checklist de provisión (infra)

1. Provisionar Container App multi-contenedor con las **3 imágenes** públicas de arriba.
2. `app` = único con ingress interno, puerto **8080**, sirve `/`.
3. **Sin secretos, sin env obligatorias** (defaults `localhost` correctos).
4. Recursos dentro del cap de ACA Consumption (**2 vCPU / 4 GiB**), sesgado a `ollama` (ver tabla).
5. Enrutar `https://demoNN.alexisalulema.com/` → `app:8080`. Listo.
