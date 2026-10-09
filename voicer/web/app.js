// Voice Studio UI: one page, hash routes (#clone, #tts, ...). No build step.
"use strict";

const NAV = [
  ["tts", "Text to Speech"], ["library", "Voice Library"], ["voices", "My Voices"], ["clone", "Clone Voice"],
  ["changer", "Voice Changer"], ["dialogue", "Dialogue"], ["batch", "Batch"], ["dictionary", "Dictionary"],
  ["history", "History"], ["api", "API & Agents"], ["usage", "Usage"], ["settings", "Settings"],
];
const views = {};               // route → render(el)

const $ = (sel, root = document) => root.querySelector(sel);
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...kids.flat().filter((k) => k != null));
  return el;
}
// fetch that throws a plain-language Error for network failures and non-2xx answers (uses the API's `detail`)
async function request(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch {
    throw new Error(t("Cannot reach the server. Is Voice Studio still running?"));
  }
  if (!r.ok) {
    const body = r.headers.get("content-type")?.includes("json") ? await r.json().catch(() => ({})) : { detail: await r.text() };
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
    throw new Error(detail || r.statusText || `Error ${r.status}`);
  }
  return r;
}
async function api(path, opts = {}) {
  const r = await request(path, opts);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}

// Sidebar icons: simple line drawings (24×24, drawn for this app).
const NAV_ICONS = {
  tts: "M4 7V5h16v2M12 5v14M9 19h6",
  library: "M5 4h4v16H5zM10 4h4v16h-4zM15.5 5.2l3.4-.9 3.1 14.8-3.4.9z",
  voices: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM19 11a7 7 0 0 1-14 0M12 18v3",
  clone: "M9 9h11v11H9zM5 15H4V4h11v1",
  changer: "M7 4 3 8l4 4M3 8h14M17 12l4 4-4 4M21 16H7",
  dialogue: "M4 5h11v8H8l-4 3zM15 9h5v8l-3-2h-7v-2",
  batch: "M12 3 2 8l10 5 10-5zM2 12.5l10 5 10-5M2 17l10 5 10-5",
  dictionary: "M3 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H3zM21 5h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z",
  history: "M3 12a9 9 0 1 0 18 0 9 9 0 1 0-18 0M12 7v5l3 2",
  api: "M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16",
  usage: "M5 20v-7M12 20V4M19 20v-11M3 20h18",
  settings: "M4 6h16M4 12h16M4 18h16M9 4v4M15 10v4M7 16v4",
};
function navIcon(id) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), path = document.createElementNS(ns, "path");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8",
    "stroke-linecap": "round", "stroke-linejoin": "round", class: "nav-icon", "aria-hidden": "true" })) svg.setAttribute(k, v);
  path.setAttribute("d", NAV_ICONS[id] || "");
  svg.append(path);
  return svg;
}
function renderNav(active) {
  $("#nav").replaceChildren(...NAV.map(([id, label]) =>
    h("a", { href: `#${id}`, class: id === active ? "active" : null, "data-route": id, title: t(label),
      "aria-current": id === active ? "page" : null }, navIcon(id), t(label))));
  $("#nav a.active")?.scrollIntoView?.({ block: "nearest", inline: "nearest" });   // phone: keep it visible
}
// Clear message for anything that fails without its own error handling.
let toastTimer;
function toast(text, kind = "error") {
  const t = $("#toast");
  if (!t) return;
  t.className = kind;
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 6000);
}
window.addEventListener("unhandledrejection", (e) => toast(t("Something went wrong: {m}", { m: e.reason?.message || e.reason })));
window.addEventListener("error", (e) => toast(t("Something went wrong: {m}", { m: e.message })));
function route() {
  const id = location.hash.slice(1) || "tts";
  renderNav(id === "blend" ? "clone" : id);           // Blend is a tab of Clone Voice
  previewStop();
  const view = $("#view");
  view.replaceChildren();
  (views[id] || placeholder)(view, id);
}
function placeholder(el, id) {
  const label = (NAV.find((n) => n[0] === id) || [, "Not found"])[1];
  el.append(h("h1", {}, t(label)), h("p", { class: "sub" }, t("Coming soon.")));
}
async function pollStatus() {
  const box = $("#status");
  try {
    const s = await api("/api/health");
    box.className = "status ok";
    $("#status-text").textContent = t("Server ok · v{v}", { v: s.version });
  } catch {
    box.className = "status err";
    $("#status-text").textContent = t("Server offline");
  }
}

// ---------- Clone Voice
const clone = { draft: null };
const fmtSec = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

const store = {            // per-browser convenience only; the page works without it
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* blocked */ } },
};
async function cloneDraft() {
  if (!clone.draft) {
    clone.draft = await api("/api/clone/drafts", { method: "POST" });
    store.set("clone-draft", clone.draft.id);
  }
  return clone.draft;
}
async function cloneRestore() {           // keep the samples after a page reload
  const id = store.get("clone-draft");
  if (!id || clone.draft) return;
  try { clone.draft = await api(`/api/clone/drafts/${id}`); } catch { store.set("clone-draft", null); }
  renderCloneFiles();
  renderClips();
}
async function cloneUpload(files, source = "upload") {
  const msg = $("#clone-msg");
  if (!files.length) return;
  msg.className = "muted";
  msg.textContent = t("Uploading {n} file(s)…", { n: files.length });
  try {
    const d = await cloneDraft();
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const r = await api(`/api/clone/drafts/${d.id}/files?source=${source}`, { method: "POST", body: fd });
    clone.draft = r;
    msg.className = r.errors.length ? "warn" : "ok";
    msg.textContent = r.errors.length
      ? t("Some files were skipped: {list}", { list: r.errors.map((e) => `${e.file} (${e.error})`).join(", ") })
      : t("Added {n} file(s).", { n: files.length });
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Upload failed: {m}", { m: e.message });
  }
  renderCloneFiles();
  cloneProcess();
}
async function cloneRemove(name) {
  try {
    clone.draft = await api(`/api/clone/drafts/${clone.draft.id}/files/${encodeURIComponent(name)}`, { method: "DELETE" });
  } catch (e) {
    const msg = $("#clone-msg");
    msg.className = "error";
    msg.textContent = t("Could not remove the file: {m}", { m: e.message });
    return;
  }
  renderCloneFiles();
  cloneProcess();
}
// Auto-clean after every change: mono 24 kHz, denoise, trim silence, normalize, split 6–15 s.
let processing = null;
async function cloneProcess() {
  if (!clone.draft) return;
  const run = (processing = Symbol());
  const box = $("#clone-clips-msg");
  if (!clone.draft.files.length) { clone.draft.clips = []; renderClips(); return; }
  if (box) { box.className = "muted"; box.textContent = t("Cleaning audio…"); }
  $("#clone-clips")?.classList.add("busy");
  try {
    const d = await api(`/api/clone/drafts/${clone.draft.id}/process`, { method: "POST" });
    if (run !== processing) return;                // a newer run started
    clone.draft = d;
    renderClips();
  } catch (e) {
    if (box) { box.className = "error"; box.textContent = t("Cleaning failed: {m}", { m: e.message }); }
    return;
  } finally {
    $("#clone-clips")?.classList.remove("busy");
  }
  cloneTranscribe(run);
}
// Auto-transcribe new clips with faster-whisper; edits are saved per clip and kept.
async function cloneTranscribe(run) {
  if (!clone.draft?.clips?.some((c) => !("text" in c))) return;
  const box = $("#clone-clips-msg");
  if (box && box.className === "muted") box.textContent += t(" · transcribing…");
  try {
    const d = await api(`/api/clone/drafts/${clone.draft.id}/transcribe`, { method: "POST" });
    if (run !== processing) return;
    clone.draft = d;
    renderClips();
  } catch (e) {
    if (box) { box.className = "error"; box.textContent = t("Transcription failed: {m}", { m: e.message }); }
  }
}
async function cloneSaveText(name, text, ta) {
  try {
    clone.draft = await api(`/api/clone/drafts/${clone.draft.id}/clips/${encodeURIComponent(name)}/text`,
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    ta.classList.add("saved");
    setTimeout(() => ta.classList.remove("saved"), 1200);
  } catch (e) {
    const box = $("#clone-clips-msg");
    if (box) { box.className = "error"; box.textContent = t("Could not save transcript: {m}", { m: e.message }); }
  }
}
const ISSUE_TEXT = {
  short: "Only {seconds} s of speech. Add more: at least 20 s, ideally 1–3 minutes.",
  below_ideal: "{seconds} s of speech. It works, but 1–3 minutes gives a closer match.",
  noise: "{file}: background noise is noticeable ({snr_db} dB SNR). Record in a quieter place if you can.",
  noise_high: "{file}: background noise is high ({snr_db} dB SNR). Record in a quieter place if you can.",
  clipping: "{file}: audio is distorted (clipping). Record a little further from the mic.",
  quiet: "{file}: very quiet recording. Move closer to the mic.",
};
const issueText = (w) => (typeof w === "string" ? w : t(ISSUE_TEXT[w.code] || w.code, w));
function renderQuality() {
  const box = $("#clone-quality");
  if (!box) return;
  const q = clone.draft?.quality;
  if (!q || !clone.draft.files.length) { box.replaceChildren(); return; }
  const label = t({ good: "Good", ok: "Okay", poor: "Poor" }[q.level]);
  box.replaceChildren(
    h("div", { class: "qrow" },
      h("strong", {}, t("Quality")),
      h("div", { class: `qmeter ${q.level}`, role: "meter", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": q.score },
        h("div", { style: `width:${q.score}%` })),
      h("span", { class: `qlabel ${q.level}` }, `${label} · ${q.score}/100`)),
    h("div", { class: "muted small" }, t("{t} of speech (ideal 1–3 min) · noise: {snr} dB SNR", { t: fmtSec(q.seconds), snr: q.snr_db })),
    q.warnings.length ? h("ul", { class: "qwarn" }, (q.issues || q.warnings).map((w) => h("li", { class: "warn" }, issueText(w)))) : null);
}
function renderClips() {
  renderQuality();
  renderDetails();
  const list = $("#clone-clips");
  if (!list) return;
  const d = clone.draft, clips = d?.clips || [];
  const box = $("#clone-clips-msg");
  box.className = d?.clean_errors?.length ? "warn" : "muted";
  box.textContent = d?.clean_errors?.length
    ? t("Skipped: {list}", { list: d.clean_errors.map((e) => `${e.file} (${e.error})`).join(", ") })
    : clips.length ? t("{n} clip(s) · {t} of clean speech", { n: clips.length, t: fmtSec(d.clean_seconds) }) : t("Clips appear here after you add samples.");
  list.replaceChildren(...clips.map((c) => h("li", { class: "file clip" },
    h("span", { class: "fname" }, c.name),
    h("span", { class: "muted" }, fmtSec(c.seconds) + (c.language ? ` · ${c.language}` : "")),
    h("audio", { controls: true, preload: "none", src: `/api/clone/drafts/${d.id}/clips/${c.name}?v=${c.hash || d.clean_seconds}` }),
    h("textarea", { class: "transcript", rows: 2, maxlength: 1000, "aria-label": t("Transcript of {name}", { name: c.name }),
      placeholder: "text" in c ? t("No speech recognised — type what is said") : t("Transcribing…"), disabled: !("text" in c),
      onchange: (e) => cloneSaveText(c.name, e.target.value, e.target) }, c.text || ""))));
}
function renderCloneFiles() {
  const list = $("#clone-files");
  if (!list) return;
  const files = clone.draft?.files || [];
  $("#clone-total").textContent = files.length ? t("{n} file(s) · {t} total", { n: files.length, t: fmtSec(clone.draft.total_seconds) }) : "";
  list.replaceChildren(...files.map((f) => h("li", { class: "file" },
    h("span", { class: "fname", title: f.original }, f.original || f.name),
    h("span", { class: "muted" }, `${f.source === "mic" ? "🎙 " : ""}${fmtSec(f.seconds)}`),
    h("audio", { controls: true, preload: "none", src: `/api/clone/drafts/${clone.draft.id}/files/${encodeURIComponent(f.name)}` }),
    h("button", { class: "ghost small", title: t("Remove"), "aria-label": t("Remove {name}", { name: f.original }), onclick: () => cloneRemove(f.name) }, "✕"),
  )));
}
// Mic recording: MediaRecorder → WebM/Opus (or the browser's default) → uploaded as source=mic.
const rec = { media: null, stream: null, chunks: [], start: 0, timer: null, count: 0, analyser: null };
function recPickType() {
  const types = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"];
  return types.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || "";
}
async function recStart() {
  const msg = $("#clone-msg");
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    msg.className = "error";
    msg.textContent = t("This browser cannot record audio here. Open the page at http://localhost:8765 (mic needs localhost or HTTPS).");
    return;
  }
  try {
    rec.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  } catch (e) {
    msg.className = "error";
    msg.textContent = e.name === "NotAllowedError" ? t("Microphone access was blocked. Allow it in the browser and try again.")
      : t("Cannot open the microphone: {m}", { m: e.message });
    return;
  }
  const type = recPickType();
  rec.media = new MediaRecorder(rec.stream, type ? { mimeType: type, audioBitsPerSecond: 128000 } : {});
  rec.chunks = [];
  rec.media.ondataavailable = (e) => e.data.size && rec.chunks.push(e.data);
  rec.media.onstop = recFinish;
  rec.media.start(250);
  rec.start = performance.now();
  const ctx = new AudioContext();
  rec.ctx = ctx;
  rec.analyser = ctx.createAnalyser();
  rec.analyser.fftSize = 1024;
  ctx.createMediaStreamSource(rec.stream).connect(rec.analyser);
  rec.timer = setInterval(recTick, 100);
  msg.className = "muted";
  msg.textContent = t("Recording… read naturally in one voice, in a quiet room.");
  renderRec();
}
function recTick() {
  const t = (performance.now() - rec.start) / 1000;
  const time = $("#rec-time");
  if (time) time.textContent = fmtSec(t);
  const buf = new Float32Array(rec.analyser.fftSize);
  rec.analyser.getFloatTimeDomainData(buf);
  const peak = buf.reduce((m, x) => Math.max(m, Math.abs(x)), 0);
  const bar = $("#rec-level");
  if (bar) bar.style.width = `${Math.min(100, peak * 100)}%`;
}
function recStop() {
  if (rec.media?.state === "recording") rec.media.stop();
}
async function recFinish() {
  clearInterval(rec.timer);
  rec.stream.getTracks().forEach((t) => t.stop());
  rec.ctx?.close();
  const type = rec.media.mimeType || "audio/webm";
  const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
  const blob = new Blob(rec.chunks, { type });
  rec.media = null;
  renderRec();
  rec.count += 1;
  await cloneUpload([new File([blob], `${t("Recording {n}", { n: rec.count })}.${ext}`, { type })], "mic");
}
function renderRec() {
  const box = $("#clone-rec");
  if (!box) return;
  const on = rec.media?.state === "recording";
  box.replaceChildren(h("div", { class: "rec" },
    on ? h("button", { id: "rec-stop", class: "rec-btn on", onclick: recStop }, t("■ Stop"))
       : h("button", { id: "rec-start", class: "rec-btn ghost", onclick: recStart }, t("● Record from microphone")),
    on ? h("span", { id: "rec-time", class: "rec-time" }, "0:00") : null,
    on ? h("div", { class: "meter", title: t("Input level") }, h("div", { id: "rec-level" })) : null));
}

// Details, preview and save. Save unlocks after a preview of the current clips.
const detailsKey = (d) => (d?.clips || []).map((c) => c.hash).join("|");
function renderDetails() {
  const box = $("#clone-details");
  if (!box) return;
  const d = clone.draft, ready = !!d?.clips?.length;
  box.classList.toggle("disabled", !ready);
  const lang = $("#voice-lang");
  if (lang && d?.language && !lang.dataset.touched) lang.value = d.language;
  const fresh = ready && clone.previewKey === detailsKey(d);
  $("#voice-save").disabled = !(fresh && $("#voice-name").value.trim() && $("#voice-consent").checked);
  $("#voice-preview").disabled = !ready || clone.previewing;
  $("#voice-hint").textContent = t(!ready ? "Add samples first."
    : !fresh ? "Listen to a preview before you save."
    : !$("#voice-name").value.trim() ? "Give the voice a name."
    : !$("#voice-consent").checked ? "Confirm you have the right to clone this voice." : "Ready to save.");
}
async function clonePreview() {
  const msg = $("#voice-msg"), player = $("#voice-audio");
  const key = detailsKey(clone.draft);
  clone.previewing = true;
  renderDetails();
  msg.className = "muted";
  msg.textContent = t("Generating preview… (the first one loads the model and can take a minute)");
  try {
    const r = await request(`/api/clone/drafts/${clone.draft.id}/preview`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("#voice-ptext").value, language: $("#voice-lang").value, engine: $("#voice-engine").value }) });
    if (player.src) URL.revokeObjectURL(player.src);
    player.src = URL.createObjectURL(await r.blob());
    player.hidden = false;
    player.play().catch(() => {});                 // autoplay may be blocked; controls stay visible
    clone.previewKey = key;
    msg.className = "ok";
    msg.textContent = t("Preview ready.");
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Preview failed: {m}", { m: e.message });
  } finally {
    clone.previewing = false;
    renderDetails();
  }
}
async function cloneSave() {
  const msg = $("#voice-msg");
  msg.className = "muted";
  msg.textContent = t("Saving…");
  try {
    const v = await api(`/api/clone/drafts/${clone.draft.id}/save`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#voice-name").value, language: $("#voice-lang").value,
        description: $("#voice-desc").value, tags: $("#voice-tags").value, engine: $("#voice-engine").value,
        consent: $("#voice-consent").checked }) });
    store.set("clone-draft", null);                // next sample starts a new draft
    clone.draft = null;
    clone.previewKey = null;
    route();
    const done = $("#clone-msg");
    done.className = "ok";
    done.replaceChildren(t("Saved “{name}” to My Voices (ID {id}). ", { name: v.name, id: v.id }), h("a", { href: "#voices" }, t("Open My Voices")));
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Save failed: {m}", { m: e.message });
  }
}
function detailsCard() {
  const field = (label, input) => h("label", { class: "field" }, h("span", {}, t(label)), input);
  const on = { oninput: renderDetails, onchange: renderDetails };
  return h("div", { class: "card", id: "clone-details" }, h("h2", {}, t("3 · Details & preview")),
    h("div", { class: "grid2" },
      field("Name", h("input", { id: "voice-name", maxlength: 80, placeholder: t("e.g. My narrator voice"), ...on })),
      field("Language", h("select", { id: "voice-lang", onchange: (e) => { e.target.dataset.touched = 1; } },
        h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
      field("Tags (comma separated)", h("input", { id: "voice-tags", maxlength: 300, placeholder: t("warm, narrator") })),
      field("Engine", h("select", { id: "voice-engine" },
        h("option", { value: "xtts" }, t("XTTS-v2 (recommended)")), h("option", { value: "f5" }, "F5-TTS")))),
    field("Description", h("textarea", { id: "voice-desc", rows: 2, maxlength: 500, placeholder: t("Optional") })),
    field("Preview text", h("input", { id: "voice-ptext", maxlength: 300, placeholder: t("Leave empty for a standard sentence") })),
    h("div", { class: "actions" },
      h("button", { id: "voice-preview", class: "ghost", onclick: clonePreview }, t("▶ Preview")),
      h("audio", { id: "voice-audio", controls: true, hidden: true })),
    h("label", { class: "check" }, h("input", { type: "checkbox", id: "voice-consent", ...on }),
      " " + t("This is my voice, or I have permission from the speaker to clone it.")),
    h("div", { class: "actions" },
      h("button", { id: "voice-save", onclick: cloneSave }, t("Save voice")),
      h("span", { id: "voice-hint", class: "muted small" })),
    h("p", { id: "voice-msg", class: "muted" }));
}

views.clone = (el) => {
  const input = h("input", { type: "file", id: "clone-input", accept: "audio/*,video/webm,.wav,.mp3,.m4a,.ogg,.opus,.flac,.webm", multiple: true, hidden: true,
    onchange: (e) => { cloneUpload([...e.target.files]); e.target.value = ""; } });
  const drop = h("div", { id: "dropzone", class: "dropzone", tabindex: 0, role: "button",
    onclick: () => input.click(), onkeydown: (e) => (e.key === "Enter" || e.key === " ") && input.click(),
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
    ondragleave: () => drop.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); cloneUpload([...e.dataTransfer.files]); } },
    h("div", { class: "big" }, t("Drop audio files here")),
    h("div", { class: "muted" }, t("or click to browse · WAV, MP3, M4A, OGG, FLAC, WebM · 1–3 minutes of clean speech is ideal")));
  el.append(
    h("h1", {}, t("Clone Voice")), cloneTabs("clone"),
    h("p", { class: "sub" }, t("Add samples of one speaker. Only clone voices you own or have permission to use.")),
    h("div", { class: "card" }, h("h2", {}, t("1 · Add samples")), drop, input,
      h("div", { id: "clone-rec" }),
      h("p", { id: "clone-msg", class: "muted" })),
    h("div", { class: "card" }, h("h2", {}, t("Samples"), " ", h("span", { id: "clone-total", class: "muted" })),
      h("ul", { id: "clone-files", class: "files" })),
    h("div", { class: "card" }, h("h2", {}, t("2 · Cleaned clips")),
      h("p", { class: "muted small" }, t("Automatic: mono WAV, silence trimmed, noise reduced, volume levelled, split into 6–15 s clips.")),
      h("div", { id: "clone-quality", class: "quality" }),
      h("p", { id: "clone-clips-msg", class: "muted" }),
      h("ul", { id: "clone-clips", class: "files" })),
    detailsCard(),
  );
  renderRec();
  renderCloneFiles();
  renderClips();
  cloneRestore();
};

function cloneTabs(active) {
  return h("div", { class: "tabs", role: "tablist" },
    h("a", { href: "#clone", role: "tab", class: active === "clone" ? "active" : null, "aria-selected": String(active === "clone") }, t("From samples")),
    h("a", { href: "#blend", role: "tab", class: active === "blend" ? "active" : null, "aria-selected": String(active === "blend") }, t("Blend two voices")));
}

// ---------- Blend two voices (XTTS latents, ratio = share of voice A)
const blendState = { key: null };
function blendBody() {
  return { a: $("#blend-a").value, b: $("#blend-b").value, ratio: Number($("#blend-ratio").value) / 100,
    language: $("#blend-lang").value, text: $("#blend-ptext").value, name: $("#blend-name").value,
    description: $("#blend-desc").value, tags: $("#blend-tags").value };
}
const blendKey = (b) => `${b.a}|${b.b}|${b.ratio}`;
function renderBlend() {
  const b = blendBody(), pct = Math.round(b.ratio * 100);
  $("#blend-ratio-label").textContent = t("{a}% A · {b}% B", { a: pct, b: 100 - pct });
  const two = b.a && b.b && b.a !== b.b;
  const fresh = two && blendState.key === blendKey(b);
  $("#blend-preview").disabled = !two || blendState.busy;
  $("#blend-save").disabled = !fresh || !b.name.trim() || blendState.busy;
  $("#blend-hint").textContent = t(!two ? "Pick two different voices." : !fresh ? "Listen to a preview before you save."
    : !b.name.trim() ? "Give the blend a name." : "Ready to save.");
}
async function blendPreview() {
  const msg = $("#blend-msg"), player = $("#blend-audio"), body = blendBody();
  blendState.busy = true;
  renderBlend();
  msg.className = "muted";
  msg.textContent = t("Generating preview… (the first one loads the model and can take a minute)");
  try {
    const r = await request("/api/blend/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (player.src) URL.revokeObjectURL(player.src);
    player.src = URL.createObjectURL(await r.blob());
    player.hidden = false;
    player.play().catch(() => {});
    blendState.key = blendKey(body);
    msg.className = "ok";
    msg.textContent = t("Preview ready.");
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Preview failed: {m}", { m: e.message });
  } finally {
    blendState.busy = false;
    renderBlend();
  }
}
async function blendSave() {
  const msg = $("#blend-msg");
  blendState.busy = true;
  renderBlend();
  msg.className = "muted";
  msg.textContent = t("Saving…");
  try {
    const v = await api("/api/blend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(blendBody()) });
    msg.className = "ok";
    msg.replaceChildren(t("Saved “{name}” to My Voices (ID {id}). ", { name: v.name, id: v.id }), h("a", { href: "#voices" }, t("Open My Voices")));
    blendState.key = null;
    $("#blend-name").value = "";
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Save failed: {m}", { m: e.message });
  } finally {
    blendState.busy = false;
    renderBlend();
  }
}
views.blend = async (el) => {
  const field = (label, input) => h("label", { class: "field" }, h("span", {}, t(label)), input);
  const on = { oninput: renderBlend, onchange: renderBlend };
  const pick = (id) => h("select", { id, ...on }, h("option", { value: "" }, t("Loading voices…")));
  el.append(
    h("h1", {}, t("Clone Voice")), cloneTabs("blend"),
    h("p", { class: "sub" }, t("Mix two voices into a new one. Works with cloned voices and XTTS library voices.")),
    h("div", { class: "card" },
      h("div", { class: "grid2" }, field("Voice A", pick("blend-a")), field("Voice B", pick("blend-b"))),
      field("Mix", h("div", { class: "slider" },
        h("input", { type: "range", id: "blend-ratio", min: 5, max: 95, step: 5, value: 70, "aria-label": t("Share of voice A"), ...on }),
        h("span", { id: "blend-ratio-label", class: "pill" }))),
      h("div", { class: "grid2" },
        field("Language", h("select", { id: "blend-lang" }, h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
        field("Preview text", h("input", { id: "blend-ptext", maxlength: 300, placeholder: t("Leave empty for a standard sentence") }))),
      h("div", { class: "actions" },
        h("button", { id: "blend-preview", class: "ghost", onclick: blendPreview }, t("▶ Preview")),
        h("audio", { id: "blend-audio", controls: true, hidden: true }))),
    h("div", { class: "card" }, h("h2", {}, t("Save blend")),
      h("div", { class: "grid2" },
        field("Name", h("input", { id: "blend-name", maxlength: 80, placeholder: t("e.g. Warm narrator blend"), ...on })),
        field("Tags (comma separated)", h("input", { id: "blend-tags", maxlength: 300 }))),
      field("Description", h("textarea", { id: "blend-desc", rows: 2, maxlength: 500, placeholder: t("Optional") })),
      h("div", { class: "actions" },
        h("button", { id: "blend-save", onclick: blendSave }, t("Save blend")),
        h("span", { id: "blend-hint", class: "muted small" })),
      h("p", { id: "blend-msg", class: "muted" })));
  renderBlend();
  try {
    const list = await api("/api/blend/sources");
    const opts = (sel) => [h("option", { value: "" }, t("Choose a voice…")),
      ...["mine", "library"].map((o) => {
        const items = list.filter((v) => v.origin === o);
        return items.length ? h("optgroup", { label: t(o === "mine" ? "My Voices" : "Voice Library") },
          items.map((v) => h("option", { value: v.id, selected: v.id === sel ? true : null }, `${v.name} · ${v.language}`))) : null;
      })];
    $("#blend-a")?.replaceChildren(...opts());
    $("#blend-b")?.replaceChildren(...opts());
  } catch (e) {
    $("#blend-msg").className = "error";
    $("#blend-msg").textContent = t("Could not load voices: {m}", { m: e.message });
  }
  if ($("#blend-a")) renderBlend();
};

// ---- Waveform player: play/pause, waveform drawn from the decoded audio, click/drag/keys to seek.
const fmtTime = (x) => (isFinite(x) ? `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}` : "0:00");
async function wavePeaks(src, n = 1200) {
  const buf = await (await request(src)).arrayBuffer();
  const audio = await new OfflineAudioContext(1, 1, 44100).decodeAudioData(buf);
  const data = audio.getChannelData(0);
  const step = Math.max(1, Math.floor(data.length / n));
  const peaks = new Float32Array(Math.ceil(data.length / step));
  for (let i = 0; i < peaks.length; i++) {
    let m = 0;
    for (let j = i * step, end = Math.min(data.length, j + step); j < end; j++) m = Math.max(m, Math.abs(data[j]));
    peaks[i] = m;
  }
  const top = Math.max(...peaks) || 1;
  return peaks.map((p) => p / top);
}
function waveformPlayer(src, id) {
  const audio = h("audio", { id, src, preload: "auto" });
  const canvas = h("canvas", { class: "wave", role: "slider", tabindex: 0, "aria-label": t("Playback position"),
    "aria-valuemin": 0, "aria-valuemax": 0, "aria-valuenow": 0 });
  const btn = h("button", { type: "button", class: "wave-play", "aria-label": t("Play") }, "▶");
  const time = h("span", { class: "wave-time muted small" }, "0:00 / 0:00");
  const box = h("div", { class: "wave-player" }, btn, canvas, time, audio);
  let peaks = null;
  function draw() {
    const w = canvas.clientWidth, ht = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
    if (!w) return;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(ht * dpr); }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, ht);
    const css = getComputedStyle(document.documentElement);
    const done = audio.duration ? audio.currentTime / audio.duration : 0;
    const bars = Math.floor(w / 3);
    for (let i = 0; i < bars; i++) {
      const p = peaks ? peaks[Math.floor((i / bars) * peaks.length)] : 0.04;
      const bh = Math.max(2, p * (ht - 4));
      ctx.fillStyle = i / bars < done ? css.getPropertyValue("--accent") : css.getPropertyValue("--line");
      ctx.fillRect(i * 3, (ht - bh) / 2, 2, bh);
    }
    time.textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
    canvas.setAttribute("aria-valuemax", Math.round(audio.duration || 0));
    canvas.setAttribute("aria-valuenow", Math.round(audio.currentTime));
    canvas.setAttribute("aria-valuetext", time.textContent);
  }
  const seek = (sec) => { if (audio.duration) { audio.currentTime = Math.min(audio.duration, Math.max(0, sec)); draw(); } };
  const seekAt = (e) => { const r = canvas.getBoundingClientRect(); seek(((e.clientX - r.left) / r.width) * audio.duration); };
  let frame;
  const loop = () => { draw(); if (!audio.paused) frame = requestAnimationFrame(loop); };
  btn.addEventListener("click", () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()));
  audio.addEventListener("play", () => { btn.textContent = "❚❚"; btn.setAttribute("aria-label", t("Pause")); cancelAnimationFrame(frame); loop(); });
  audio.addEventListener("pause", () => { btn.textContent = "▶"; btn.setAttribute("aria-label", t("Play")); draw(); });
  for (const ev of ["loadedmetadata", "seeked", "ended"]) audio.addEventListener(ev, draw);
  canvas.addEventListener("pointerdown", (e) => { canvas.setPointerCapture(e.pointerId); seekAt(e); });
  canvas.addEventListener("pointermove", (e) => { if (canvas.hasPointerCapture(e.pointerId)) seekAt(e); });
  canvas.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, PageDown: -5, PageUp: 5 }[e.key];
    if (step) seek(audio.currentTime + step);
    else if (e.key === "Home") seek(0);
    else if (e.key === "End") seek(audio.duration);
    else if (e.key === " ") btn.click();
    else return;
    e.preventDefault();
  });
  new ResizeObserver(draw).observe(canvas);
  wavePeaks(src).then((p) => { peaks = p; box.dataset.ready = "1"; draw(); })
    .catch(() => { box.dataset.ready = "error"; });        // the player still works without the picture
  return box;
}

// ---- Text to Speech
const TTS_MAX = 5000;
const TTS_DEFAULTS = { speed: 1, stability: 0.5, expressiveness: 0.5 };
const tts = { text: "", voices: null, voice: null, busy: false, last: null, ...TTS_DEFAULTS };
try { tts.voice = localStorage.getItem("tts-voice"); } catch { /* storage blocked */ }

const voiceLabel = (v) => [v.name, (v.language || "").toUpperCase(), v.accent, v.engine].filter(Boolean).join(" · ");
const voiceShort = (v) => `${v.name} · ${(v.language || "").toUpperCase()}`;
function ttsVoiceOptions() {
  const q = ($("#tts-search")?.value || "").trim().toLowerCase();
  const hit = (v) => !q || [v.name, v.id, v.accent, v.language, v.gender, v.engine, ...(v.tags || [])]
    .filter(Boolean).join(" ").toLowerCase().includes(q);
  const groups = ["mine", "library"].map((o) => {
    const items = (tts.voices || []).filter((v) => v.origin === o && hit(v));
    return items.length ? h("optgroup", { label: t(o === "mine" ? "My Voices" : "Voice Library") },
      items.map((v) => h("option", { value: v.id, selected: v.id === tts.voice ? true : null, title: voiceLabel(v) }, voiceShort(v)))) : null;
  }).filter(Boolean);
  const sel = $("#tts-voice");
  sel.replaceChildren(...(groups.length ? groups : [h("option", { value: "", disabled: true }, t("No voices match your search."))]));
  if (tts.voice && [...sel.options].some((o) => o.value === tts.voice)) sel.value = tts.voice;
  renderTts();
}
function renderTts() {
  const n = $("#tts-text").value.length;
  const count = $("#tts-count");
  count.textContent = t("{n} / {max} characters", { n: n.toLocaleString(), max: TTS_MAX.toLocaleString() });
  count.className = "muted small" + (n > TTS_MAX * 0.9 ? " warn" : "");
  const voice = (tts.voices || []).find((v) => v.id === tts.voice);
  $("#tts-voice-info").textContent = voice ? voiceLabel(voice) : t("Choose a voice.");
  const controls = voice?.controls || ["speed"];
  for (const k of Object.keys(TTS_DEFAULTS)) {
    const input = $(`#tts-${k}`);
    input.disabled = !controls.includes(k);
    input.value = k === "speed" ? tts[k] : Math.round(tts[k] * 100);
    $(`#tts-${k}-val`).textContent = k === "speed" ? `${tts.speed.toFixed(2)}×` : `${Math.round(tts[k] * 100)}%`;
  }
  $("#tts-controls-note").textContent = voice && controls.length === 1
    ? t("This voice's engine ({engine}) supports speed only.", { engine: voice.engine }) : "";
  $("#tts-generate").disabled = tts.busy || !$("#tts-text").value.trim() || !voice;
  $("#tts-generate").textContent = tts.busy ? t("Generating…") : t("Generate");
}
function ttsBody(text) {
  const controls = (tts.voices || []).find((v) => v.id === tts.voice)?.controls || ["speed"];
  const body = { text, voice: tts.voice, language: $("#tts-lang").value, speed: tts.speed };
  for (const k of ["stability", "expressiveness"]) if (controls.includes(k)) body[k] = tts[k];
  return body;
}
async function ttsGenerate() {
  const text = $("#tts-text").value.trim();
  if (tts.busy || !text || !tts.voice) return;
  const msg = $("#tts-msg");
  tts.busy = true;
  renderTts();
  msg.className = "muted";
  msg.textContent = t("Generating speech… (the first request loads the model and can take a minute)");
  try {
    const e = await api("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ttsBody(text)) });
    tts.last = e;
    msg.className = "ok";
    msg.textContent = t("Done · {s} s · saved to History", { s: e.seconds.toFixed(1) });
    renderTtsResult(true);
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Generation failed: {m}", { m: e.message });
  } finally {
    tts.busy = false;
    if ($("#tts-generate")) renderTts();
  }
}
const DOWNLOADS = [["mp3", "MP3"], ["wav", "WAV"], ["ogg_opus", "OGG (WhatsApp voice note)"]];
function renderTtsResult(play = false) {
  const box = $("#tts-result");
  if (!box || !tts.last) return;
  const e = tts.last;
  const player = waveformPlayer(`/api/history/${e.id}/audio`, "tts-audio");
  box.replaceChildren(h("div", { class: "muted small" }, `${e.voice_name} · ${e.text.slice(0, 80)}${e.text.length > 80 ? "…" : ""}`), player,
    h("div", { class: "downloads" }, h("span", { class: "muted small" }, t("Download")),
      DOWNLOADS.map(([fmt, label]) => h("a", { class: "btn ghost small", "data-format": fmt, download: "",
        href: `/api/history/${e.id}/audio?format=${fmt}&download=true` }, t(label)))),
    h("div", { class: "downloads" }, h("span", { class: "muted small" }, t("Subtitles")),
      ["srt", "vtt"].map((fmt) => h("a", { class: "btn ghost small", "data-subs": fmt, download: "",
        title: t("Timed subtitles, one line per sentence"),
        href: `/api/history/${e.id}/subtitles?format=${fmt}&download=true` }, fmt.toUpperCase()))));
  box.hidden = false;
  if (play) $("audio", player).play().catch(() => {});      // autoplay may be blocked; the player is still there
}
// Text tag buttons: pauses go in at the cursor; a style wraps the selection ([happy]…[normal]) or starts there.
const TTS_TAGS = [
  ["[pause 0.5s]", "Pause 0.5 s", "Insert a 0.5 second pause"], ["[pause 1s]", "Pause 1 s", "Insert a 1 second pause"],
  ["[slow]", "Slow", "Speak slower from here"], ["[fast]", "Fast", "Speak faster from here"],
  ["[whisper]", "Whisper", "Whisper from here"], ["[happy]", "Happy", "Sound happy from here"],
  ["[sad]", "Sad", "Sound sad from here"], ["[excited]", "Excited", "Sound excited from here"],
  ["[normal]", "Normal", "Back to the normal voice"],
];
function ttsInsertTag(tag) {
  const ta = $("#tts-text");
  const { selectionStart: a, selectionEnd: b, value } = ta;
  const pad = (str, i) => (i > 0 && !/\s/.test(value[i - 1]) ? " " : "") + str;
  const wrap = a !== b && !tag.startsWith("[pause") && tag !== "[normal]";
  const tail = /\s/.test(value[b] || "") ? "" : " ";                 // no double spaces
  const ins = wrap ? `${pad(tag, a)} ${value.slice(a, b).trim()} [normal]${tail}` : `${pad(tag, b)}${tail}`;
  if (value.length - (wrap ? b - a : 0) + ins.length > TTS_MAX) {
    $("#tts-msg").className = "error";
    $("#tts-msg").textContent = t("No room for the tag: the text is at the {max} character limit.", { max: TTS_MAX.toLocaleString() });
    return;
  }
  if (wrap) ta.setRangeText(ins, a, b, "end");
  else ta.setRangeText(ins, b, b, "end");
  ta.focus();
  tts.text = ta.value;
  renderTts();
}
function ttsSlider(key, label, min, max, step, lo, hi) {
  return h("div", { class: "field tts-slider" },
    h("div", { class: "tts-slider-head" }, h("label", { for: `tts-${key}` }, t(label)), h("span", { id: `tts-${key}-val`, class: "pill" })),
    h("input", { id: `tts-${key}`, type: "range", min, max, step,
      oninput: (e) => { tts[key] = key === "speed" ? Number(e.target.value) : Number(e.target.value) / 100; renderTts(); } }),
    h("div", { class: "tts-slider-ends muted small" }, h("span", {}, t(lo)), h("span", {}, t(hi))));
}
views.tts = async (el) => {
  const text = h("textarea", { id: "tts-text", class: "tts-text", maxlength: TTS_MAX, "aria-label": t("Text to speak"),
    placeholder: t("Type or paste the text you want to hear…"),
    oninput: (e) => { tts.text = e.target.value; renderTts(); },
    onkeydown: (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ttsGenerate(); } });
  text.value = tts.text;
  const field = (label, input) => h("label", { class: "field" }, h("span", {}, t(label)), input);
  el.append(
    h("h1", {}, t("Text to Speech")),
    h("p", { class: "sub" }, t("Turn text into speech with any voice. Spanish and English, even mixed.")),
    h("div", { class: "tts-grid" },
      h("div", { class: "card tts-main" }, text,
        h("div", { class: "tts-tags", role: "toolbar", "aria-label": t("Text tags") },
          TTS_TAGS.map(([tag, label, title]) => h("button", { type: "button", class: "ghost small", "data-tag": tag,
            title: `${t(title)} · ${tag}`, onmousedown: (e) => e.preventDefault(), onclick: () => ttsInsertTag(tag) }, t(label)))),
        h("div", { class: "tts-bar" }, h("span", { id: "tts-count", class: "muted small" }),
          h("span", { class: "muted small" }, t("Ctrl+Enter to generate"))),
        h("div", { class: "actions" }, h("button", { id: "tts-generate", onclick: ttsGenerate }, t("Generate")),
          h("span", { id: "tts-msg", role: "status" })),
        h("div", { id: "tts-result", class: "tts-result", hidden: true })),
      h("div", { class: "card tts-side" },
        field("Voice", h("input", { id: "tts-search", type: "search", placeholder: t("Search voices…"),
          autocomplete: "off", oninput: ttsVoiceOptions })),
        h("select", { id: "tts-voice", class: "tts-voice", size: 8, "aria-label": t("Voice"),
          onchange: (e) => { tts.voice = e.target.value; tts.picked = true; try { localStorage.setItem("tts-voice", tts.voice); } catch { /* storage blocked */ } renderTts(); } },
          h("option", { value: "", disabled: true }, t("Loading voices…"))),
        h("div", { id: "tts-voice-info", class: "muted small tts-voice-info" }),
        field("Language", h("select", { id: "tts-lang" },
          h("option", { value: "auto" }, t("Auto-detect (Spanish / English)")),
          h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
        ttsSlider("speed", "Speed", 0.5, 2, 0.05, "Slower", "Faster"),
        ttsSlider("stability", "Stability", 0, 100, 5, "More variable", "More stable"),
        ttsSlider("expressiveness", "Expressiveness", 0, 100, 5, "Calmer", "Livelier"),
        h("div", { class: "actions" }, h("button", { id: "tts-reset", class: "ghost small", onclick: () => {
          Object.assign(tts, TTS_DEFAULTS); renderTts(); } }, t("Reset settings")),
          h("span", { id: "tts-controls-note", class: "muted small" })))));
  renderTts();
  renderTtsResult();
  try {
    tts.voices = await api("/api/voices");
    const def = tts.voices.find((v) => v.default);
    if (def && !tts.picked) tts.voice = def.id;                         // the default voice wins until you pick one
    if (!tts.voices.some((v) => v.id === tts.voice)) tts.voice = (tts.voices.find((v) => v.origin === "mine") || tts.voices[0])?.id || null;
    if ($("#tts-voice")) ttsVoiceOptions();
  } catch (e) {
    $("#tts-msg").className = "error";
    $("#tts-msg").textContent = t("Could not load voices: {m}", { m: e.message });
  }
};

// ---- Voice Changer: your speech (microphone or file) → the same words, timing and emotion in another voice.
const vc = { file: null, url: null, voices: null, voice: null, busy: false, subs: false, last: null, count: 0 };
try { vc.voice = localStorage.getItem("vc-voice"); } catch { /* storage blocked */ }
const VC_EXT = /\.(wav|mp3|m4a|ogg|oga|opus|flac|webm|aac|mp4|mov|mkv)$/i;
function vcSetFile(file) {
  const msg = $("#vc-msg");
  if (file && !/^(audio|video)\//.test(file.type) && !VC_EXT.test(file.name)) {
    msg.className = "error";
    msg.textContent = t("This is not an audio file: {name}", { name: file.name });
    return;
  }
  if (vc.url) URL.revokeObjectURL(vc.url);
  vc.file = file;
  vc.url = file ? URL.createObjectURL(file) : null;
  if (msg) { msg.className = "muted"; msg.textContent = ""; }
  renderVc();
}
const vcRec = { media: null, stream: null, chunks: [], start: 0, timer: null, analyser: null, ctx: null };
async function vcRecStart() {
  const msg = $("#vc-msg");
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    msg.className = "error";
    msg.textContent = t("This browser cannot record audio here. Open the page at http://localhost:8765 (mic needs localhost or HTTPS).");
    return;
  }
  try {
    vcRec.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
  } catch (e) {
    msg.className = "error";
    msg.textContent = e.name === "NotAllowedError" ? t("Microphone access was blocked. Allow it in the browser and try again.")
      : t("Cannot open the microphone: {m}", { m: e.message });
    return;
  }
  const type = recPickType();
  vcRec.media = new MediaRecorder(vcRec.stream, type ? { mimeType: type, audioBitsPerSecond: 128000 } : {});
  vcRec.chunks = [];
  vcRec.media.ondataavailable = (e) => e.data.size && vcRec.chunks.push(e.data);
  vcRec.media.onstop = vcRecFinish;
  vcRec.media.start(250);
  vcRec.start = performance.now();
  vcRec.ctx = new AudioContext();
  vcRec.analyser = vcRec.ctx.createAnalyser();
  vcRec.analyser.fftSize = 1024;
  vcRec.ctx.createMediaStreamSource(vcRec.stream).connect(vcRec.analyser);
  vcRec.timer = setInterval(() => {
    const time = $("#vc-rec-time"), bar = $("#vc-rec-level");
    if (time) time.textContent = fmtSec((performance.now() - vcRec.start) / 1000);
    const buf = new Float32Array(vcRec.analyser.fftSize);
    vcRec.analyser.getFloatTimeDomainData(buf);
    if (bar) bar.style.width = `${Math.min(100, buf.reduce((m, x) => Math.max(m, Math.abs(x)), 0) * 100)}%`;
  }, 100);
  msg.className = "muted";
  msg.textContent = t("Recording… speak naturally.");
  renderVc();
}
function vcRecFinish() {
  clearInterval(vcRec.timer);
  vcRec.stream.getTracks().forEach((tr) => tr.stop());
  vcRec.ctx?.close();
  const type = vcRec.media.mimeType || "audio/webm";
  const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
  vcRec.media = null;
  vc.count += 1;
  vcSetFile(new File([new Blob(vcRec.chunks, { type })], `${t("Recording {n}", { n: vc.count })}.${ext}`, { type }));
}
function vcVoiceOptions() {
  const q = ($("#vc-search")?.value || "").trim().toLowerCase();
  const hit = (v) => !q || [v.name, v.id, v.accent, v.language, v.gender, v.engine, ...(v.tags || [])]
    .filter(Boolean).join(" ").toLowerCase().includes(q);
  const groups = ["mine", "library"].map((o) => {
    const items = (vc.voices || []).filter((v) => v.origin === o && hit(v));
    return items.length ? h("optgroup", { label: t(o === "mine" ? "My Voices" : "Voice Library") },
      items.map((v) => h("option", { value: v.id, selected: v.id === vc.voice ? true : null, title: voiceLabel(v) }, voiceShort(v)))) : null;
  }).filter(Boolean);
  const sel = $("#vc-voice");
  sel.replaceChildren(...(groups.length ? groups : [h("option", { value: "", disabled: true }, t("No voices match your search."))]));
  if (vc.voice && [...sel.options].some((o) => o.value === vc.voice)) sel.value = vc.voice;
  renderVc();
}
function renderVc() {
  const on = vcRec.media?.state === "recording";
  $("#vc-rec")?.replaceChildren(h("div", { class: "rec" },
    on ? h("button", { id: "vc-rec-stop", class: "rec-btn on", onclick: () => vcRec.media.stop() }, t("■ Stop"))
       : h("button", { id: "vc-rec-start", class: "rec-btn ghost", disabled: vc.busy, onclick: vcRecStart }, t("● Record from microphone")),
    on ? h("span", { id: "vc-rec-time", class: "rec-time" }, "0:00") : null,
    on ? h("div", { class: "meter", title: t("Input level") }, h("div", { id: "vc-rec-level" })) : null));
  const src = $("#vc-source");
  if (!src) return;
  src.hidden = !vc.file;
  if (vc.file && src.dataset.url !== vc.url) {
    src.dataset.url = vc.url;
    src.replaceChildren(h("span", { class: "vc-name" }, vc.file.name),
      h("audio", { controls: true, src: vc.url, preload: "metadata", "aria-label": t("Your recording") }),
      h("button", { id: "vc-clear", class: "ghost small", onclick: () => vcSetFile(null) }, t("Remove")));
  }
  if (!vc.file) delete src.dataset.url;
  const voice = (vc.voices || []).find((v) => v.id === vc.voice);
  $("#vc-voice-info").textContent = voice ? voiceLabel(voice) : t("Choose a voice.");
  $("#vc-convert").disabled = vc.busy || vc.subs || on || !vc.file || !voice;
  $("#vc-convert").textContent = vc.busy ? t("Converting…") : t("Convert");
  $("#vc-subs").disabled = vc.busy || vc.subs || on || !vc.file;           // no voice needed
  $("#vc-subs").textContent = vc.subs ? t("Making subtitles…") : t("Subtitles only (SRT)");
}
// Subtitles for the recording itself (Whisper timings): downloads <name>.srt; nothing is converted or saved.
async function vcSubtitles() {
  if (vc.busy || vc.subs || !vc.file) return;
  const msg = $("#vc-msg");
  vc.subs = true;
  renderVc();
  msg.className = "muted";
  msg.textContent = t("Making subtitles…");
  try {
    const form = new FormData();
    form.append("file", vc.file, vc.file.name);
    form.append("language", $("#vc-lang").value);
    form.append("format", "srt");
    const r = await request("/api/subtitles", { method: "POST", body: form });
    const name = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || "subtitles.srt";
    const blob = await r.blob();
    const n = ((await blob.text()).match(/ --> /g) || []).length;
    const a = h("a", { href: URL.createObjectURL(blob), download: name, hidden: true });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
    msg.className = "ok";
    msg.textContent = t("Subtitles downloaded: {name} · {n} lines", { name, n });
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Subtitles failed: {m}", { m: e.message });
  } finally {
    vc.subs = false;
    if ($("#vc-subs")) renderVc();
  }
}
async function vcConvert() {
  if (vc.busy || !vc.file || !vc.voice) return;
  const msg = $("#vc-msg");
  vc.busy = true;
  renderVc();
  msg.className = "muted";
  msg.textContent = t("Converting… (the first time loads the model and can take a minute)");
  try {
    const form = new FormData();
    form.append("file", vc.file, vc.file.name);
    form.append("voice", vc.voice);
    form.append("language", $("#vc-lang").value);
    form.append("format", "wav");                         // the stored file itself: no encoding wait
    const r = await request("/api/voice-changer", { method: "POST", body: form });
    r.body?.cancel().catch(() => {});                     // the player loads the audio from History
    vc.last = await api(`/api/history/${encodeURIComponent(r.headers.get("X-Voicer-Id"))}`);
    msg.className = "ok";
    msg.textContent = t("Done · {s} s · saved to History", { s: vc.last.seconds.toFixed(1) });
    renderVcResult(true);
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Conversion failed: {m}", { m: e.message });
  } finally {
    vc.busy = false;
    if ($("#vc-convert")) renderVc();
  }
}
// The result of a generate: waveform player, audio downloads and subtitle links (Voice Changer, Dialogue).
function renderResult(sel, e, audioId, play = false) {
  const box = $(sel);
  if (!box || !e) return;
  const player = waveformPlayer(`/api/history/${e.id}/audio`, audioId);
  box.replaceChildren(h("div", { class: "muted small" }, `${e.voice_name} · ${e.text.slice(0, 80)}${e.text.length > 80 ? "…" : ""}`), player,
    h("div", { class: "downloads" }, h("span", { class: "muted small" }, t("Download")),
      DOWNLOADS.map(([fmt, label]) => h("a", { class: "btn ghost small", "data-format": fmt, download: "",
        href: `/api/history/${e.id}/audio?format=${fmt}&download=true` }, t(label)))),
    h("div", { class: "downloads" }, h("span", { class: "muted small" }, t("Subtitles")),
      ["srt", "vtt"].map((fmt) => h("a", { class: "btn ghost small", "data-subs": fmt, download: "",
        title: t("Timed subtitles, one line per sentence"),
        href: `/api/history/${e.id}/subtitles?format=${fmt}&download=true` }, fmt.toUpperCase()))));
  box.hidden = false;
  if (play) $("audio", player).play().catch(() => {});      // autoplay may be blocked; the player is still there
}
const renderVcResult = (play = false) => renderResult("#vc-result", vc.last, "vc-audio", play);
views.changer = async (el) => {
  const input = h("input", { type: "file", id: "vc-input", hidden: true,
    accept: "audio/*,video/*,.wav,.mp3,.m4a,.ogg,.opus,.flac,.webm,.aac,.mp4,.mov,.mkv",
    onchange: (e) => { if (e.target.files[0]) vcSetFile(e.target.files[0]); e.target.value = ""; } });
  const drop = h("div", { id: "vc-drop", class: "dropzone", tabindex: 0, role: "button",
    onclick: () => input.click(), onkeydown: (e) => (e.key === "Enter" || e.key === " ") && input.click(),
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
    ondragleave: () => drop.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) vcSetFile(e.dataTransfer.files[0]); } },
    h("div", { class: "big" }, t("Drop a recording here")),
    h("div", { class: "muted" }, t("or click to browse · audio or video · 0.5 s to 5 min")));
  const field = (label, ctl) => h("label", { class: "field" }, h("span", {}, t(label)), ctl);
  el.append(
    h("h1", {}, t("Voice Changer")),
    h("p", { class: "sub" }, t("Speak or upload a recording. Hear the same words, timing and emotion in another voice.")),
    h("div", { class: "tts-grid" },
      h("div", { class: "card tts-main" }, h("h2", {}, t("1 · Your speech")), drop, input,
        h("div", { id: "vc-rec" }),
        h("div", { id: "vc-source", class: "vc-source", hidden: true }),
        h("div", { class: "actions" }, h("button", { id: "vc-convert", onclick: vcConvert }, t("Convert")),
          h("button", { id: "vc-subs", class: "ghost", onclick: vcSubtitles,
            title: t("Make timed subtitles of the recording as it is, without changing the voice (up to 10 min).") },
            t("Subtitles only (SRT)")),
          h("span", { id: "vc-msg", role: "status" })),
        h("div", { id: "vc-result", class: "tts-result", hidden: true })),
      h("div", { class: "card tts-side" }, h("h2", {}, t("2 · New voice")),
        field("Voice", h("input", { id: "vc-search", type: "search", placeholder: t("Search voices…"),
          autocomplete: "off", oninput: vcVoiceOptions })),
        h("select", { id: "vc-voice", class: "tts-voice", size: 8, "aria-label": t("Voice"),
          onchange: (e) => { vc.voice = e.target.value; try { localStorage.setItem("vc-voice", vc.voice); } catch { /* storage blocked */ } renderVc(); } },
          h("option", { value: "", disabled: true }, t("Loading voices…"))),
        h("div", { id: "vc-voice-info", class: "muted small tts-voice-info" }),
        field("Language of the recording", h("select", { id: "vc-lang" },
          h("option", { value: "auto" }, t("Auto-detect (Spanish / English)")),
          h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
        h("p", { class: "muted small" }, t("Only use voices you own or have permission to use. The result is saved to History with subtitles.")))));
  renderVc();
  renderVcResult();
  try {
    vc.voices = await api("/api/voices");
    if (!vc.voices.some((v) => v.id === vc.voice)) vc.voice = (vc.voices.find((v) => v.default) || vc.voices[0])?.id || null;
    if ($("#vc-voice")) vcVoiceOptions();
  } catch (e) {
    $("#vc-msg").className = "error";
    $("#vc-msg").textContent = t("Could not load voices: {m}", { m: e.message });
  }
};

// ---- Dialogue: a script of `Name: text` lines → one audio file, with a voice per speaker.
const DLG_SPEAKER = /^\s*([^:\[\]]{1,40}?)\s*:\s*(.*)$/;          // same rule as dialogue.SPEAKER on the server
const DLG_MAX_SPEAKERS = 10;
const dlg = { script: "", cast: {}, voices: null, busy: false, last: null, gap: 0.4, names: [] };
try { dlg.cast = JSON.parse(localStorage.getItem("dlg-cast") || "{}") || {}; } catch { dlg.cast = {}; }
function dlgNames(script) {        // speaker names in order of first appearance (a name is the same in any case)
  const turns = [], seen = new Map();
  for (const line of script.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const m = DLG_SPEAKER.exec(line);
    if (m && m[1].trim()) {
      const k = m[1].trim().toLowerCase();
      if (!seen.has(k)) seen.set(k, m[1].trim());
      turns.push([seen.get(k), m[2].trim()]);
    } else if (turns.length) turns[turns.length - 1][1] += ` ${line.trim()}`;
  }
  return [...new Set(turns.filter((x) => x[1].trim()).map((x) => x[0]))];
}
function dlgAssign() {             // a new speaker gets an unused voice, a different gender from the speaker before
  const all = dlg.voices || [];
  const byId = (id) => all.find((v) => v.id === id);
  dlg.names.forEach((name, i) => {
    const k = name.toLowerCase();
    if (byId(dlg.cast[k])) return;
    const used = new Set(dlg.names.map((n) => dlg.cast[n.toLowerCase()]));
    const prev = i ? byId(dlg.cast[dlg.names[i - 1].toLowerCase()]) : null;
    const free = all.filter((v) => !used.has(v.id));
    const pick = (prev && free.find((v) => v.gender && v.gender !== prev.gender && v.language === prev.language))
      || (!prev && all.find((v) => v.default)) || free[0] || all[0];
    if (pick) dlg.cast[k] = pick.id;
  });
}
function dlgSaveCast() {
  try { localStorage.setItem("dlg-cast", JSON.stringify(dlg.cast)); } catch { /* storage blocked */ }
}
function dlgVoiceSelect(name, i) {
  const k = name.toLowerCase();
  const groups = ["mine", "library"].map((o) => {
    const items = (dlg.voices || []).filter((v) => v.origin === o);
    return items.length ? h("optgroup", { label: t(o === "mine" ? "My Voices" : "Voice Library") },
      items.map((v) => h("option", { value: v.id, selected: v.id === dlg.cast[k] ? true : null, title: voiceLabel(v) }, voiceShort(v)))) : null;
  });
  return h("select", { id: `dlg-voice-${i}`, "data-speaker": name, "aria-label": t("Voice for {name}", { name }),
    onchange: (e) => { dlg.cast[k] = e.target.value; dlgSaveCast(); } }, groups);
}
function renderDlgCast() {
  const box = $("#dlg-cast");
  if (!box) return;
  const names = dlgNames(dlg.script);
  const changed = names.join("\n") !== dlg.names.join("\n") || !box.dataset.ready;
  dlg.names = names;
  if (dlg.voices && changed) {
    dlgAssign();
    dlgSaveCast();
    box.dataset.ready = "1";
    box.replaceChildren(...(names.length
      ? names.map((n, i) => h("label", { class: "field dlg-speaker" }, h("span", {}, n), dlgVoiceSelect(n, i)))
      : [h("p", { class: "muted small" }, t("Write lines like “Ann: Hello.” Each new name gets its own voice."))]));
  }
  const n = $("#dlg-script").value.length;
  $("#dlg-count").textContent = t("{n} / {max} characters", { n: n.toLocaleString(), max: TTS_MAX.toLocaleString() });
  const many = names.length > DLG_MAX_SPEAKERS;
  $("#dlg-cast-msg").textContent = many ? t("Too many speakers ({n}, max {max})", { n: names.length, max: DLG_MAX_SPEAKERS }) : "";
  $("#dlg-generate").disabled = dlg.busy || !names.length || many || !dlg.voices;
  $("#dlg-generate").textContent = dlg.busy ? t("Generating…") : t("Generate dialogue");
}
async function dlgGenerate() {
  const names = dlgNames(dlg.script);
  if (dlg.busy || !names.length) return;
  const msg = $("#dlg-msg");
  dlg.busy = true;
  renderDlgCast();
  msg.className = "muted";
  msg.textContent = t("Generating speech… (the first request loads the model and can take a minute)");
  try {
    const voices = Object.fromEntries(names.map((n) => [n, dlg.cast[n.toLowerCase()]]));
    const r = await request("/api/dialogue", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script: dlg.script, voices, language: $("#dlg-lang").value, gap: dlg.gap, format: "wav" }) });
    r.body?.cancel().catch(() => {});                     // the player loads the audio from History
    dlg.last = await api(`/api/history/${encodeURIComponent(r.headers.get("X-Voicer-Id"))}`);
    msg.className = "ok";
    msg.textContent = t("Done · {s} s · saved to History", { s: dlg.last.seconds.toFixed(1) });
    renderResult("#dlg-result", dlg.last, "dlg-audio", true);
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Generation failed: {m}", { m: e.message });
  } finally {
    dlg.busy = false;
    if ($("#dlg-generate")) renderDlgCast();
  }
}
views.dialogue = async (el) => {
  const text = h("textarea", { id: "dlg-script", class: "tts-text", maxlength: TTS_MAX, "aria-label": t("Script"),
    placeholder: [t("Ann: Hi Ben! How was the trip?"), t("Ben: Long, but worth it. I saw the sea!"), t("Ann: [happy] Lucky you!")].join("\n"),
    oninput: (e) => { dlg.script = e.target.value; renderDlgCast(); },
    onkeydown: (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) dlgGenerate(); } });
  text.value = dlg.script;
  const gapVal = h("span", { id: "dlg-gap-val", class: "muted small" }, `${dlg.gap.toFixed(1)} s`);
  el.append(
    h("h1", {}, t("Dialogue")),
    h("p", { class: "sub" }, t("Write a conversation, one line per turn: “Name: text”. Each speaker gets a voice. You get one audio file.")),
    h("div", { class: "tts-grid" },
      h("div", { class: "card tts-main" }, text,
        h("div", { class: "tts-bar" }, h("span", { id: "dlg-count", class: "muted small" }),
          h("span", { class: "muted small" }, t("Ctrl+Enter to generate"))),
        h("div", { class: "actions" }, h("button", { id: "dlg-generate", onclick: dlgGenerate }, t("Generate dialogue")),
          h("span", { id: "dlg-msg", role: "status" })),
        h("div", { id: "dlg-result", class: "tts-result", hidden: true })),
      h("div", { class: "card tts-side" }, h("h2", {}, t("Speakers")),
        h("div", { id: "dlg-cast", class: "dlg-cast" }, h("p", { class: "muted small" }, t("Loading voices…"))),
        h("p", { id: "dlg-cast-msg", class: "error small", role: "status" }),
        h("label", { class: "field" }, h("span", {}, t("Language")), h("select", { id: "dlg-lang" },
          h("option", { value: "auto" }, t("Auto-detect (Spanish / English)")),
          h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
        h("label", { class: "field" }, h("span", {}, t("Pause between turns"), " ", gapVal),
          h("input", { id: "dlg-gap", type: "range", min: 0, max: 2, step: 0.1, value: dlg.gap,
            oninput: (e) => { dlg.gap = Number(e.target.value); gapVal.textContent = `${dlg.gap.toFixed(1)} s`; } })))));
  renderDlgCast();
  renderResult("#dlg-result", dlg.last, "dlg-audio");
  try {
    dlg.voices = await api("/api/voices");
    if ($("#dlg-cast")) renderDlgCast();
  } catch (e) {
    $("#dlg-msg").className = "error";
    $("#dlg-msg").textContent = t("Could not load voices: {m}", { m: e.message });
  }
};

// ---- Batch: a .txt / .docx / .csv file → many clips, made one by one (progress bar), then one ZIP.
const bat = { file: null, items: [], results: [], voices: null, voice: null, busy: false, stop: false };
try { bat.voice = localStorage.getItem("batch-voice"); } catch { /* storage blocked */ }
async function batLoad(file) {
  const msg = $("#bat-msg");
  if (bat.busy || !file) return;
  msg.className = "muted";
  msg.textContent = t("Reading {name}…", { name: file.name });
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const r = await api("/api/batch/parse", { method: "POST", body: form });
    Object.assign(bat, { file: file.name, items: r.items, results: [] });
    msg.className = "ok";
    msg.textContent = t("{n} clips found in {name}", { n: r.count, name: file.name });
  } catch (e) {
    Object.assign(bat, { file: null, items: [], results: [] });
    msg.className = "error";
    msg.textContent = t("Cannot read this file: {m}", { m: e.message });
  }
  renderBatList();
  renderBat();
}
function batStatus(i) {
  const r = bat.results[i];
  if (!r) return h("div", { class: "bat-status muted" }, bat.busy && i === bat.results.length ? t("Generating…") : "");
  return r.id ? h("div", { class: "bat-status ok" }, t("Done · {s} s", { s: r.seconds.toFixed(1) }))
    : h("div", { class: "bat-status error" }, r.error);
}
function renderBatList() {
  const list = $("#bat-list");
  if (!list) return;
  list.hidden = !bat.items.length;
  list.replaceChildren(...bat.items.map((it, i) => h("li", { id: `bat-row-${i}` },
    h("span", { class: "muted" }, `${i + 1}`),
    h("div", {}, h("div", { class: "bat-text", title: it.text }, it.name ? h("b", {}, `${it.name} · `) : null, it.text),
      (it.voice || it.language) ? h("div", { class: "muted small" }, [it.voice, it.language?.toUpperCase()].filter(Boolean).join(" · ")) : null,
      batStatus(i)))));
}
function renderBat() {
  if (!$("#bat-start")) return;
  const n = bat.items.length, done = bat.results.length, failed = bat.results.filter((r) => !r.id).length;
  $("#bat-start").disabled = bat.busy || !n || !bat.voices;
  $("#bat-start").textContent = bat.busy ? t("Generating…") : t("Generate {n} clips", { n });
  $("#bat-stop").hidden = !bat.busy;
  $("#bat-zip").hidden = bat.busy || !bat.results.some((r) => r.id);
  $("#bat-drop").classList.toggle("disabled", bat.busy);
  const prog = $("#bat-progress");
  prog.hidden = !bat.busy && !done;
  prog.max = n || 1;
  prog.value = done;
  $("#bat-progress-text").textContent = prog.hidden ? ""
    : t("{done} / {n} clips", { done, n }) + (failed ? ` · ${t("{n} failed", { n: failed })}` : "");
}
async function batRun() {
  if (bat.busy || !bat.items.length) return;
  Object.assign(bat, { busy: true, stop: false, results: [] });
  const fmt = $("#bat-format").value, language = $("#bat-lang").value, msg = $("#bat-msg");
  msg.className = "muted";
  msg.textContent = t("Generating speech… (the first request loads the model and can take a minute)");
  renderBatList();
  renderBat();
  for (const [i, it] of bat.items.entries()) {
    if (bat.stop) break;
    let row;
    try {               // one request per clip, so the bar moves after each clip and Stop takes effect quickly
      const m = await api("/api/batch", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: [it], voice: bat.voice, language, format: fmt }) });
      row = m.items[0];
    } catch (e) {
      row = { status: "error", error: e.message };
    }
    bat.results.push(row.status === "ok" ? { id: row.id, seconds: row.seconds } : { error: row.error });
    const cell = $(`#bat-row-${i} .bat-status`);
    if (cell) cell.replaceWith(batStatus(i));
    $(`#bat-row-${i + 1} .bat-status`)?.replaceWith(batStatus(i + 1));
    renderBat();
  }
  bat.busy = false;
  const ok = bat.results.filter((r) => r.id).length;
  msg.className = ok ? "ok" : "error";
  msg.textContent = (bat.stop ? `${t("Stopped.")} ` : "") + t("{ok} of {n} clips made · saved to History", { ok, n: bat.items.length });
  renderBatList();
  renderBat();
}
async function batZip() {
  const msg = $("#bat-msg"), btn = $("#bat-zip");
  btn.disabled = true;
  try {
    const items = bat.items.map((it, i) => {
      const r = bat.results[i];
      return r?.id ? { id: r.id, name: it.name || null } : { error: r?.error || t("Not generated"), name: it.name || null };
    });
    const r = await request("/api/batch/zip", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, format: $("#bat-format").value }) });
    const url = URL.createObjectURL(await r.blob());
    const stem = (bat.file || "voicer-batch").replace(/\.[^.]+$/, "");
    h("a", { href: url, download: `${stem}.zip` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    msg.className = "error";
    msg.textContent = t("Could not make the ZIP: {m}", { m: e.message });
  } finally {
    btn.disabled = false;
  }
}
views.batch = async (el) => {
  const input = h("input", { type: "file", id: "bat-input", hidden: true, accept: ".txt,.docx,.csv,text/plain,text/csv",
    onchange: (e) => { batLoad(e.target.files[0]); e.target.value = ""; } });
  const drop = h("div", { id: "bat-drop", class: "dropzone", tabindex: 0, role: "button",
    onclick: () => !bat.busy && input.click(), onkeydown: (e) => (e.key === "Enter" || e.key === " ") && !bat.busy && input.click(),
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
    ondragleave: () => drop.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); batLoad(e.dataTransfer.files[0]); } },
    h("div", { class: "big" }, t("Drop a .txt, .docx or .csv file here")),
    h("div", { class: "muted" }, t("or click to browse · up to 100 clips")));
  const field = (label, ctl) => h("label", { class: "field" }, h("span", {}, t(label)), ctl);
  const voiceSel = h("select", { id: "bat-voice", onchange: (e) => {
    bat.voice = e.target.value;
    try { localStorage.setItem("batch-voice", bat.voice); } catch { /* storage blocked */ }
  } }, h("option", { value: "" }, t("Loading voices…")));
  el.append(
    h("h1", {}, t("Batch")),
    h("p", { class: "sub" }, t("Turn a file into many clips at once. Download them all as one ZIP.")),
    h("div", { class: "tts-grid" },
      h("div", { class: "card tts-main" }, drop, input,
        h("ul", { class: "muted small bat-help" },
          h("li", {}, t("TXT: one clip per line.")), h("li", {}, t("DOCX: one clip per paragraph.")),
          h("li", {}, t("CSV: a header row with the column text, and optional voice, language, filename."))),
        h("ol", { id: "bat-list", class: "bat-list", hidden: true }),
        h("progress", { id: "bat-progress", hidden: true }),
        h("div", { id: "bat-progress-text", class: "muted small", role: "status" }),
        h("div", { class: "actions" },
          h("button", { id: "bat-start", onclick: batRun }, t("Generate {n} clips", { n: 0 })),
          h("button", { id: "bat-stop", class: "ghost", hidden: true, onclick: () => { bat.stop = true; } }, t("Stop")),
          h("button", { id: "bat-zip", class: "ghost", hidden: true, onclick: batZip }, t("Download ZIP")),
          h("span", { id: "bat-msg", role: "status" }))),
      h("div", { class: "card tts-side" }, h("h2", {}, t("Settings")),
        h("p", { class: "muted small" }, t("Used for clips that do not set their own.")),
        field("Voice", voiceSel),
        field("Language", h("select", { id: "bat-lang" },
          h("option", { value: "auto" }, t("Auto-detect (Spanish / English)")),
          h("option", { value: "en" }, "English"), h("option", { value: "es" }, "Español"))),
        field("Format", h("select", { id: "bat-format" },
          DOWNLOADS.map(([fmt, label]) => h("option", { value: fmt }, t(label))))),
        h("p", { class: "muted small" }, t("Every clip is also saved to History, with subtitles.")))));
  renderBatList();
  renderBat();
  try {
    bat.voices = await api("/api/voices");
    if (!bat.voices.some((v) => v.id === bat.voice)) bat.voice = (bat.voices.find((v) => v.default) || bat.voices[0])?.id || null;
    voiceSel.replaceChildren(...["mine", "library"].map((o) => {
      const items = bat.voices.filter((v) => v.origin === o);
      return items.length ? h("optgroup", { label: t(o === "mine" ? "My Voices" : "Voice Library") },
        items.map((v) => h("option", { value: v.id, selected: v.id === bat.voice ? true : null, title: voiceLabel(v) }, voiceShort(v)))) : null;
    }).filter(Boolean));
    renderBat();
  } catch (e) {
    $("#bat-msg").className = "error";
    $("#bat-msg").textContent = t("Could not load voices: {m}", { m: e.message });
  }
};

// ---- Voice Library: loads every voice once, filters in the browser (no request per keystroke).
const LIB_FILTERS = [            // [key, label, "any" label, value(s) of a voice]
  ["language", "Language", "Any language", (v) => [v.language]],
  ["accent", "Accent", "Any accent", (v) => [v.accent]],
  ["gender", "Gender", "Any gender", (v) => [v.gender]],
  ["age", "Age", "Any age", (v) => [v.age]],
  ["style", "Style", "Any style", (v) => v.tags || []],
  ["engine", "Engine", "Any engine", (v) => [v.engine]],
  ["license", "License", "Any license", (v) => [v.license_short]],
];
const LIB_VALUES = {             // stored values → labels (translated by t())
  female: "Female", male: "Male", neutral: "Neutral (gender)",
  "young adult": "Young adult", adult: "Adult", "middle-aged": "Middle-aged", senior: "Senior",
  warm: "warm", narrator: "narrator", news: "news", conversational: "conversational", energetic: "energetic",
  calm: "calm", multilingual: "multilingual", kokoro: "Kokoro", piper: "Piper", xtts: "XTTS-v2",
};
const LANG_NAMES = { en: "English", es: "Español" };          // each in its own language, like the TTS picker
const libValue = (key, x) => (key === "language" ? LANG_NAMES[x] || x : t(LIB_VALUES[x] || x));
const lib = { voices: null, q: "", filters: {}, commercial: false };
function libMatches(v) {
  const q = lib.q.trim().toLowerCase();
  if (q && ![v.name, v.id, v.accent, v.description, ...(v.tags || [])].filter(Boolean).join(" ").toLowerCase().includes(q)) return false;
  if (lib.commercial && !v.commercial) return false;
  return LIB_FILTERS.every(([k, , , get]) => !lib.filters[k] || get(v).includes(lib.filters[k]));
}
// One preview clip at a time on card pages (Voice Library, My Voices). A second click stops it.
const preview = { audio: null, id: null };
function previewStop() {
  preview.audio?.pause();
  preview.id = null;
  document.querySelectorAll(".play-btn").forEach((b) => {
    b.textContent = b.dataset.idle || t("▶ Preview"); b.setAttribute("aria-pressed", "false"); });
}
function previewPlay(id, url, btn) {
  const same = preview.id === id;
  previewStop();
  if (same) return;
  preview.audio = preview.audio || new Audio();
  preview.audio.onended = previewStop;
  preview.audio.src = url;
  preview.id = id;
  btn.textContent = t("■ Stop");
  btn.setAttribute("aria-pressed", "true");
  preview.audio.play().catch((e) => { previewStop(); if (e.name !== "AbortError") toast(t("Could not play the preview: {m}", { m: e.message })); });
}
async function libAdd(v, btn) {
  btn.disabled = true;
  btn.textContent = t("Adding…");
  try {
    const mine = await api(`/api/library/${encodeURIComponent(v.id)}/add`, { method: "POST" });
    v.added = true;
    toast(t("Added “{name}” to My Voices.", { name: mine.name }), "ok");
  } catch (e) {
    toast(t("Could not add the voice: {m}", { m: e.message }));
  }
  renderLibrary();
}
function libCard(v) {
  const meta = [libValue("language", v.language), v.accent && libValue("accent", v.accent),
    v.gender && libValue("gender", v.gender), v.age && libValue("age", v.age)].filter(Boolean).join(" · ");
  const est = (v.estimated || []).length ? t("Estimated from the audio: {list}", { list: v.estimated.map((f) => t(f)).join(", ") }) : null;
  return h("article", { class: "voice-card", "data-id": v.id },
    h("div", { class: "vc-head" }, h("h3", {}, v.name),
      h("span", { class: "badge " + (v.commercial ? "ok" : "warn"), title: v.license },
        v.commercial ? t("Commercial use OK") : t("Non-commercial"))),
    h("div", { class: "muted small", title: est }, meta, est ? " *" : ""),
    h("div", { class: "chips" }, (v.tags || []).map((x) => h("span", { class: "chip" }, libValue("style", x)))),
    h("div", { class: "muted small vc-lic" }, `${libValue("engine", v.engine)} · `,
      h("a", { href: v.license_url || v.source_url, target: "_blank", rel: "noopener noreferrer" }, libValue("license", v.license_short))),
    h("div", { class: "actions" },
      v.preview_url ? h("button", { type: "button", class: "ghost small lib-play play-btn", "aria-pressed": preview.id === v.id ? "true" : "false",
        "aria-label": t("Preview {name}", { name: v.name }), onclick: (e) => previewPlay(v.id, v.preview_url, e.currentTarget) },
        preview.id === v.id ? t("■ Stop") : t("▶ Preview")) : null,
      h("button", { type: "button", class: "small lib-add", disabled: v.added ? true : null,
        onclick: (e) => libAdd(v, e.currentTarget) }, v.added ? t("✓ In My Voices") : t("Add to My Voices"))));
}
function renderLibrary() {
  const grid = $("#lib-grid");
  if (!grid || !lib.voices) return;
  const hits = lib.voices.filter(libMatches);
  $("#lib-count").textContent = t("{n} of {total} voices", { n: hits.length, total: lib.voices.length });
  grid.replaceChildren(...(hits.length ? hits.map(libCard) : [h("p", { class: "muted" }, t("No voices match these filters."))]));
}
function libFilterBar() {
  const opts = (key, get) => [...new Set(lib.voices.flatMap(get).filter(Boolean))]
    .sort((a, b) => libValue(key, a).localeCompare(libValue(key, b)));
  return h("div", { class: "card lib-filters" },
    h("input", { id: "lib-search", type: "search", placeholder: t("Search by name, accent or style…"), "aria-label": t("Search voices…"),
      value: lib.q, autocomplete: "off", oninput: (e) => { lib.q = e.target.value; renderLibrary(); } }),
    h("div", { class: "lib-selects" },
      LIB_FILTERS.map(([key, label, any, get]) => h("select", { id: `lib-${key}`, "aria-label": t(label),
        onchange: (e) => { lib.filters[key] = e.target.value; renderLibrary(); } },
        h("option", { value: "" }, t(any)),
        opts(key, get).map((x) => h("option", { value: x, selected: lib.filters[key] === x ? true : null }, libValue(key, x))))),
      h("label", { class: "check small" }, h("input", { id: "lib-commercial", type: "checkbox", checked: lib.commercial ? true : null,
        onchange: (e) => { lib.commercial = e.target.checked; renderLibrary(); } }), t("Commercial use only")),
      h("button", { type: "button", class: "ghost small", id: "lib-clear", onclick: () => {
        Object.assign(lib, { q: "", filters: {}, commercial: false }); route(); } }, t("Clear filters"))),
    h("div", { id: "lib-count", class: "muted small", role: "status" }));
}
views.library = async (el) => {
  el.append(h("h1", {}, t("Voice Library")),
    h("p", { class: "sub" }, t("Free voices with open licenses. Listen to a preview, then add the ones you like to My Voices.")),
    h("div", { id: "lib-top" }, h("p", { class: "muted" }, t("Loading voices…"))),
    h("div", { id: "lib-grid", class: "lib-grid" }));
  try {
    lib.voices = await api("/api/library");
  } catch (e) {
    $("#lib-top")?.replaceChildren(h("p", { class: "error" }, t("Could not load voices: {m}", { m: e.message })));
    return;
  }
  if (!$("#lib-top")) return;                            // user left the page
  $("#lib-top").replaceChildren(libFilterBar());
  renderLibrary();
};

// ---- My Voices: cards with preview, edit / rename, duplicate, default, copy ID, delete.
const mv = { voices: null, q: "", editing: null, focus: null };
const KIND_LABEL = { cloned: "Cloned", blended: "Blend", preset: "Preset" };
async function mvLoad() {
  try {
    mv.voices = await api("/api/my-voices");
  } catch (e) {
    $("#mv-grid")?.replaceChildren(h("p", { class: "error" }, t("Could not load voices: {m}", { m: e.message })));
    return;
  }
  renderMyVoices();
}
async function mvImport(file) {
  const btn = $("#mv-import");
  if (!file || !btn || btn.disabled) return;
  btn.disabled = true;
  btn.textContent = t("Importing…");
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const r = await api("/api/import", { method: "POST", body: form });
    const renamed = r.voices.filter((v) => v.renamed).length;
    toast([t("Imported {n} voices and {w} dictionary words.", { n: r.voices.length, w: r.dictionary_added }),
      renamed ? t("{n} voices were already here, so they were added as copies.", { n: renamed }) : ""]
      .filter(Boolean).join(" "), "ok");
    await mvLoad();
  } catch (e) {
    toast(t("Could not import the backup: {m}", { m: e.message }));
  } finally {
    btn.disabled = false;
    btn.textContent = t("Import backup");
  }
}
async function mvAction(fn, ok) {
  try {
    await fn();
    if (ok) toast(ok, "ok");
  } catch (e) {
    toast(t("Something went wrong: {m}", { m: e.message }));
  }
  await mvLoad();
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {                                              // older browsers / blocked clipboard: select-and-copy
    const ta = h("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    if (!ok) throw new Error(t("Copy is blocked in this browser. The ID is: {id}", { id: text }));
  }
}
function mvEditForm(v) {
  const sel = (id, value, options) => h("select", { id }, options.map(([val, label]) =>
    h("option", { value: val, selected: val === (value || "") ? true : null }, label)));
  const field = (label, input) => h("label", { class: "field" }, h("span", {}, t(label)), input);
  const msg = h("div", { class: "error small", role: "alert" });
  const form = h("form", { class: "mv-edit", onsubmit: async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const body = { name: $("#mv-name", f).value, description: $("#mv-desc", f).value, tags: $("#mv-tags", f).value,
      language: $("#mv-lang", f).value, accent: $("#mv-accent", f).value, gender: $("#mv-gender", f).value,
      age: $("#mv-age", f).value, engine: $("#mv-engine", f).value };
    $("button[type=submit]", f).disabled = true;
    try {
      await api(`/api/my-voices/${encodeURIComponent(v.id)}`, { method: "PATCH",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      mv.editing = null;
      toast(t("Saved “{name}”.", { name: body.name.trim() }), "ok");
      await mvLoad();
    } catch (err) {
      msg.textContent = err.message;
      $("button[type=submit]", f).disabled = false;
    }
  } },
    field("Name", h("input", { id: "mv-name", value: v.name, maxlength: 80, required: true })),
    field("Description", h("textarea", { id: "mv-desc", rows: 2, maxlength: 500 }, v.description || "")),
    field("Tags (comma separated)", h("input", { id: "mv-tags", value: (v.tags || []).join(", "), placeholder: t("warm, narrator") })),
    h("div", { class: "mv-row" },
      field("Language", sel("mv-lang", v.language, [["en", "English"], ["es", "Español"]])),
      field("Accent", h("input", { id: "mv-accent", value: v.accent || "", maxlength: 40 }))),
    h("div", { class: "mv-row" },
      field("Gender", sel("mv-gender", v.gender, [["", t("Not set")], ["female", t("Female")], ["male", t("Male")], ["neutral", t("Neutral (gender)")]])),
      field("Age", sel("mv-age", v.age, [["", t("Not set")], ["young adult", t("Young adult")], ["adult", t("Adult")],
        ["middle-aged", t("Middle-aged")], ["senior", t("Senior")]]))),
    field("Engine", h("select", { id: "mv-engine", disabled: v.allowed_engines.length < 2 ? true : null },
      v.allowed_engines.map((x) => h("option", { value: x, selected: x === v.engine ? true : null }, libValue("engine", x))))),
    msg,
    h("div", { class: "actions" }, h("button", { type: "submit", class: "small" }, t("Save")),
      h("button", { type: "button", class: "ghost small", onclick: () => { mv.editing = null; renderMyVoices(); } }, t("Cancel"))));
  return form;
}
function mvCard(v) {
  if (mv.editing === v.id) return h("article", { class: "voice-card editing", "data-id": v.id }, mvEditForm(v));
  const meta = [libValue("language", v.language), v.accent && libValue("accent", v.accent),
    v.gender && libValue("gender", v.gender), v.age && libValue("age", v.age)].filter(Boolean).join(" · ");
  const id = encodeURIComponent(v.id);
  return h("article", { class: "voice-card" + (v.default ? " default" : ""), "data-id": v.id },
    h("div", { class: "vc-head" }, h("h3", {}, v.name),
      v.default ? h("span", { class: "badge ok" }, t("★ Default")) : h("span", { class: "badge" }, t(KIND_LABEL[v.kind] || v.kind || ""))),
    h("div", { class: "muted small" }, meta),
    v.description ? h("div", { class: "small" }, v.description) : null,
    h("div", { class: "chips" }, (v.tags || []).map((x) => h("span", { class: "chip" }, libValue("style", x)))),
    h("div", { class: "muted small vc-id" }, `${libValue("engine", v.engine)} · ID `, h("code", {}, v.id),
      h("button", { type: "button", class: "ghost small mv-copy", "aria-label": t("Copy voice ID"), title: t("Copy voice ID"),
        onclick: () => copyText(v.id).then(() => toast(t("Copied {id}", { id: v.id }), "ok"), (e) => toast(e.message)) }, t("Copy"))),
    h("div", { class: "actions" },
      h("button", { type: "button", class: "ghost small play-btn mv-play", "aria-pressed": preview.id === v.id ? "true" : "false",
        "aria-label": t("Preview {name}", { name: v.name }), title: v.has_preview ? null : t("The first preview is made now and can take a moment."),
        onclick: (e) => previewPlay(v.id, `/api/my-voices/${id}/preview`, e.currentTarget) },
        preview.id === v.id ? t("■ Stop") : t("▶ Preview")),
      h("button", { type: "button", class: "ghost small mv-rename", onclick: () => { mv.editing = v.id; mv.focus = "name"; renderMyVoices(); } }, t("Rename")),
      h("button", { type: "button", class: "ghost small mv-edit-btn", onclick: () => { mv.editing = v.id; mv.focus = null; renderMyVoices(); } }, t("Edit")),
      h("button", { type: "button", class: "ghost small mv-dup", onclick: () => mvAction(() =>
        api(`/api/my-voices/${id}/duplicate`, { method: "POST" }), t("Made a copy of “{name}”.", { name: v.name })) }, t("Duplicate")),
      h("a", { class: "btn ghost small mv-export", href: `/api/export?voice=${id}`, download: "",
        title: t("Download this voice (samples, settings, dictionary) as a zip, to use on another PC or VPS.") }, t("Export")),
      h("button", { type: "button", class: "ghost small mv-default", disabled: v.default ? true : null, onclick: () => mvAction(() =>
        api("/api/default-voice", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ voice: v.id }) }),
        t("“{name}” is now the default voice.", { name: v.name })) }, t("Set as default")),
      h("button", { type: "button", class: "ghost small danger mv-delete", onclick: () => {
        if (!confirm(t("Delete “{name}”? Its samples and settings are removed. This cannot be undone.", { name: v.name }))) return;
        mvAction(() => api(`/api/my-voices/${id}`, { method: "DELETE" }), t("Deleted “{name}”.", { name: v.name }));
      } }, t("Delete"))));
}
function renderMyVoices() {
  const grid = $("#mv-grid");
  if (!grid || !mv.voices) return;
  const q = mv.q.trim().toLowerCase();
  const hits = mv.voices.filter((v) => !q || [v.name, v.id, v.accent, v.description, ...(v.tags || [])]
    .filter(Boolean).join(" ").toLowerCase().includes(q));
  $("#mv-count").textContent = t("{n} of {total} voices", { n: hits.length, total: mv.voices.length });
  if (!mv.voices.length) {
    grid.replaceChildren(h("div", { class: "card mv-empty" }, h("p", {}, t("No voices yet.")),
      h("p", { class: "muted" }, h("a", { href: "#clone" }, t("Clone a voice")), " · ", h("a", { href: "#library" }, t("Browse the Voice Library")))));
    return;
  }
  grid.replaceChildren(...(hits.length ? hits.map(mvCard) : [h("p", { class: "muted" }, t("No voices match your search."))]));
  const f = $(".voice-card.editing #mv-name");
  if (f) { f.focus(); if (mv.focus === "name") f.select(); }
}
views.voices = async (el) => {
  mv.editing = null;
  el.append(h("h1", {}, t("My Voices")),
    h("p", { class: "sub" }, t("Your saved voices: cloned, blended and copied from the library. "),
      h("a", { href: "#clone" }, t("Clone a voice")), " · ", h("a", { href: "#library" }, t("Browse the Voice Library"))),
    h("div", { class: "card lib-filters" },
      h("input", { id: "mv-search", type: "search", placeholder: t("Search voices…"), "aria-label": t("Search voices…"),
        value: mv.q, autocomplete: "off", oninput: (e) => { mv.q = e.target.value; renderMyVoices(); } }),
      h("div", { id: "mv-count", class: "muted small", role: "status" }, t("Loading voices…")),
      h("div", { class: "mv-backup" },
        h("a", { id: "mv-export-all", class: "btn ghost small", href: "/api/export", download: "",
          title: t("Download all your voices and the pronunciation dictionary as one zip.") }, t("Export all voices")),
        h("button", { id: "mv-import", type: "button", class: "btn ghost small",
          title: t("Add the voices and dictionary words from a backup zip. Nothing you have is overwritten."),
          onclick: () => $("#mv-import-input").click() }, t("Import backup")),
        h("input", { id: "mv-import-input", type: "file", hidden: true, accept: ".zip,application/zip",
          onchange: (e) => { mvImport(e.target.files[0]); e.target.value = ""; } }))),
    h("div", { id: "mv-grid", class: "lib-grid" }));
  await mvLoad();
};

// ---- History: every generated clip, newest first. Server-side search and paging (30 per page).
const HIST_PAGE = 30;
const hist = { items: [], total: 0, q: "", seq: 0, timer: null };
const fmtDate = (iso) => {
  const d = new Date(String(iso).replace(/([+-]\d\d)(\d\d)$/, "$1:$2"));      // "+0200" → "+02:00"
  return isNaN(d) ? iso : d.toLocaleString(uiLang, { dateStyle: "medium", timeStyle: "short" });
};
async function histLoad(more = false) {
  const seq = ++hist.seq;                                     // newer search wins over a slow older one
  const offset = more ? hist.items.length : 0;
  try {
    const r = await api(`/api/history?${new URLSearchParams({ q: hist.q, limit: HIST_PAGE, offset })}`);
    if (seq !== hist.seq) return;
    hist.items = more ? hist.items.concat(r.items) : r.items;
    hist.total = r.total;
  } catch (e) {
    $("#hist-list")?.replaceChildren(h("p", { class: "error" }, t("Could not load the history: {m}", { m: e.message })));
    return;
  }
  renderHistory();
}
function histUse(e) {
  Object.assign(tts, { text: e.text, voice: e.voice_id, picked: true });
  location.hash = "#tts";
}
async function histDelete(e) {
  if (!confirm(t("Delete this clip? Its audio and subtitles are removed. This cannot be undone."))) return;
  try {
    await api(`/api/history/${e.id}`, { method: "DELETE" });
    if (preview.id === `hist:${e.id}`) previewStop();
    if (tts.last?.id === e.id) tts.last = null;
    hist.items = hist.items.filter((x) => x.id !== e.id);
    hist.total -= 1;
    toast(t("Clip deleted."), "ok");
    renderHistory();
  } catch (err) {
    toast(t("Could not delete the clip: {m}", { m: err.message }));
  }
}
function histItem(e) {
  const long = e.text.length > 240;
  const text = h("p", { class: "hist-text" + (long ? " clamp" : "") }, e.text);
  const base = `/api/history/${e.id}`;
  const play = h("button", { type: "button", class: "ghost small play-btn hist-play", "data-idle": t("▶ Play"),
    "aria-pressed": preview.id === `hist:${e.id}` ? "true" : "false",
    onclick: (ev) => previewPlay(`hist:${e.id}`, `${base}/audio`, ev.currentTarget) },
    preview.id === `hist:${e.id}` ? t("■ Stop") : t("▶ Play"));
  return h("article", { class: "card hist-item", "data-id": e.id },
    h("div", { class: "hist-meta muted small" },
      h("strong", {}, e.voice_name || e.voice_id), ` · ${LANG_NAMES[e.language] || e.language} · ${libValue("engine", e.engine)} · ${Number(e.seconds).toLocaleString(uiLang, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s · `,
      h("time", { datetime: e.created }, fmtDate(e.created))),
    text,
    long ? h("button", { type: "button", class: "link small hist-more", onclick: (ev) => {
      const open = text.classList.toggle("clamp");
      ev.currentTarget.textContent = open ? t("Show more") : t("Show less");
    } }, t("Show more")) : null,
    h("div", { class: "actions" }, play,
      h("span", { class: "downloads" }, h("span", { class: "muted small" }, t("Download")),
        DOWNLOADS.map(([fmt, label]) => h("a", { class: "btn ghost small", "data-format": fmt, download: "",
          href: `${base}/audio?format=${fmt}&download=true` }, t(label))),
        e.has_subtitles ? ["srt", "vtt"].map((fmt) => h("a", { class: "btn ghost small", "data-subs": fmt, download: "",
          title: t("Timed subtitles, one line per sentence"), href: `${base}/subtitles?format=${fmt}&download=true` }, fmt.toUpperCase())) : null),
      h("button", { type: "button", class: "ghost small hist-use", onclick: () => histUse(e) }, t("Use in Text to Speech")),
      h("button", { type: "button", class: "ghost small danger hist-delete", onclick: () => histDelete(e) }, t("Delete"))));
}
function renderHistory() {
  const list = $("#hist-list");
  if (!list) return;
  $("#hist-count").textContent = hist.total === 1 ? t("1 clip") : t("{n} clips", { n: hist.total });
  if (!hist.items.length) {
    list.replaceChildren(hist.q.trim() ? h("p", { class: "muted" }, t("No clips match your search."))
      : h("div", { class: "card" }, h("p", {}, t("No clips yet.")), h("p", {}, h("a", { href: "#tts" }, t("Go to Text to Speech")))));
    return;
  }
  list.replaceChildren(...hist.items.map(histItem));
  if (hist.items.length < hist.total) list.append(h("button", { type: "button", id: "hist-more", class: "ghost", onclick: (ev) => {
      ev.currentTarget.disabled = true; histLoad(true); } }, t("Load more ({n} left)", { n: hist.total - hist.items.length })));
}
views.history = async (el) => {
  el.append(h("h1", {}, t("History")),
    h("p", { class: "sub" }, t("Every clip you generate is kept here, newest first.")),
    h("div", { class: "card lib-filters" },
      h("input", { id: "hist-search", type: "search", placeholder: t("Search text or voice…"), "aria-label": t("Search text or voice…"),
        value: hist.q, autocomplete: "off", oninput: (e) => {
          hist.q = e.target.value;
          clearTimeout(hist.timer);
          hist.timer = setTimeout(() => histLoad(), 250);        // one request after typing stops
        } }),
      h("div", { id: "hist-count", class: "muted small", role: "status" }, t("Loading…"))),
    h("div", { id: "hist-list", class: "hist-list" }));
  await histLoad();
};

// ---- API & Agents: address, optional API key, copy-ready examples, endpoint list (from the live OpenAPI schema).
const apiPage = { key: null, status: null, voice: "piper-en-us-lessac-medium", lang: "curl", mcp: null, mcpTab: "http", remote: null };
function codeBlock(text, id) {
  return h("div", { class: "code" }, h("pre", { id }, h("code", {}, text)),
    h("button", { type: "button", class: "ghost small code-copy", "aria-label": t("Copy code"),
      onclick: () => copyText(text).then(() => toast(t("Copied."), "ok"), (e) => toast(e.message)) }, t("Copy")));
}
function apiExamples() {
  const base = location.origin, v = apiPage.voice, auth = apiPage.status?.enabled;
  const H = auth ? ` \\\n  -H "Authorization: Bearer $VOICER_API_KEY"` : "";
  const pyH = auth ? `, "Authorization": "Bearer " + os.environ["VOICER_API_KEY"]` : "";
  const curl = [
    [t("List voices"), `curl ${base}/api/voices${H}`],
    [t("Speak and save an MP3"), `ID=$(curl -s ${base}/api/tts${H} \\\n  -H "Content-Type: application/json" \\\n  -d '{"text": "Hello from Voice Studio.", "voice": "${v}", "language": "auto"}' \\\n  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')\ncurl -o speech.mp3 "${base}/api/history/$ID/audio?format=mp3"${H}`],
    [t("WhatsApp voice note (OGG/Opus)"), `curl -o note.ogg "${base}/api/history/$ID/audio?format=ogg_opus"${H}`],
    [t("Subtitles (SRT)"), `curl -o speech.srt "${base}/api/history/$ID/subtitles?format=srt"${H}`],
  ];
  const py = [[t("Speak and save an MP3"), `import json, os, urllib.request

BASE = "${base}"
HEADERS = {"Content-Type": "application/json"${pyH}}


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


entry = json.loads(call("/api/tts", {"text": "Hola, esto es Voice Studio.", "voice": "${v}", "language": "auto"}))
for fmt, name in (("mp3", "speech.mp3"), ("ogg_opus", "note.ogg")):
    with open(name, "wb") as f:
        f.write(call(f"/api/history/{entry['id']}/audio?format={fmt}"))
print("Saved", entry["seconds"], "seconds of audio")`]];
  const key = auth ? `os.environ["VOICER_API_KEY"]` : `"not-needed"`;
  const oai = [[t("OpenAI SDK (Python)"), `# pip install openai
import os
from openai import OpenAI

client = OpenAI(base_url="${base}/v1", api_key=${key})
with client.audio.speech.with_streaming_response.create(
    model="tts-1", voice="${v}", input="Hello from Voice Studio.", response_format="mp3"
) as r:
    r.stream_to_file("speech.mp3")
print("Saved speech.mp3")`],
    [t("OpenAI-compatible (curl)"), `curl ${base}/v1/audio/speech${H} \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "tts-1", "input": "Hello from Voice Studio.", "voice": "${v}", "response_format": "opus"}' \\\n  -o note.ogg`]];
  return ({ curl, python: py, openai: oai }[apiPage.lang] || curl).map(([title, text], i) =>
    h("div", { class: "api-example" }, h("h3", {}, title), codeBlock(text, `api-ex-${i}`)));
}
function renderApiKey() {
  const box = $("#api-key-box");
  if (!box) return;
  const s = apiPage.status || {};
  const create = async (replace) => {
    if (replace && !confirm(t("Replace the API key? Agents that use the old key stop working."))) return;
    try {
      const r = await api("/api/api-key", { method: "POST" });
      apiPage.key = r.key;
      apiPage.status = r;
      toast(t("New API key made. Copy it now."), "ok");
    } catch (e) { toast(t("Something went wrong: {m}", { m: e.message })); }
    renderApiKey();
    renderApiExamples();
    renderMcp();
    renderRemote();
  };
  const off = async () => {
    if (!confirm(t("Turn off the API key? Then any device that can reach this server can use it."))) return;
    try {
      apiPage.status = await api("/api/api-key", { method: "DELETE" });
      apiPage.key = null;
      toast(t("API key turned off."), "ok");
    } catch (e) { toast(t("Something went wrong: {m}", { m: e.message })); }
    renderApiKey();
    renderApiExamples();
    renderMcp();
    renderRemote();
  };
  box.replaceChildren(...[
    h("p", { id: "api-key-status" }, s.enabled
      ? [h("span", { class: "badge ok" }, t("On")), " ", t("Key {hint}, made {date}.", { hint: s.hint, date: fmtDate(s.created) })]
      : [h("span", { class: "badge" }, t("Off")), " ", t("Any device on your network can use the API. Remote access (Tailscale) stays closed until you make a key.")]),
    h("p", { class: "muted small" }, t("This PC never needs the key. Other devices (phone, VPS, Tailscale) must send it as “Authorization: Bearer <key>”.")),
    apiPage.key ? h("div", { class: "api-new-key" },
      h("p", { class: "warn small" }, t("Copy the key now. It is shown only once. Keep it secret.")),
      codeBlock(apiPage.key, "api-key-value")) : null,
    h("div", { class: "actions" },
      s.enabled ? h("button", { type: "button", id: "api-key-replace", class: "ghost small", onclick: () => create(true) }, t("Replace key"))
        : h("button", { type: "button", id: "api-key-create", class: "small", onclick: () => create(false) }, t("Create API key")),
      s.enabled ? h("button", { type: "button", id: "api-key-off", class: "ghost small danger", onclick: off }, t("Turn off")) : null)].filter(Boolean));
}
function renderApiExamples() {
  const box = $("#api-examples");
  if (!box) return;
  box.replaceChildren(...apiExamples());
  document.querySelectorAll(".api-tabs button[data-lang]").forEach((b) => b.setAttribute("aria-selected", b.dataset.lang === apiPage.lang ? "true" : "false"));
}
// MCP config snippets: HTTP (any agent that can reach the server), stdio (agents on this PC / in WSL),
// and the Windows desktop apps (they start the stdio server inside WSL through wsl.exe).
function mcpSnippets() {
  const c = apiPage.mcp;
  if (!c) return [];
  const json = (server) => JSON.stringify({ mcpServers: { "voice-studio": server } }, null, 2);
  const url = location.origin + c.http_path, auth = apiPage.status?.enabled;
  const http = { type: "http", url };
  if (auth) http.headers = { Authorization: "Bearer YOUR_API_KEY" };
  const out = { http: [[t("Config file (Claude Code, Cursor, VS Code…)"), json(http)],
    [t("Claude Code command"), `claude mcp add --transport http voice-studio ${url}` + (auth ? ` \\\n  --header "Authorization: Bearer $VOICER_API_KEY"` : "")]] };
  const s = c.stdio;
  if (s) {
    out.stdio = [[t("Config file (agents on this PC or in WSL)"),
      json({ command: s.python, args: ["-m", s.module], env: { PYTHONPATH: s.root } })]];
    if (s.wsl_distro) out.windows = [[t("Config file (Claude Desktop and other Windows apps)"),
      json({ command: "wsl.exe", args: ["-d", s.wsl_distro, "--cd", s.root, s.venv_python, "-m", s.module] })]];
  }
  const list = out[apiPage.mcpTab] || out.http;
  return list.map(([title, text], i) => h("div", { class: "api-example" }, h("h3", {}, title), codeBlock(text, `mcp-ex-${i}`)));
}
function renderMcp() {
  const box = $("#mcp-box");
  if (!box || !apiPage.mcp) return;
  const tabs = [["http", "HTTP"], ["stdio", "stdio"], ["windows", "Windows"]].filter(([k]) =>
    k === "http" || (k === "stdio" && apiPage.mcp.stdio) || (k === "windows" && apiPage.mcp.stdio?.wsl_distro));
  if (!tabs.some(([k]) => k === apiPage.mcpTab)) apiPage.mcpTab = "http";
  box.replaceChildren(...[
    h("p", { class: "muted small" }, t("Tools: {tools}. “speak” returns a link to the audio (and the file path on this PC). Use format “ogg_opus” for WhatsApp voice notes.",
      { tools: apiPage.mcp.tools.join(", ") })),
    h("div", { class: "api-tabs mcp-tabs", role: "tablist" }, tabs.map(([k, label]) =>
      h("button", { type: "button", role: "tab", class: "ghost small", "data-mcp": k, "aria-selected": k === apiPage.mcpTab ? "true" : "false",
        onclick: () => { apiPage.mcpTab = k; renderMcp(); } }, label))),
    ...mcpSnippets(),
    apiPage.mcp.stdio ? null : h("p", { class: "muted small" }, t("stdio and Windows app configs are shown only on the PC that runs Voice Studio.")),
    apiPage.status?.enabled ? h("p", { class: "muted small" }, t("The API key is on: agents on other devices must send it. Replace YOUR_API_KEY with your key.")) : null,
  ].filter(Boolean));
}
// Remote access card: Tailscale status (this PC only) and the steps to share the server on the tailnet.
function renderRemote() {
  const box = $("#remote-box");
  const r = apiPage.remote;
  if (!box || !r) return;
  if (r.error) {
    box.replaceChildren(h("p", { class: "muted small", id: "remote-status" }, t("Remote access settings are shown only on the PC that runs Voice Studio.")));
    return;
  }
  const keyOn = apiPage.status ? apiPage.status.enabled : r.api_key_on;
  const sudo = r.where === "linux" ? "sudo " : "";
  const url = r.url || "https://YOUR-PC.YOUR-TAILNET.ts.net";
  const state = !r.installed ? t("Tailscale is not installed.")
    : !r.running ? t("Tailscale is installed but not signed in.")
    : !r.serving ? t("Tailscale is on ({name}). Voice Studio is not shared yet.", { name: r.dns_name || r.ips[0] || "?" })
    : t("Shared on your tailnet: {url}", { url: r.url });
  const warnings = [...(r.funnel ? [t("Tailscale Funnel is on: the server is open to the whole internet, not just your tailnet. Turn it off with: tailscale funnel reset")] : []),
    ...(!keyOn ? [t("The API key is off, so remote requests are refused. Make a key on this page.")] : [])];
  const step = (text, ...kids) => h("li", {}, h("p", {}, text), ...kids);
  box.replaceChildren(
    h("p", { id: "remote-status" }, h("span", { class: `badge${r.serving && keyOn ? " ok" : ""}` }, r.serving ? t("On") : t("Off")), " ", state),
    ...warnings.map((w) => h("p", { class: "warn small remote-warning" }, w)),
    h("p", { class: "muted small" }, t("Agents on a VPS reach this PC through Tailscale. Only devices in your tailnet can connect, the link is encrypted, and every request must send the API key.")),
    h("ol", { class: "remote-steps" },
      step(r.where === "linux" ? t("Tailscale runs in this WSL/Linux. Sign in:") : t("Install Tailscale on this Windows PC and sign in:"),
        r.where === "linux" ? codeBlock("sudo tailscale up", "remote-up") : h("p", {}, h("a", { href: "https://tailscale.com/download/windows", target: "_blank", rel: "noopener" }, "tailscale.com/download/windows"))),
      step(t("Make an API key (card above). Remote requests without it are refused.")),
      step(r.where === "linux" ? t("Share Voice Studio on your tailnet only (in this WSL terminal):") : t("Share Voice Studio on your tailnet only (in Windows PowerShell):"),
        codeBlock(`${sudo}tailscale serve --bg http://127.0.0.1:${r.port}`, "remote-serve")),
      step(t("On the VPS, install Tailscale and sign in to the same tailnet:"),
        codeBlock("curl -fsSL https://tailscale.com/install.sh | sh\nsudo tailscale up", "remote-vps")),
      step(t("Test from the VPS. Use the same address for the REST API, the OpenAI API ({v1}) and MCP ({mcp}):", { v1: `${url}/v1`, mcp: `${url}/mcp` }),
        codeBlock(`curl ${url}/api/voices \\\n  -H "Authorization: Bearer $VOICER_API_KEY"`, "remote-test"))),
    h("p", { class: "muted small" }, t("Do not use “tailscale funnel”: it opens the server to the whole internet. To stop sharing: {cmd}", { cmd: `${sudo}tailscale serve reset` })));
}
async function renderEndpoints() {
  const box = $("#api-endpoints");
  try {
    const spec = await api("/openapi.json");
    const rows = [];
    for (const [path, ops] of Object.entries(spec.paths))
      for (const [method, op] of Object.entries(ops))
        rows.push(h("tr", {}, h("td", {}, h("span", { class: `method m-${method}` }, method.toUpperCase())),
          h("td", {}, h("code", {}, path)), h("td", { class: "muted small" }, (op.description || op.summary || "").split("\n")[0])));
    box.replaceChildren(h("div", { class: "table-wrap" }, h("table", { class: "endpoints", lang: "en" }, h("tbody", {}, rows))),
      h("p", { class: "muted small" }, t("{n} endpoints. ", { n: rows.length }),
        h("a", { href: "/docs", target: "_blank", rel: "noopener" }, t("Try them in the interactive docs"))));
  } catch (e) {
    box.replaceChildren(h("p", { class: "error" }, t("Could not load the endpoint list: {m}", { m: e.message })));
  }
}
views.api = async (el) => {
  const base = location.origin;
  el.append(h("h1", {}, t("API & Agents")),
    h("p", { class: "sub" }, t("Use Voice Studio from scripts and AI agents.")),
    h("div", { class: "card" }, h("h2", {}, t("Server address")), codeBlock(base, "api-base")),
    h("div", { class: "card" }, h("h2", {}, t("API key")), h("div", { id: "api-key-box" }, t("Loading…"))),
    h("div", { class: "card" }, h("h2", {}, t("Examples")),
      h("div", { class: "api-tabs", role: "tablist" }, [["curl", "curl"], ["python", "Python"], ["openai", "OpenAI SDK"]].map(([lang, label]) =>
        h("button", { type: "button", role: "tab", class: "ghost small", "data-lang": lang,
          onclick: () => { apiPage.lang = lang; renderApiExamples(); } }, label))),
      h("p", { class: "muted small", id: "api-voice-note" }),
      h("div", { id: "api-examples" })),
    h("div", { class: "card" }, h("h2", {}, t("MCP for AI agents")), h("div", { id: "mcp-box" }, t("Loading…"))),
    h("div", { class: "card" }, h("h2", {}, t("Remote access (Tailscale)")), h("div", { id: "remote-box" }, t("Loading…"))),
    h("div", { class: "card" }, h("h2", {}, t("Endpoints")), h("div", { id: "api-endpoints" }, t("Loading…"))));
  renderApiExamples();
  renderEndpoints();
  try {
    const [status, vs, mcp] = await Promise.all([api("/api/api-key"), api("/api/voices"), api("/api/mcp-config")]);
    apiPage.status = status;
    apiPage.mcp = mcp;
    const v = vs.find((x) => x.default) || vs.find((x) => x.origin === "mine") || vs.find((x) => x.id === apiPage.voice) || vs[0];
    if (v) apiPage.voice = v.id;
    if ($("#api-voice-note") && v) $("#api-voice-note").textContent = t("Examples use the voice “{name}” (ID {id}). Any voice ID from /api/voices works.", { name: v.name, id: v.id });
  } catch (e) {
    toast(t("Something went wrong: {m}", { m: e.message }));
  }
  renderApiKey();
  renderApiExamples();
  renderMcp();
  try {
    apiPage.remote = await api("/api/remote-access");
  } catch (e) {
    apiPage.remote = { error: e.message };
  }
  renderRemote();
};

// ---------- Usage
const use = { days: store.get("usage-days") || "30", seq: 0 };
const USE_PERIODS = [["1", "Last 24 hours"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["0", "All time"]];
const USE_CHANNELS = { rest: "REST API", openai: "OpenAI API", websocket: "WebSocket", mcp: "MCP (HTTP)",
  "mcp-stdio": "MCP (local app)", internal: "Other" };
const useNum = (n, digits = 0) => Number(n || 0).toLocaleString(uiLang, { maximumFractionDigits: digits });

function useTable(id, title, head, rows, label) {
  const body = rows.length
    ? h("div", { class: "table-wrap" }, h("table", { class: "usage-table" },
      h("thead", {}, h("tr", {}, [head, t("Requests"), t("Characters"), t("Minutes")].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", {}, label(r)), h("td", {}, useNum(r.requests)),
        h("td", {}, useNum(r.characters)), h("td", {}, useNum(r.minutes, 2)))))))
    : h("p", { class: "muted" }, t("Nothing in this period."));
  return h("div", { class: "card", id }, h("h2", {}, t(title)), body);
}

async function loadUsage() {
  const box = $("#use-body");
  if (!box) return;
  const seq = ++use.seq;
  let s;
  try {
    s = await api(`/api/usage?days=${encodeURIComponent(use.days)}`);
  } catch (e) {
    if (seq === use.seq) box.replaceChildren(h("p", { class: "error" }, e.message));
    return;
  }
  if (seq !== use.seq || !$("#use-body")) return;          // a newer period was picked, or the page was left
  const tot = s.totals;
  box.replaceChildren(
    h("div", { class: "usage-totals", id: "use-totals" }, [["Requests", useNum(tot.requests)],
      ["Characters", useNum(tot.characters)], ["Audio minutes", useNum(tot.minutes, 1)]].map(([k, v]) =>
      h("div", { class: "card usage-stat" }, h("div", { class: "usage-num" }, v), h("div", { class: "muted" }, t(k))))),
    useTable("use-voice", "By voice", t("Voice"), s.by_voice, (r) => t(r.name || r.voice_id || "Unknown")),
    useTable("use-agent", "By app or agent", t("App or agent"), s.by_agent, (r) => t(r.name)),
    useTable("use-key", "By API key or device", t("API key or device"), s.by_key, (r) => t(r.name)),
    useTable("use-channel", "By connection", t("Connection"), s.by_channel, (r) => t(USE_CHANNELS[r.name] || r.name)));
}

views.usage = (el) => {
  el.append(h("h1", {}, t("Usage")),
    h("p", { class: "sub" }, t("Clips made, characters read and audio minutes, per voice and per app or API key. One request = one clip saved to History.")),
    h("div", { class: "usage-bar" }, h("label", { for: "use-days" }, t("Period")),
      h("select", { id: "use-days", onchange: (e) => { use.days = e.target.value; store.set("usage-days", use.days); loadUsage(); } },
        USE_PERIODS.map(([v, label]) => h("option", { value: v, selected: v === use.days ? true : null }, t(label))))),
    h("div", { id: "use-body" }, h("p", { class: "muted" }, t("Loading…"))),
    h("p", { class: "muted small" }, t("Name your app: send the header X-Voicer-Agent: <name> with each request. MCP apps are named automatically.")));
  if (!USE_PERIODS.some(([v]) => v === use.days)) use.days = "30";
  $("#use-days").value = use.days;
  loadUsage();
};

// ---- Settings: optional daily auto-backup to a folder (this PC only).
const ab = { s: null, busy: false };
const abTime = (sec) => new Date(sec * 1000).toLocaleString(uiLang, { dateStyle: "medium", timeStyle: "short" });
function renderAutoBackup() {
  const box = $("#ab-box");
  if (!box) return;
  const s = ab.s;
  if (!s) return;
  if (s.error) {
    box.replaceChildren(h("p", { class: "muted small", id: "ab-status" }, t("Backup settings are shown only on the PC that runs Voice Studio.")));
    return;
  }
  const status = s.last_error ? h("p", { id: "ab-status", class: "error" }, t("Last backup failed: {m}", { m: s.last_error }))
    : h("p", { id: "ab-status", class: s.last ? "ok" : "muted" }, s.last
      ? t("Last backup: {when} ({file}). {n} kept in the folder.", { when: abTime(s.last), file: s.last_file, n: s.count })
      : t("No automatic backup yet."));
  box.replaceChildren(
    h("p", { class: "muted small" }, t("Once a day, all your voices and the pronunciation dictionary are saved as one zip in a folder. Import the zip on My Voices to restore them.")),
    h("label", { class: "check" }, h("input", { type: "checkbox", id: "ab-enabled", checked: s.enabled ? true : null }),
      h("span", {}, t("Make a backup every day"))),
    h("label", { class: "field" }, h("span", {}, t("Folder")),
      h("input", { id: "ab-folder", value: s.folder, placeholder: s.default_folder, autocomplete: "off", spellcheck: "false" })),
    h("p", { class: "muted small" }, t("Empty = {path}. A Windows folder such as {example} also works.", { path: s.default_folder, example: "C:\\Backups\\Voices" })),
    h("label", { class: "field ab-keep" }, h("span", {}, t("Keep the newest")),
      h("input", { id: "ab-keep", type: "number", min: 1, max: 365, step: 1, value: s.keep })),
    h("div", { class: "actions" },
      h("button", { type: "button", id: "ab-save", disabled: ab.busy ? true : null, onclick: () => abSave() }, t("Save")),
      h("button", { type: "button", id: "ab-run", class: "ghost", disabled: ab.busy ? true : null, onclick: () => abRun() },
        ab.busy === "run" ? t("Backing up…") : t("Back up now"))),
    status,
    s.enabled && s.next ? h("p", { class: "muted small", id: "ab-next" }, t("Next backup: {when}", { when: abTime(s.next) })) : "");
}
async function abLoad() {
  try {
    ab.s = await api("/api/auto-backup");
  } catch (e) {
    ab.s = { error: e.message };
  }
  renderAutoBackup();
}
async function abDo(kind, fn, ok) {
  if (ab.busy) return;
  ab.busy = kind;
  renderAutoBackup();
  try {
    ab.s = await fn();
    toast(ok, "ok");
  } catch (e) {
    toast(e.message);
    await abLoad();
  } finally {
    ab.busy = false;
    renderAutoBackup();
  }
}
function abSave() {
  const body = { enabled: $("#ab-enabled").checked, folder: $("#ab-folder").value, keep: Number($("#ab-keep").value) };
  return abDo("save", () => api("/api/auto-backup", { method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }), t("Backup settings saved."));
}
function abRun() {
  return abDo("run", () => api("/api/auto-backup/run", { method: "POST" }), t("Backup made."));
}
// ---- Dictionary: how the voices say a word (names, brands, abbreviations). Applied before every generation.
const dic = { data: null, q: "", edit: null, busy: false, audio: null };
const DIC_LANGS = [["es", "Español"], ["en", "English"]];
function dicRows() {
  const q = dic.q.trim().toLowerCase();
  return DIC_LANGS.flatMap(([lang]) => (dic.data?.[lang] || []).map((e) => ({ lang, ...e })))
    .filter((e) => !q || e.word.toLowerCase().includes(q) || e.spoken.toLowerCase().includes(q));
}
function renderDictionary() {
  const box = $("#dict-list");
  if (!box || !dic.data) return;
  const rows = dicRows();
  $("#dict-count").textContent = dic.q.trim() ? t("{n} of {total} words", { n: rows.length, total: dic.data.count })
    : dic.data.count === 1 ? t("1 word") : t("{n} words", { n: dic.data.count });
  if (!rows.length) {
    box.replaceChildren(h("p", { class: "muted" }, dic.data.count ? t("No words match.") : t("No words yet. Add the first one above.")));
    return;
  }
  box.replaceChildren(h("div", { class: "table-wrap" }, h("table", { class: "dict-table", id: "dict-table" },
    h("thead", {}, h("tr", {}, h("th", {}, t("Language")), h("th", {}, t("Word")), h("th", {}, t("Say it as")), h("th", {}, ""))),
    h("tbody", {}, rows.map((e) => h("tr", { "data-lang": e.lang, "data-word": e.word },
      h("td", { class: "muted" }, e.lang.toUpperCase()), h("td", {}, e.word), h("td", {}, e.spoken),
      h("td", { class: "dict-actions" },
        h("button", { type: "button", class: "ghost small dict-listen", "aria-label": t("Listen to {word}", { word: e.word }),
          onclick: (ev) => dicListen(e.lang, e.word, ev.currentTarget) }, "▶"),
        h("button", { type: "button", class: "ghost small dict-edit", onclick: () => dicEdit(e) }, t("Edit")),
        h("button", { type: "button", class: "ghost small dict-del", onclick: () => dicDelete(e) }, t("Delete")))))))));
}
async function dicLoad() {
  try {
    dic.data = await api("/api/dictionary");
  } catch (e) {
    $("#dict-list")?.replaceChildren(h("p", { class: "error" }, e.message));
    return;
  }
  renderDictionary();
}
function dicMsg(text, kind = "") {
  const m = $("#dict-msg");
  if (m) { m.className = kind; m.textContent = text; }
}
function dicForm() {
  const editing = dic.edit;
  $("#dict-save").textContent = editing ? t("Save change") : t("Add word");
  $("#dict-cancel").hidden = !editing;
}
function dicEdit(e) {
  dic.edit = e;
  $("#dict-lang").value = e.lang;
  $("#dict-word").value = e.word;
  $("#dict-spoken").value = e.spoken;
  dicForm();
  dicMsg("");
  $("#dict-word").focus();
}
function dicCancel() {
  dic.edit = null;
  $("#dict-word").value = "";
  $("#dict-spoken").value = "";
  dicForm();
  dicMsg("");
}
async function dicSave(ev) {
  ev.preventDefault();
  if (dic.busy) return;
  const body = { language: $("#dict-lang").value, word: $("#dict-word").value.trim(), spoken: $("#dict-spoken").value.trim() };
  if (!body.word || !body.spoken) return dicMsg(t("Type the word and how to say it."), "error");
  if (dic.edit && dic.edit.lang === body.language) body.old_word = dic.edit.word;
  dic.busy = true;
  try {
    dic.data = await api("/api/dictionary", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (dic.edit && dic.edit.lang !== body.language) {          // moved to the other language: remove the old one
      dic.data = await api(`/api/dictionary?language=${dic.edit.lang}&word=${encodeURIComponent(dic.edit.word)}`, { method: "DELETE" });
    }
    const was = dic.edit;
    dicCancel();
    dicMsg(was ? t("Saved “{word}”.", { word: body.word }) : t("Added “{word}”.", { word: body.word }), "ok");
    renderDictionary();
    $("#dict-word").focus();
  } catch (e) {
    dicMsg(e.message, "error");
  } finally {
    dic.busy = false;
  }
}
async function dicDelete(e) {
  if (!confirm(t("Delete “{word}” from the dictionary?", { word: e.word }))) return;
  try {
    dic.data = await api(`/api/dictionary?language=${e.lang}&word=${encodeURIComponent(e.word)}`, { method: "DELETE" });
    if (dic.edit?.word === e.word && dic.edit?.lang === e.lang) dicCancel();
    renderDictionary();
    toast(t("Deleted “{word}”.", { word: e.word }), "ok");
  } catch (err) {
    toast(err.message);
  }
}
// Speak `text` (not saved to History). A word in the list is spoken through the dictionary, so you hear the entry.
async function dicListen(lang, text, btn) {
  if (!text.trim()) return dicMsg(t("Type the word and how to say it."), "error");
  dic.audio?.pause();
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "…";
  try {
    const r = await request("/api/dictionary/listen", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: lang, text }) });
    if (dic.audio) URL.revokeObjectURL(dic.audio.src);
    dic.audio = new Audio(URL.createObjectURL(await r.blob()));
    await dic.audio.play().catch(() => {});
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}
async function dicImport(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/dictionary/import", { method: "POST", body: fd });
    dic.data = r;
    renderDictionary();
    toast(t("Imported {n} words.", { n: r.imported }), "ok");
  } catch (e) {
    toast(e.message);
  }
}
views.dictionary = async (el) => {
  dic.edit = null;
  const on = { autocomplete: "off", spellcheck: "false" };
  el.append(h("h1", {}, t("Dictionary")),
    h("p", { class: "sub" }, t("Tell the voices how to say a word: names, brands, abbreviations. Used before every generation, in the app and the API.")),
    h("form", { class: "card", id: "dict-form", onsubmit: dicSave },
      h("div", { class: "dict-fields" },
        h("label", { class: "field" }, h("span", {}, t("Language")),
          h("select", { id: "dict-lang" }, DIC_LANGS.map(([c, n]) => h("option", { value: c }, n)))),
        h("label", { class: "field" }, h("span", {}, t("Word")),
          h("input", { id: "dict-word", maxlength: 100, placeholder: "WhatsApp", ...on })),
        h("label", { class: "field" }, h("span", {}, t("Say it as")),
          h("input", { id: "dict-spoken", maxlength: 300, placeholder: "guatsap", ...on }))),
      h("div", { class: "actions" },
        h("button", { type: "submit", id: "dict-save" }, t("Add word")),
        h("button", { type: "button", id: "dict-try", class: "ghost",
          onclick: (ev) => dicListen($("#dict-lang").value, $("#dict-spoken").value, ev.currentTarget) }, t("▶ Listen")),
        h("button", { type: "button", id: "dict-cancel", class: "ghost", hidden: true, onclick: dicCancel }, t("Cancel")),
        h("span", { id: "dict-msg", role: "status" }))),
    h("div", { class: "card" },
      h("div", { class: "lib-filters dict-bar" },
        h("input", { id: "dict-search", type: "search", placeholder: t("Search words…"), "aria-label": t("Search words…"),
          value: dic.q, ...on, oninput: (e) => { dic.q = e.target.value; renderDictionary(); } }),
        h("div", { id: "dict-count", class: "muted small", role: "status" }, t("Loading…")),
        h("div", { class: "mv-backup" },
          h("a", { id: "dict-export", class: "btn ghost small", href: "/api/dictionary/export", download: "",
            title: t("Download all words as a CSV file (language, word, spoken form).") }, t("Export CSV")),
          h("button", { id: "dict-import", type: "button", class: "btn ghost small",
            title: t("Add words from a CSV file: language, word, spoken form. Words you have are changed, none are removed."),
            onclick: () => $("#dict-import-input").click() }, t("Import CSV")),
          h("input", { id: "dict-import-input", type: "file", hidden: true, accept: ".csv,.txt,text/csv",
            onchange: (e) => { dicImport(e.target.files[0]); e.target.value = ""; } }))),
      h("div", { id: "dict-list" })));
  await dicLoad();
};

views.settings = (el) => {
  el.append(h("h1", {}, t("Settings")),
    h("div", { class: "card" }, h("h2", {}, t("Daily backup")), h("div", { id: "ab-box" }, t("Loading…"))));
  abLoad();
};

// Interface language (English / Spanish), remembered per browser.
function renderLangPicker() {
  const sel = $("#ui-lang");
  if (!sel) return;
  sel.replaceChildren(...UI_LANGS.map(([c, name]) => h("option", { value: c, selected: c === uiLang ? true : null }, name)));
  sel.setAttribute("aria-label", t("Interface language"));
  $("#status").title = t("Server status");
  setNavCollapsed(document.body.classList.contains("nav-collapsed"));
}
// Collapse / expand the sidebar (desktop). Remembered per browser.
function setNavCollapsed(on) {
  document.body.classList.toggle("nav-collapsed", on);
  const b = $("#nav-toggle");
  if (b) {
    const label = t(on ? "Expand menu" : "Collapse menu");
    b.setAttribute("aria-expanded", on ? "false" : "true");
    b.setAttribute("aria-label", label);
    b.title = label;
  }
}
function setLang(code) {
  uiLang = code;
  try { localStorage.setItem("ui-lang", code); } catch { /* storage blocked */ }
  document.documentElement.lang = code;
  renderLangPicker();
  route();
  pollStatus();
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => {
  document.documentElement.lang = uiLang;
  document.body.classList.toggle("nav-collapsed", store.get("nav-collapsed") === "1");
  renderLangPicker();
  $("#ui-lang")?.addEventListener("change", (e) => setLang(e.target.value));
  $("#nav-toggle")?.addEventListener("click", () => {
    const on = !document.body.classList.contains("nav-collapsed");
    setNavCollapsed(on);
    store.set("nav-collapsed", on ? "1" : null);
  });
  route();
  pollStatus();
  setInterval(pollStatus, 15000);
});
