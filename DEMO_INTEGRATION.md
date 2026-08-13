# Integrar un demo a la infraestructura efímera (alexisalulema.com)

> **Copia este archivo en tu repo de demo.** Es el **contrato** autocontenido que tu proyecto
> debe cumplir para enchufarse al servicio de demos efímeros de `alexisalulema.com`. NO asume
> que tienes acceso al repo de la infra: todo lo que necesitas está aquí.

## Cómo funciona (en una frase)

Empaquetas tu demo como **imagen pública en GHCR**. La infra la provisiona on-demand en un
Resource Group efímero de Azure Container Apps, la expone en `https://demoNN.alexisalulema.com/`
detrás de un **gateway** que hace la autenticación y el ruteo por ti, y la destruye sola
(inactividad / tope de tiempo / kill-switch). Tú solo construyes **un contenedor que sirve
HTTP/WS por ingress interno**.

---

## El contrato (lo que tu demo DEBE cumplir)

1. **Contenedor con ingress interno, puerto fijo.** Sirve en `0.0.0.0:<TU_PUERTO>` (elige uno y
   documéntalo, p.ej. `8080`). El ingress es **interno** → solo el gateway te alcanza. **No
   pongas TLS en tu app**: Azure Container Apps + el gateway terminan TLS.
2. **Cero auth en tu app.** El gateway valida el JWT de sesión **antes** de enrutarte. Confía en
   todo request que te llega (ya pasó el filtro). No implementes login ni tokens propios.
3. **Sírvete desde la raíz `/`.** Te exponen en `https://demoNN.alexisalulema.com/`. Nada de
   rutas con prefijo fijo (`/miapp/...`).
4. **Streaming soportado.** El gateway proxea **WebSocket y SSE** en streaming, y **corta el
   stream cuando la sesión expira** (WS → close code `4001`). Un chat puede usar SSE o WS sin
   lógica extra; solo maneja el cierre abrupto con elegancia.
5. **Stateless / estado solo efímero.** Tu entorno se destruye **en cualquier momento**. No
   dependas de persistencia. Si necesitas estado (índice vectorial, DB), que sea **co-localizado,
   efímero y reconstruible al arranque** (p.ej. un Postgres+pgvector en el mismo contenedor/red,
   sembrado al iniciar desde un dump horneado en la imagen).
6. **Sin tecnología Microsoft en el stack interno** (restricción dura): OSS / terceros. Ej.:
   Claude (no Azure OpenAI), pgvector (no Azure AI Search), `sentence-transformers`, imagen en
   **GHCR** (no ACR). Azure/Cloudflare como *infra* sí están bien (no son "el demo").
7. **Imagen pública en GHCR.** Publica `ghcr.io/<owner>/<nombre>:latest` y marca el package como
   **Public** (la infra la jala sin credenciales). **Solo datos públicos en la imagen**; los
   secretos llegan en runtime (ver punto 8).
8. **Variables de entorno que recibes en provisión:**
   - `PROJECT_ID` — el slug de tu demo (ej. `rag-demo`).
   - `DEMO_SLOT` — el slot asignado (ej. `demo03`).
   - Los **secretos** que declares (ej. `ANTHROPIC_API_KEY`) — inyectados como secret del
     Container App. **Léelos de env; NUNCA los hornees en la imagen** (es pública).

---

## Referencia mínima (inline)

El demo válido más simple es un estático:

```dockerfile
# Dockerfile — sirve / en el puerto 80 (interno); el gateway hace el resto.
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
```

Una app dinámica con streaming, igual de autocontenida:

```python
# main.py — FastAPI: sirve / + un stream SSE. Sin auth (la hace el gateway).
import os
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()
PROJECT_ID = os.environ.get("PROJECT_ID", "")
DEMO_SLOT  = os.environ.get("DEMO_SLOT", "")
# SECRET = os.environ["ANTHROPIC_API_KEY"]   # inyectado en provisión, no en la imagen

@app.get("/")
def root():
    return {"project": PROJECT_ID, "slot": DEMO_SLOT}

@app.get("/stream")
def stream():
    def gen():
        for tok in ("hola ", "mundo"):
            yield f"data: {tok}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```

```dockerfile
# Dockerfile para la app FastAPI (escucha en 0.0.0.0:8080, ingress interno)
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt . && RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Estilo / branding (adopta el look de alexisalulema.com)

Para que tu demo se vea como parte del sitio **y adopte sus cambios de estilo
automáticamente**, enlaza **en vivo** la hoja de tema que publica el sitio (mismos design
tokens: colores, tipografías, dark/light) y estila con sus variables CSS:

```html
<link rel="stylesheet" href="https://alexisalulema.com/demo-theme.css">
```
```css
/* Tu UI usa los tokens del tema (no hardcodees colores): */
.panel  { background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius); }
.title  { color: var(--color-text); font-family: var(--font-sans); }
.accent { color: var(--color-accent); }
```

- **Auto-adopción:** enlazas el archivo vivo → el día que el sitio cambie su branding, tu demo
  lo toma solo (no es una copia). No hardcodees la paleta; usa `var(--color-*)`, `--font-*`,
  `--radius`.
- **Dark/light:** el tema es **dark por defecto** y pasa a **light** si el SO lo prefiere
  (`prefers-color-scheme`). Los demos están en otro subdominio, así que **no comparten** el
  toggle del sitio; si quieres un toggle propio, pon `data-theme="light"|"dark"` en `<html>`.
- **Fuentes:** el tema ya importa Inter + JetBrains Mono; con enlazarlo las tienes.
- **Fallback:** ten valores propios mínimos por si el tema no carga (degradación elegante).

---

## Lo que entregas a la infra (hand-off manifest)

Cuando tu imagen esté lista y probada, pásale al mantenedor de la infra estos datos (él hace el
registro y la provisión en el repo de infra privado; **tú no tocas Azure ni OIDC**):

| Campo | Ejemplo |
|---|---|
| `projectId` (slug) | `rag-demo` |
| Nombre legible (ES / EN) | "RAG Chatbot" |
| Imagen GHCR + puerto | `ghcr.io/alulema/rag-demo:latest`, `8080` |
| `shareable` | `false` (stateful → un entorno por request) / `true` (stateless reusable) |
| Secretos a inyectar | `ANTHROPIC_API_KEY` |
| Recursos extra | sidecar Postgres+pgvector (si aplica) + cómo levantarlo |

---

## Ciclo de vida que tu app DEBE tolerar

- Sesión por usuario: **~20 min** (hard cap).
- Inactividad: **~8 min** sin tráfico de cliente → teardown.
- Vida máxima del entorno: **~60 min**.
- Kill-switch del admin en cualquier momento.

El gateway cierra WS/SSE al expirar la sesión. **Diséñate para teardown abrupto:** arranque
rápido, sin estado que se pierda. No asumas que la siguiente request verá lo de la anterior si
hubo un corte.

---

## Prueba local (sin la infra)

El gateway es **transparente** (proxy + auth). Regla práctica: **si tu contenedor funciona
golpeándolo directo en su puerto, funciona detrás del gateway.** Así que para el 90% del
desarrollo basta:

```bash
docker build -t mi-demo . && docker run -p 8080:8080 \
  -e PROJECT_ID=mi-demo -e DEMO_SLOT=demo01 mi-demo
curl localhost:8080/         # tu app, directo
```

Para validar el ruteo por subdominio + auth por token end-to-end (opcional, antes de publicar),
coordina con el mantenedor de la infra: tiene un `docker-compose` que levanta el gateway real +
storage emulado y prueba el flujo completo.

---

## Notas capturadas del relay con la infra (`personal-website`)

> Respuestas de alcance general traídas desde el Copilot de `personal-website` (vía Alexis, relay
> humano). Se capturan aquí para que el contrato sea el cerebro compartido (per `CLAUDE.md`).

### 2026-08-12 — Pull policy en provisión y refresh event-driven

**1) Pull policy: siempre `:latest` fresco (sin digest pineado).**
La provisión (`demo-provision.yml`) crea un RG efímero nuevo (`rg-demo-<slot>`) + un Container App
nuevo (primera revisión). ACA resuelve y **jala `:latest` contra el manifest actual de GHCR** al
crear la revisión (revisión nueva = pull nuevo; no hay `imagePullPolicy`, ACA no es k8s). Por tanto
**una imagen recién republicada llega sola al próximo demo** — cero acción de la infra.
- **Caveats:** tag mutable ⇒ **sin rollback ni atomicidad** (lo que sea `:latest` al provisionar es
  lo que ve el usuario). Si se quiere rollback/pin: publicar además un tag inmutable (`:<gitsha>` o
  `:<fecha-corpus>`) y pasárselo a la infra para fijar el param `image` del Bicep.
- **Demos en vuelo NO se actualizan** (correcto: efímeros ~20 min); el refresh solo afecta demos
  provisionados **después** del push.

**2) Refresh event-driven cross-repo: `repository_dispatch` (Opción A, recomendada).**
Publicar post = Keystatic commitea markdown a `alulema/personal-website` (`src/content/blog-{en,es}/**`);
la infra ya dispara workflows por REST API con un PAT. Al publicar, la infra hace
`POST /repos/alulema/rag-blogposts/dispatches` con `event_type: refresh-corpus` → nuestro
`refresh-corpus.yml` (trigger `repository_dispatch`, **debe vivir en el default branch**) reconstruye
`rag-demo-db:latest` → por (1), el próximo demo sirve el corpus fresco.
- **Token (única credencial):** lo **minta el dueño de este repo** (fine-grained PAT scoped a
  `alulema/rag-blogposts`, **Contents: Read and write** para Opción A); Alexis lo guarda como secret
  `RAG_DISPATCH_TOKEN` en `personal-website`. La infra no puede scopear un token a un repo ajeno.
- **Timing (importante):** nuestra ingesta lee el **sitemap público en vivo**, así que el dispatch
  debe llegar **después** de que el deploy del sitio publique el post (si no, re-ingerimos antes de
  que el post esté live → no-op). Coordinar que el trigger salga tras `deploy.yml`, no en el push.
- **Drafts:** como ingerimos del sitio público, los borradores **no** entran; un trigger espurio
  produce un refresh no-op (sin diff → sin rebuild). No requiere filtrado especial.
- La infra deja listo su `notify-rag-refresh.yml` (push a `main` con paths de blog → dispatch) en
  cuanto se confirmen: repo, `event_type`, token, forma del `client_payload`, y default branch.
