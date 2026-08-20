// UI de chat del demo RAG (vanilla JS). Consume el endpoint POST /chat, que emite SSE
// (event: sources | token | error | done) — se lee con fetch() + ReadableStream porque
// EventSource es solo-GET. El historial vive en el cliente (stateless en el server).

const messagesEl = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const themeToggle = document.getElementById("theme-toggle");
const aboutDemoBtn = document.getElementById("about-demo-btn");

/** Historial de la conversación: [{role, content}]. Se envía completo en cada turno. */
const history = [];
let streaming = false;

// ── Utilidades ────────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/** Markdown mínimo y SEGURO: escapa HTML y luego resalta **negrita** e `inline code`. */
function renderMarkdownLite(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  return html;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function hideEmptyState() {
  if (emptyState) emptyState.remove();
}

// ── Render de mensajes ──────────────────────────────────────────────────────
function addUserMessage(text) {
  hideEmptyState();
  const wrap = document.createElement("div");
  wrap.className = "msg msg-user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function addAssistantMessage() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-assistant";
  const bubble = document.createElement("div");
  bubble.className = "bubble cursor";
  wrap.appendChild(bubble);
  messagesEl.appendChild(wrap);
  scrollToBottom();
  return { wrap, bubble };
}

function renderCitations(wrap, sources) {
  if (!sources || sources.length === 0) return;
  const box = document.createElement("div");
  box.className = "citations";
  const title = document.createElement("div");
  title.className = "citations-title";
  title.textContent = "Fuentes / Sources";
  box.appendChild(title);
  const ul = document.createElement("ul");
  for (const s of sources) {
    const li = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "lang-badge";
    badge.textContent = s.lang || "";
    const a = document.createElement("a");
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = s.title || s.url;
    li.appendChild(badge);
    li.appendChild(a);
    ul.appendChild(li);
  }
  box.appendChild(ul);
  wrap.appendChild(box);
  scrollToBottom();
}

function addNotice(wrap, text, isError) {
  const p = document.createElement("p");
  p.className = "notice" + (isError ? " error" : "");
  p.textContent = text;
  wrap.appendChild(p);
  scrollToBottom();
}

// ── Parser SSE sobre fetch/ReadableStream ───────────────────────────────────
// Divide el flujo en bloques separados por línea en blanco; cada bloco tiene
// líneas `event:` y `data:`. Invoca onEvent(event, dataString) por bloque.
function parseSseBuffer(buffer, onEvent) {
  const blocks = buffer.split("\n\n");
  const remainder = blocks.pop(); // último bloque puede estar incompleto
  for (const block of blocks) {
    let event = "message";
    const dataLines = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) onEvent(event, dataLines.join("\n"));
  }
  return remainder;
}

// ── Envío + streaming ───────────────────────────────────────────────────────
async function sendMessage(text) {
  if (streaming) return;
  const question = text.trim();
  if (!question) return;

  streaming = true;
  setBusy(true);

  addUserMessage(question);
  history.push({ role: "user", content: question });

  const { wrap, bubble } = addAssistantMessage();
  let answer = "";
  let done = false;

  try {
    const resp = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });

    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseBuffer(buffer, (event, data) => {
        if (event === "sources") {
          try {
            renderCitations(wrap, JSON.parse(data));
          } catch (_) {
            /* ignore malformed sources */
          }
        } else if (event === "token") {
          try {
            answer += JSON.parse(data).text || "";
          } catch (_) {
            /* ignore */
          }
          bubble.innerHTML = renderMarkdownLite(answer);
          scrollToBottom();
        } else if (event === "error") {
          let msg = "Error del servidor.";
          try {
            msg = JSON.parse(data).message || msg;
          } catch (_) {
            /* ignore */
          }
          addNotice(wrap, "⚠ " + msg, true);
        } else if (event === "done") {
          done = true;
        }
      });
    }
  } catch (err) {
    addNotice(wrap, "⚠ Conexión interrumpida (la sesión del demo pudo expirar). Intenta de nuevo.", true);
  } finally {
    bubble.classList.remove("cursor");
    if (answer) {
      history.push({ role: "assistant", content: answer });
    }
    if (!done && answer) {
      // Stream cortado antes del evento 'done' (teardown/expiración de sesión).
      addNotice(wrap, "⚠ Respuesta incompleta (stream cerrado).", false);
    }
    streaming = false;
    setBusy(false);
    input.focus();
  }
}

function setBusy(busy) {
  sendBtn.disabled = busy;
  input.disabled = busy;
  messagesEl.setAttribute("aria-busy", busy ? "true" : "false");
}

// ── Auto-resize del textarea ────────────────────────────────────────────────
function autoResize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

// ── Tema (override propio; el demo no comparte el toggle del sitio) ──────────
function applyStoredTheme() {
  const t = localStorage.getItem("demo-theme");
  if (t === "light" || t === "dark") {
    document.documentElement.setAttribute("data-theme", t);
  }
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme");
  const isLight = cur
    ? cur === "light"
    : window.matchMedia("(prefers-color-scheme: light)").matches;
  const next = isLight ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("demo-theme", next);
}

// ── Eventos ─────────────────────────────────────────────────────────────────
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value;
  input.value = "";
  autoResize();
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", autoResize);

messagesEl.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip && !streaming) {
    sendMessage(chip.textContent);
  }
});

themeToggle.addEventListener("click", toggleTheme);

// Panel "Acerca de este demo" (window.DemoPanel): script aditivo cargado desde
// alexisalulema.com — trigger:"custom" en DEMO_INFO, así que lo abrimos nosotros.
// Si el script no cargó (offline, bloqueado), el botón simplemente no hace nada.
aboutDemoBtn.addEventListener("click", () => {
  window.DemoPanel?.open();
});

applyStoredTheme();
input.focus();
