# CLAUDE.md — rag-blogposts

Demo **RAG sobre los posts del blog de alexisalulema.com**: un chatbot que responde preguntas
**fundamentado en los posts**, con **citas/enlaces** al post fuente. Bilingüe (EN+ES). Es uno de
los **demos efímeros** de `alexisalulema.com`: se provisiona on-demand, corre un rato y se
destruye solo. **Stack 100% OSS · $0 de API de pago · sin tecnología Microsoft en el stack
interno · self-contained** (sin secretos en runtime, sin llamadas externas en producción).

> **Contrato con la infra:** lee `DEMO_INTEGRATION.md` (en este repo) — define qué debe cumplir
> el contenedor para enchufarse al servicio de demos efímeros. **Este archivo es el plan del
> proyecto; aquél es el contrato de integración.** No los contradigas.

## Coordinación con la infra (repo `personal-website`)
Eres una instancia **independiente**: no compartes contexto, memoria ni canal con la sesión que
mantiene la infra en `personal-website`. Tu **fuente de verdad** sobre la infra es
`DEMO_INTEGRATION.md` (este repo) — consúltala **siempre primero**.
- Para algo de la infra que **no** esté en `DEMO_INTEGRATION.md`, pídele a Alexis que **lleve la
  pregunta** al lado de `personal-website` y te traiga la respuesta (él es el **relay humano**;
  no hay conexión directa entre repos).
- Cuando recibas una respuesta de alcance general, **escríbela de vuelta en
  `DEMO_INTEGRATION.md`** para que quede capturada y la próxima vez (u otra instancia/demo) no
  tenga que volver a preguntar. El contrato es el cerebro compartido, no ninguna sesión viva.

## Stack (fijado — no cambiar sin consultar al dueño)
- **App:** FastAPI (Python 3.13) — UI de chat en `/` + endpoint **SSE** de streaming.
- **LLM:** **Qwen2.5-1.5B-Instruct** (Apache-2.0, multilingüe) vía **Ollama**, local en el
  contenedor. **$0 API.** Tamaño configurable por env (p.ej. a 7B) si la calidad se queda corta.
- **Embeddings:** `sentence-transformers` `paraphrase-multilingual-MiniLM-L12-v2` (384-d), local.
- **Vector store:** Postgres 16 + **pgvector**, co-localizado y efímero, **sembrado al arranque
  desde un dump horneado** (embeddings precomputados en build-time).
- **Sin secretos en runtime. Sin APIs externas en producción.** (En *build* sí se traen los
  posts públicos para la ingesta.)

## Arquitectura
- **Runtime:** un Container App con **3 contenedores** que comparten `localhost`:
  `app` (FastAPI `:8080`, ingress interno — lo alcanza el gateway) · `ollama` (`:11434`) ·
  `db` (postgres+pgvector `:5432`, sembrado al arranque).
- **Ingesta (build-time, en CI):** trae los posts del **origen público** (`alexisalulema.com`,
  vía `sitemap-index.xml` → URLs `/blog/*` y `/es/blog/*`; NO se depende del repo privado) →
  limpia → **chunk** (~600 tokens, overlap ~80) → **embed** → `dump.sql` con metadata
  (título, url, lang, fecha) → horneado en la imagen `db`.
- **Local:** `docker-compose` con los 3 servicios.

## Flujo RAG (por mensaje)
`pregunta + historial (del cliente)` → embed de la query → **top-k** (k=5, cosine) en pgvector →
prompt = `system (grounded + cita fuentes) + contexto recuperado + historial + pregunta` →
**Ollama/Qwen** genera en **streaming** → **SSE** al cliente + adjunta **citas** (los posts de
los chunks usados).

## Funcionalidades
1. **UI de chat** single-page en `/` (vanilla, ligera), **streaming token a token** (SSE).
2. **Responde en el idioma de la pregunta** (EN/ES); retrieval **cross-lingual** (embeddings
   multilingües → una pregunta ES recupera chunks EN y viceversa).
3. **Citas:** cada respuesta lista los posts fuente (título + enlace a `alexisalulema.com/blog/…`).
4. **Grounded-only:** si la respuesta no está en el corpus, lo dice ("solo puedo responder sobre
   los posts de Alexis"). System prompt anti-alucinación.
5. *(Opcional)* panel "fuentes recuperadas" para transparencia del RAG.

## Estilo / branding (adopta el look del sitio)
Enlaza **EN VIVO** la hoja de tema del sitio y estila con sus variables — **no hardcodees la
paleta**, así el demo adopta los cambios de branding automáticamente:
```html
<link rel="stylesheet" href="https://alexisalulema.com/demo-theme.css">
```
Usa `var(--color-bg)`, `--color-bg-card`, `--color-text`, `--color-accent`, `--font-sans`,
`--font-mono`, `--radius`. Dark por defecto + light por `prefers-color-scheme` (los demos no
comparten el toggle del sitio; otro subdominio). Ten un fallback mínimo por si el tema no carga.
Detalle en `DEMO_INTEGRATION.md` §Estilo.

## Integración con la infra (hand-off manifest)
Cuando esté listo, pásale al mantenedor de la infra (repo `personal-website`, privado) para que
lo registre y provisione (tú no tocas Azure ni OIDC):
| Campo | Valor |
|---|---|
| `projectId` | `rag-demo` (ya existe allí como `demoReady:false`) |
| Imagen(es) GHCR | `ghcr.io/alulema/rag-demo-*:latest` (márcalas **Public**) |
| Puerto app | `8080`, ingress interno, sirve `/`, **sin auth** (la hace el gateway) |
| `shareable` | **true** (stateless: historial en el cliente, corpus read-only) |
| Secretos | **ninguno** |
| Streaming | **SSE** (el gateway lo proxea y corta al expirar la sesión) |
| Servicios extra | sidecars `ollama` + `postgres/pgvector` (multi-contenedor) |

**Tolera teardown abrupto** (20 min sesión / 8 min idle / kill-switch): arranque rápido (cargar
dump + modelo), sin estado que perder.

## Refrescar el corpus cuando haya posts nuevos
Workflow `refresh-corpus.yml` (`workflow_dispatch`, opcional `schedule`): trae los posts del
origen público → re-ingesta (chunk + embed) → regenera `dump.sql` → **commitea** snapshot + dump
→ **rebuild + push** de la imagen `db` a GHCR. Un clic. El **próximo demo provisionado** usa el
corpus fresco. **No es reentrenamiento:** el modelo es fijo; solo se **re-indexa** el corpus.

## Parámetros
| Param | Valor |
|---|---|
| LLM | Qwen2.5-1.5B-Instruct (Q4) vía Ollama; opción 7B por env |
| Embeddings | paraphrase-multilingual-MiniLM-L12-v2 (384-d) |
| top-k | 5 · chunk ~600 tokens, overlap 80 · max output ~512 tokens |
| shareable | true · secretos: ninguno · puerto app: 8080 |

## Estructura sugerida
```
rag-blogposts/
  app/                 # FastAPI: main.py, rag.py, ui (static)
  ingest/              # build-time: fetch posts → chunk → embed → dump.sql
  db/                  # Dockerfile.db (postgres+pgvector + dump) + init
  Dockerfile           # app
  docker-compose.yml   # local: app + ollama + db
  .github/workflows/   # build+push imágenes a GHCR + refresh-corpus.yml
  DEMO_INTEGRATION.md  # contrato de la infra (copiado)
  CLAUDE.md            # este archivo
  README.md
```

## Orden de build sugerido
1. **Ingesta** (`ingest/`): trae unos pocos posts del sitio público → chunk + embed → `dump.sql`
   de muestra. Valida calidad de chunks/metadata.
2. **App + RAG** (`app/`): carga el dump en pgvector local, retrieval top-k, prompt, **Ollama/Qwen
   en streaming**. Prueba por consola/SSE.
3. **UI** (`/`): chat vanilla + SSE + estilo del tema del sitio + citas.
4. **Contenedores:** `Dockerfile` (app), `Dockerfile.db` (postgres + dump), `docker-compose` local
   (app + ollama + db). Valida e2e local.
5. **CI:** workflows de build+push a GHCR + `refresh-corpus.yml`.
6. **Hand-off:** entrega el manifest al mantenedor de la infra.

## Restricciones duras
- **Sin tecnología Microsoft** en el stack interno (OSS/terceros). Azure/Cloudflare como *infra*
  de despliegue sí (no son "el demo").
- **$0 API de pago** (LLM y embeddings locales).
- **Self-contained:** sin secretos en runtime, sin llamadas externas en producción.
- Imágenes en **GHCR** (no ACR), **públicas**. Solo datos públicos en la imagen (los posts ya son
  públicos).
- **Diseñar para teardown abrupto.**

## Comandos clave
- Local e2e: `docker compose up -d --build` → abrir `http://localhost:8080`
- Ingesta local: `python ingest/run.py` (genera `db/dump.sql`)
- (Define lint/test al crear el proyecto.)

## Convenciones de trabajo — IMPORTANTE
- **Nunca auto-commitear.** Prepara los comandos `git` exactos para que el **dueño** los corra
  (identidad **personal**, separada de la del trabajo). Termina cada mensaje de commit con el
  trailer `Co-Authored-By:`.
- Una rama por concern lógico; mantén refactors (sin cambio de comportamiento) separados de
  cambios de comportamiento/bugfixes.
- Repo **público** → nada de secretos ni datos privados en commits.

## No-objetivos
Sin persistir conversaciones server-side · sin fine-tuning (solo RAG) · sin auth propia · sin GPU
(CPU only; ACA serverless GPU es opción futura) · sin reindex en runtime (corpus fijo por imagen).
