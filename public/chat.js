// Chat page front-end.  Talks to /api/chat.
//
// No history is persisted between reloads — clearing it out on refresh
// keeps the Professor's persona predictable and matches the user's
// expectation that a page reload is a fresh conversation.

const LANG_KEY = "pokedex-lang";
const DEFAULT_LANG = "en";

const els = {
    langSelect: document.getElementById("lang-select"),
    log: document.getElementById("chat-log"),
    form: document.getElementById("chat-form"),
    input: document.getElementById("chat-input"),
    sendBtn: document.getElementById("chat-send"),
    clearBtn: document.getElementById("chat-clear"),
    professorName: document.querySelector(".professor-name"),
    professorBio: document.querySelector(".professor-bio"),
    oakSprite: document.getElementById("oak-sprite"),
    oakFallback: document.getElementById("oak-fallback"),
};

/*
 * Sprite source: 12 pre-sliced PNGs at /cells/oak_{0..11}.png.  Each
 * is ~150 KB; the HTML <head> preloads all 12 in parallel, and we
 * switch frames simply by rewriting <img>.src.  No canvas, no CSS
 * crop math, and a single 404 would make the fallback overlay visible.
 */
const SPRITE_FRAMES = 12;
const FRAME_URL = (i) => `/cells/oak_${i}.png`;
let currentFrame = 0;
let animationToken = 0;

function setFrame(index) {
    currentFrame = index;
    if (els.oakSprite) els.oakSprite.src = FRAME_URL(index);
}

if (els.oakSprite) {
    els.oakSprite.addEventListener("load", () => {
        if (els.oakFallback) els.oakFallback.hidden = true;
    });
    els.oakSprite.addEventListener("error", () => {
        const url = els.oakSprite.src;
        console.error("sprite failed to load:", url);
        els.oakSprite.style.display = "none";
        if (els.oakFallback) els.oakFallback.hidden = false;
        // Dump the real HTTP response into the chat log — it's always
        // visible there, regardless of the .oak-frame's overflow clip.
        showSpriteDiagnosticInLog(url).catch((e) =>
            console.error("diagnostic failed:", e),
        );
    });
}

async function showSpriteDiagnosticInLog(url) {
    if (!els.log) return;
    // Avoid spamming the log if every one of the 12 cells fails.
    if (els.log.querySelector(".oak-diag-msg")) return;

    let detail = `URL: ${url}\nfetching…`;
    try {
        const r = await fetch(url, { cache: "no-store" });
        const snippet = (await r.text()).slice(0, 200);
        detail =
            `URL: ${url}\n` +
            `HTTP: ${r.status} ${r.statusText}\n` +
            `Content-Type: ${r.headers.get("content-type") || "(none)"}\n` +
            `Content-Length: ${r.headers.get("content-length") || "(none)"}\n` +
            `Body[0..200]: ${JSON.stringify(snippet)}`;
    } catch (e) {
        detail = `URL: ${url}\nfetch threw: ${e.name}: ${e.message}`;
    }

    const wrap = document.createElement("div");
    wrap.className = "chat-msg chat-msg-system chat-error oak-diag-msg";
    const top = document.createElement("div");
    top.className = "chat-error-title";
    top.textContent = "Sprite failed to load";
    wrap.appendChild(top);
    const badge = document.createElement("div");
    badge.className = "chat-error-status";
    badge.textContent = "DIAGNOSTIC";
    wrap.appendChild(badge);
    const pre = document.createElement("pre");
    pre.className = "chat-error-pre";
    pre.textContent = detail;
    wrap.appendChild(pre);
    els.log.appendChild(wrap);
    scrollToBottom();
}

function pickRandomFrames(count, exclude) {
    const pool = Array.from({ length: SPRITE_FRAMES }, (_, i) => i)
        .filter((i) => i !== exclude);
    for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, count);
}

/**
 * Play a 2-frame "reaction" animation (~2 s total). Subsequent calls
 * bump animationToken so an in-flight animation gets cancelled cleanly.
 */
async function playFrameAnimation() {
    const token = ++animationToken;
    const frames = pickRandomFrames(2, currentFrame);
    for (const frame of frames) {
        if (token !== animationToken) return;
        setFrame(frame);
        await new Promise((r) => setTimeout(r, 1000));
    }
}

const state = {
    lang: localStorage.getItem(LANG_KEY) || DEFAULT_LANG,
    languages: [],
    strings: null,
    messages: [],    // [{role, content}]
    sending: false,
};

init().catch((err) => {
    console.error(err);
    appendSystemMessage(err.message);
});

async function init() {
    const langs = await fetchJSON("/api/languages").then((r) => r.languages);
    state.languages = langs;
    if (!langs.some((l) => l.code === state.lang)) state.lang = DEFAULT_LANG;
    populateLanguages();
    await loadStrings();
    applyI18n();
    greet();
    bindUi();
    // Surface server-side config issues up-front instead of hiding them
    // behind the first failed /api/chat call.
    checkChatHealth().catch((e) => console.warn("chat health check failed", e));
}

async function checkChatHealth() {
    const r = await fetch("/api/chat/health");
    if (!r.ok) return;
    const { has_api_key, model, referer } = await r.json();
    console.info("chat health:", { has_api_key, model, referer });
    if (!has_api_key) {
        appendErrorMessage(
            t("chat_error_config"),
            "GET /api/chat/health → has_api_key=false. Set OPENROUTER_API_KEY in Vercel → Settings → Environment Variables, then redeploy.",
            503,
        );
    }
}

function populateLanguages() {
    els.langSelect.innerHTML = "";
    for (const l of state.languages) {
        const o = document.createElement("option");
        o.value = l.code;
        o.textContent = l.native_name;
        els.langSelect.appendChild(o);
    }
    els.langSelect.value = state.lang;
}

async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status} from ${url}`);
    return r.json();
}

async function loadStrings() {
    state.strings = await fetchJSON(`/api/${state.lang}/strings`);
    document.documentElement.lang = state.lang;
}

function t(key, params = {}) {
    let s = (state.strings?.ui && state.strings.ui[key]) || key;
    for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, v);
    return s;
}

function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    document.title = `${t("chat_title")} · PÓkE-GooGle`;
    els.sendBtn.setAttribute("aria-label", t("chat_send"));
}

function greet() {
    // Only greet if the log is empty (first load or after Clear).
    if (els.log.childElementCount === 0) {
        appendMessage("assistant", t("chat_welcome"));
    }
}

function bindUi() {
    els.langSelect.addEventListener("change", async (e) => {
        state.lang = e.target.value;
        localStorage.setItem(LANG_KEY, state.lang);
        try {
            await loadStrings();
        } catch (err) {
            console.error(err);
        }
        applyI18n();
    });

    els.form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = els.input.value.trim();
        if (!text || state.sending) return;
        els.input.value = "";
        send(text);
    });

    els.clearBtn.addEventListener("click", () => {
        state.messages = [];
        els.log.replaceChildren();
        greet();
    });

    // Enter sends, Shift+Enter inserts a newline.
    els.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            els.form.requestSubmit();
        }
    });
}

async function send(text) {
    appendMessage("user", text);
    state.messages.push({ role: "user", content: text });

    state.sending = true;
    els.sendBtn.disabled = true;
    const typingEl = appendTyping();

    try {
        const r = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: state.messages, language: state.lang }),
        });
        typingEl.remove();
        if (!r.ok) {
            const detail = await readErrorDetail(r);
            appendErrorMessage(pickErrorText(r.status), detail, r.status);
            return;
        }
        const data = await r.json();
        const reply = (data.reply || "").trim();
        if (!reply) {
            appendErrorMessage(t("chat_error_generic"), "empty reply", 0);
            return;
        }
        state.messages.push({ role: "assistant", content: reply });
        appendMessage("assistant", reply);
        // Let the Professor "react" to the answer: 3 random frames, 1 s each.
        playFrameAnimation();
    } catch (err) {
        typingEl.remove();
        console.error(err);
        appendErrorMessage(t("chat_error_generic"), err.message, 0);
    } finally {
        state.sending = false;
        els.sendBtn.disabled = false;
        els.input.focus();
    }
}

function pickErrorText(status) {
    if (status === 429) return t("chat_error_rate_limit");
    if (status === 503) return t("chat_error_config");
    return t("chat_error_generic");
}

async function readErrorDetail(response) {
    try {
        const body = await response.json();
        if (typeof body === "string") return body;
        if (body && typeof body === "object") return body.detail || JSON.stringify(body);
    } catch (_) {
        try { return await response.text(); } catch (_) { return ""; }
    }
    return "";
}

function appendMessage(role, content) {
    const wrap = document.createElement("div");
    wrap.className = `chat-msg chat-msg-${role}`;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = content;
    wrap.appendChild(bubble);
    els.log.appendChild(wrap);
    scrollToBottom();
}

function appendTyping() {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg chat-msg-assistant chat-typing";
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.innerHTML = `<span class="dots"><span></span><span></span><span></span></span>`;
    wrap.appendChild(bubble);
    els.log.appendChild(wrap);
    scrollToBottom();
    return wrap;
}

function appendSystemMessage(text) {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg chat-msg-system";
    wrap.textContent = text;
    els.log.appendChild(wrap);
    scrollToBottom();
}

function appendErrorMessage(title, detail, status) {
    const wrap = document.createElement("div");
    wrap.className = "chat-msg chat-msg-system chat-error";
    const top = document.createElement("div");
    top.className = "chat-error-title";
    top.textContent = title;
    wrap.appendChild(top);
    if (detail) {
        // Show the upstream message inline so the user sees the real
        // cause (bad model id, auth, rate limit, network, ...) without
        // having to expand anything or open the devtools.
        const badge = document.createElement("div");
        badge.className = "chat-error-status";
        badge.textContent = status ? `HTTP ${status}` : "error";
        wrap.appendChild(badge);
        const pre = document.createElement("pre");
        pre.className = "chat-error-pre";
        pre.textContent = String(detail);
        wrap.appendChild(pre);
    }
    els.log.appendChild(wrap);
    scrollToBottom();
    console.error("chat error:", status, detail);
}

function scrollToBottom() {
    els.log.scrollTop = els.log.scrollHeight;
}
