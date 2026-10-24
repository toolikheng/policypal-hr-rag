/*
 * PolicyPal chat widget: plain JavaScript, no build step and no libraries.
 *
 * Add it to any page with:
 *   <script src="http://localhost:8000/widget/policypal-widget.js" defer></script>
 *
 * It asks the API that served this script (or the one in data-api-url) and shows the
 * answer, how it was produced, and the cited policy sections. A page on another site
 * needs its origin in the API's CORS_ORIGINS.
 *
 * Safety: answers and citations come from an LLM and from policy files that admins can
 * upload, so they are untrusted. Text is only ever set with textContent, never parsed as
 * HTML. The widget lives in a shadow root, so the page's CSS and the widget's CSS don't
 * affect each other.
 */
(function () {
  "use strict";

  const script = document.currentScript;
  const apiUrl = (script.dataset.apiUrl || new URL(script.src).origin).replace(/\/+$/, "");
  // The API may wait up to 120 s for the LLM on a CPU before quoting the policy instead.
  const TIMEOUT_MS = 180000;

  // How each answer was produced (the API's `mode`).
  const MODE_LABELS = {
    llm: "AI answer from the policies",
    extractive: "Policy text (no AI answer)",
    refused: "Not covered by the policies",
  };

  const STYLE = `
    :host { all: initial; font-family: system-ui, sans-serif; font-size: 14px; }
    .launcher { position: fixed; right: 20px; bottom: 20px; z-index: 2147483000;
      border: 0; border-radius: 24px; padding: 12px 18px; cursor: pointer;
      background: #1d4ed8; color: #fff; font: inherit; font-weight: 600;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25); }
    .panel { position: fixed; right: 20px; bottom: 76px; z-index: 2147483000;
      width: min(380px, calc(100vw - 40px)); height: min(560px, calc(100vh - 110px));
      display: flex; flex-direction: column; background: #fff; color: #111827;
      border: 1px solid #d1d5db; border-radius: 12px; overflow: hidden;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); }
    .panel[hidden] { display: none; }
    header { padding: 10px 14px; background: #1d4ed8; color: #fff; }
    header strong { display: block; }
    header small { opacity: 0.85; }
    .log { flex: 1; overflow-y: auto; padding: 12px; display: flex;
      flex-direction: column; gap: 10px; }
    .question { align-self: flex-end; max-width: 85%; background: #dbeafe;
      padding: 8px 10px; border-radius: 10px; white-space: pre-wrap; }
    .answer { max-width: 95%; background: #f3f4f6; padding: 8px 10px; border-radius: 10px; }
    .mode { font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 4px; }
    .text { white-space: pre-wrap; overflow-wrap: anywhere; }
    .sources { margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: #374151; }
    .error { color: #b91c1c; }
    form { display: flex; gap: 6px; padding: 10px; border-top: 1px solid #e5e7eb; }
    input { flex: 1; padding: 8px; border: 1px solid #d1d5db; border-radius: 8px; font: inherit; }
    button[type="submit"] { padding: 8px 12px; border: 0; border-radius: 8px;
      background: #1d4ed8; color: #fff; font: inherit; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: wait; }
  `;

  // Small helper: an element with a class and (optionally) text, set safely.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  const host = el("div");
  const root = host.attachShadow({ mode: "open" });
  const style = el("style");
  style.textContent = STYLE;

  const launcher = el("button", "launcher", "Ask HR policies");
  launcher.type = "button";
  launcher.setAttribute("aria-expanded", "false");

  const panel = el("section", "panel");
  panel.hidden = true;
  panel.setAttribute("aria-label", "PolicyPal HR policy assistant");
  const header = el("header");
  header.append(
    el("strong", "", "PolicyPal"),
    el("small", "", "Fictional sample policies for Binaan Maju Sdn Bhd"),
  );
  const log = el("div", "log");
  log.setAttribute("aria-live", "polite");
  const form = el("form");
  const input = el("input");
  input.placeholder = "Ask about leave, claims, overtime…";
  input.maxLength = 1000;
  input.setAttribute("aria-label", "Your question");
  const send = el("button", "", "Ask");
  send.type = "submit";
  form.append(input, send);
  panel.append(header, log, form);
  root.append(style, launcher, panel);

  let conversationId = null; // the API groups one chat's questions by this ID

  launcher.addEventListener("click", function () {
    panel.hidden = !panel.hidden;
    launcher.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) input.focus();
  });

  function showAnswer(answer) {
    const box = el("div", "answer");
    box.append(el("div", "mode", MODE_LABELS[answer.mode] || answer.mode));
    // Markdown source shown as plain text: readable, and never interpreted.
    box.append(el("div", "text", answer.answer));
    // An extractive answer already quotes each passage, so only list the sources here.
    if (answer.citations.length > 0) {
      const sources = el("ol", "sources");
      for (const citation of answer.citations) {
        const item = el("li", "", citation.document_title + " — " + citation.section);
        item.value = citation.number;
        sources.append(item);
      }
      box.append(sources);
    }
    return box;
  }

  async function errorMessage(response) {
    let detail = "";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      if (body.request_id) detail += " (reference " + body.request_id + ")";
    } catch (ignored) {
      // Not JSON (e.g. a proxy's error page): the status is enough.
    }
    return "PolicyPal couldn't answer (HTTP " + response.status + ")" +
      (detail ? ": " + detail : ".");
  }

  async function ask(question) {
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, TIMEOUT_MS);
    try {
      const response = await fetch(apiUrl + "/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, conversation_id: conversationId, channel: "widget" }),
        signal: controller.signal,
      });
      if (!response.ok) return el("div", "answer error", await errorMessage(response));
      const answer = await response.json();
      conversationId = answer.conversation_id;
      return showAnswer(answer);
    } catch (error) {
      const text = error.name === "AbortError"
        ? "PolicyPal took too long to answer. Please try again."
        : "PolicyPal can't be reached at " + apiUrl + ".";
      return el("div", "answer error", text);
    } finally {
      clearTimeout(timer);
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const question = input.value.trim();
    if (question.length < 3) return; // the API needs at least 3 characters
    input.value = "";
    log.append(el("div", "question", question));
    const waiting = el("div", "answer", "Searching the policies… (an AI answer can take a minute)");
    log.append(waiting);
    log.scrollTop = log.scrollHeight;
    send.disabled = true;
    waiting.replaceWith(await ask(question));
    send.disabled = false;
    log.scrollTop = log.scrollHeight;
    input.focus();
  });

  function mount() { document.body.append(host); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
