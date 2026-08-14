/* MarkMute — frontend logic (vanilla JS) */
"use strict";

const API_BASE = "/api/v1";

/* ---------- helpers ---------- */

function toast(msg, type = "info") {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

async function api(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch (_) {}
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

function setBusy(btn, busy, label) {
  if (!btn) return;
  btn.disabled = busy;
  const spinner = btn.querySelector(".btn-spinner");
  const labelEl = btn.querySelector(".btn-label");
  if (spinner) spinner.classList.toggle("hidden", !busy);
  if (labelEl) {
    if (busy) {
      if (!btn.dataset.label) btn.dataset.label = labelEl.textContent;
      labelEl.textContent = label || "Working…";
    } else {
      labelEl.textContent = btn.dataset.label || labelEl.textContent;
    }
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtBytes(n) {
  if (n == null) return "";
  const units = ["B", "KiB", "MiB", "GiB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

/* ---------- theme ---------- */

const themeToggle = document.getElementById("theme-toggle");
const themeIconSun = document.getElementById("theme-icon-sun");
const themeIconMoon = document.getElementById("theme-icon-moon");

function renderThemeIcons() {
  const dark = document.documentElement.dataset.theme === "dark";
  themeIconSun?.classList.toggle("hidden", !dark);
  themeIconMoon?.classList.toggle("hidden", dark);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#020617" : "#f1f5f9");
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("mm-theme", theme);
  renderThemeIcons();
}

renderThemeIcons();
themeToggle?.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

/* ---------- tabs ---------- */

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });
});
document.querySelector(".tab-btn").classList.add("active");

/* ---------- health ---------- */

function setPill(id, text, ok) {
  const pill = document.getElementById(id);
  if (!pill) return;
  const dot = pill.querySelector(".status-dot");
  const txt = pill.querySelector(".status-text");
  if (dot) { dot.classList.toggle("ok", ok); dot.classList.toggle("err", !ok); }
  if (txt) txt.textContent = text;
}

api("/health").then((h) => {
  setPill("status-api", "API online", true);
  setPill("status-synthid", `SynthID ${h.synthid_available ? "online" : "offline"}`, h.synthid_available);
  setPill("status-ctrlregen", `CtrlRegen ${h.ctrlregen_available ? "online" : "offline"}`, h.ctrlregen_available);
}).catch(() => {
  setPill("status-api", "API offline", false);
  setPill("status-synthid", "SynthID offline", false);
  setPill("status-ctrlregen", "CtrlRegen offline", false);
});

/* ---------- text helpers ---------- */

const textInput = document.getElementById("text-input");
const textOutput = document.getElementById("text-output");
const textReport = document.getElementById("text-report");
const textVerdict = document.getElementById("text-verdict");
const resultEmpty = document.getElementById("result-empty");

function showTextReport() {
  resultEmpty?.classList.add("hidden");
  textReport.classList.remove("hidden");
}

function showTextEmpty() {
  resultEmpty?.classList.remove("hidden");
  textReport.classList.add("hidden");
  textReport.innerHTML = "";
}

function confBadge(conf) {
  const n = typeof conf === "number" ? conf : (conf === "high" ? 1 : conf === "medium" || conf === "med" ? 0.5 : 0);
  const level = n >= 0.7 ? ["conf-high", "HIGH"] : n >= 0.4 ? ["conf-med", "MEDIUM"] : ["conf-low", "LOW"];
  return `<span class="confidence-badge ${level[0]}">${level[1]}</span>`;
}

function renderTextHits(data) {
  showTextReport();
  const hits = data.hits || [];
  textVerdict.classList.remove("hidden");
  if (data.suspicious_total === 0) {
    textVerdict.className = "badge-clean text-xs font-semibold px-3 py-1 rounded-full";
    textVerdict.textContent = "CLEAN";
    textReport.innerHTML = `<div class="finding-card"><div class="finding-label">No invisible Unicode characters or space homoglyphs detected.</div></div>`;
    return;
  }
  textVerdict.className = "badge-suspicious text-xs font-semibold px-3 py-1 rounded-full";
  textVerdict.textContent = "SUSPICIOUS";
  const cards = hits.map((h) => `
    <div class="finding-card">
      <div class="finding-card-head">
        <div>
          <div class="finding-label">${esc(h.codepoint || h.label)}</div>
          <div class="finding-desc">${esc(h.label || h.kind || "")}</div>
        </div>
        ${confBadge(h.confidence)}
      </div>
      <div class="finding-reasons">
        <div class="reason-row"><span class="reason-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86l-8.2 14.2A2 2 0 003.8 21h16.4a2 2 0 001.7-3.06l-8.2-14.2a2 2 0 00-3.4 0z" stroke-linecap="round" stroke-linejoin="round"/></svg></span><span>${esc(h.kind || "invisible character")} · count: ${h.count ?? "?"}</span></div>
      </div>
    </div>`).join("");
  textReport.innerHTML = `
    <p class="mb-3">Found <strong>${data.suspicious_total}</strong> suspicious character class(es) in ${data.length ?? "?"} scanned chars:</p>
    ${cards}`;
}

function updateTextStats() {
  const el = document.getElementById("char-count");
  if (el) el.textContent = textInput.value.length;
  const inv = document.getElementById("invisible-count");
  const num = document.getElementById("invisible-num");
  const n = countInvisible(textInput.value);
  if (num) num.textContent = n;
  if (inv) inv.style.display = n > 0 ? "inline-flex" : "none";
}

function countInvisible(s) {
  if (!s) return 0;
  const re = /[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF\u00AD\u061C\uFE00-\uFE0F\uE0000-\uE007F]/g;
  const m = s.match(re);
  return m ? m.length : 0;
}

textInput?.addEventListener("input", updateTextStats);

async function copyText() {
  try {
    await navigator.clipboard.writeText(textOutput.value || textReport.textContent || "");
    const lbl = document.getElementById("copy-label");
    if (lbl) { lbl.textContent = "Copied!"; setTimeout(() => (lbl.textContent = "Copy"), 1500); }
    toast("Copied to clipboard.", "success");
  } catch { toast("Copy failed", "error"); }
}

function downloadText() {
  const content = textOutput.value || textReport.textContent || "";
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "markmute-output.txt";
  a.click();
  URL.revokeObjectURL(url);
}

/* ================= TEXT ================= */

document.getElementById("text-paste").addEventListener("click", async () => {
  try { textInput.value = await navigator.clipboard.readText(); updateTextStats(); } catch { toast("Clipboard unavailable", "error"); }
});

document.getElementById("text-clear").addEventListener("click", () => {
  textInput.value = "";
  textOutput.value = "";
  textOutput.classList.add("hidden");
  document.getElementById("text-output-actions").classList.add("hidden");
  document.getElementById("text-rewrite-options").classList.add("hidden");
  textVerdict.classList.add("hidden");
  document.getElementById("text-copy").classList.add("hidden");
  document.getElementById("text-download").classList.add("hidden");
  showTextEmpty();
  updateTextStats();
});

document.getElementById("text-inspect").addEventListener("click", async () => {
  const btn = document.getElementById("text-inspect");
  const text = textInput.value;
  if (!text) return toast("Paste some text first.", "error");
  setBusy(btn, true, "Inspecting…");
  try {
    const data = await api("/text/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        aggressive: document.getElementById("opt-aggressive").checked,
        strip_emoji_glue: document.getElementById("opt-strip-emoji").checked,
      }),
    });
    renderTextHits(data);
  } catch (e) {
    showTextReport();
    textReport.textContent = `Inspect failed: ${e.message}`;
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
});

document.getElementById("text-clean").addEventListener("click", async () => {
  const btn = document.getElementById("text-clean");
  const text = textInput.value;
  if (!text) return toast("Paste some text first.", "error");
  setBusy(btn, true, "Cleaning…");
  try {
    const data = await api("/text/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        options: {
          nfkc: false,
          aggressive_homoglyphs: document.getElementById("opt-aggressive").checked,
          strip_emoji_glue: document.getElementById("opt-strip-emoji").checked,
        },
      }),
    });
    textOutput.value = data.cleaned_text ?? "";
    textOutput.classList.remove("hidden");
    document.getElementById("text-output-actions").classList.remove("hidden");
    document.getElementById("text-copy").classList.remove("hidden");
    document.getElementById("text-download").classList.remove("hidden");
    const st = data.stats || {};
    showTextReport();
    textReport.textContent =
      `✓ Cleaned. removed=${st.removed_count ?? "?"} replaced=${st.replaced_count ?? "?"} ` +
      `length ${st.input_length ?? "?"} → ${st.output_length ?? "?"}`;
    toast("Text cleaned.", "success");
  } catch (e) {
    showTextReport();
    textReport.textContent = `Clean failed: ${e.message}`;
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
});

/* rewrite settings popover */
const rwSettings = document.getElementById("text-rewrite-settings");
rwSettings.addEventListener("click", () => {
  const panel = document.getElementById("text-rewrite-options");
  panel.classList.toggle("hidden");
});

document.getElementById("text-rewrite").addEventListener("click", async () => {
  const btn = document.getElementById("text-rewrite");
  const text = textInput.value;
  if (!text) return toast("Paste some text first.", "error");
  const backend = document.getElementById("rw-backend").value;
  const strength = document.getElementById("rw-strength").value;
  const lang = document.getElementById("rw-lang").value;
  const temperature = document.getElementById("rw-temperature").value || null;
  const candidates = document.getElementById("rw-candidates").value || null;

  if (backend !== "print-prompt") {
    const ok = confirm(
      `${backend} rewrite calls an external LLM and may send your text to a remote service. Continue?`
    );
    if (!ok) return;
  }

  setBusy(btn, true, "Rewriting…");
  try {
    const data = await api("/text/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text, backend, strength, lang,
        temperature: temperature ? Number(temperature) : null,
        candidates: candidates ? Number(candidates) : null,
      }),
    });
    textOutput.value = data.rewritten_text ?? "";
    textOutput.classList.remove("hidden");
    document.getElementById("text-output-actions").classList.remove("hidden");
    document.getElementById("text-copy").classList.remove("hidden");
    document.getElementById("text-download").classList.remove("hidden");
    const st = data.stats || {};
    showTextReport();
    textReport.textContent =
      backend === "print-prompt"
        ? "Rewrite prompt printed (no LLM call). Configure OLLAMA_HOST or an API key to run for real."
        : `✓ Rewritten via ${backend}/${strength}. tokens_in=${st.tokens_in ?? "?"} tokens_out=${st.tokens_out ?? "?"}`;
    toast("Rewrite complete.", "success");
  } catch (e) {
    showTextReport();
    textReport.textContent = `Rewrite failed: ${e.message}`;
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
});

document.getElementById("text-copy").addEventListener("click", copyText);
document.getElementById("text-download").addEventListener("click", downloadText);

/* keyboard shortcuts */
const isMac = /Mac|iP(hone|ad|od)/.test(navigator.platform);
if (isMac) {
  document.querySelectorAll("#kbd-mod, #kbd-mod2, #kbd-mod3").forEach((k) => (k.textContent = "⌘"));
}
document.addEventListener("keydown", (e) => {
  const mod = e.metaKey || e.ctrlKey;
  if (!mod) return;
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    document.getElementById("text-inspect").click();
  } else if (e.key === "Enter" && e.shiftKey) {
    e.preventDefault();
    document.getElementById("text-clean").click();
  } else if (e.key === "k" || e.key === "K") {
    e.preventDefault();
    document.getElementById("text-clear").click();
  }
});

/* ================= FILES ================= */

const filesInput = document.getElementById("files-input");
const filesDrop = document.getElementById("files-drop");
const filesQueue = document.getElementById("files-queue");
const filesReport = document.getElementById("files-report");
const filesEmpty = document.getElementById("files-empty");
let currentFile = null;

function showFilesReport(text) {
  filesEmpty?.classList.add("hidden");
  filesReport.classList.remove("hidden");
  if (text != null) filesReport.textContent = text;
}

filesDrop.addEventListener("click", () => filesInput.click());
filesInput.addEventListener("change", () => handleFiles([...filesInput.files]));
["dragenter", "dragover"].forEach((ev) =>
  filesDrop.addEventListener(ev, (e) => { e.preventDefault(); filesDrop.classList.add("dragover"); }));
["dragleave", "drop"].forEach((ev) =>
  filesDrop.addEventListener(ev, (e) => { e.preventDefault(); filesDrop.classList.remove("dragover"); }));
filesDrop.addEventListener("drop", (e) => handleFiles([...e.dataTransfer.files]));

async function handleFiles(files) {
  for (const f of files.slice(0, 3)) {
    const item = document.createElement("div");
    item.className = "queued-item";
    item.innerHTML = `<span>${esc(f.name)} <span class="theme-faint">(${fmtBytes(f.size)})</span></span><span class="spinner"></span>`;
    filesQueue.appendChild(item);
    try {
      const data = await api("/files/upload", {
        method: "POST",
        body: (() => { const fd = new FormData(); fd.append("file", f); return fd; })(),
      });
      item.innerHTML = `<span>${esc(f.name)} → <span class="theme-ok">${data.file_id.slice(0, 8)}</span></span><button class="btn-ghost text-xs inspect-this" data-fid="${data.file_id}">Inspect</button>`;
      item.querySelector(".inspect-this").addEventListener("click", () => {
        currentFile = data;
        inspectCurrentFile();
      });
    } catch (e) {
      item.innerHTML = `<span class="theme-err">${esc(f.name)} — ${esc(e.message)}</span>`;
    }
  }
  filesInput.value = "";
}

async function inspectCurrentFile() {
  if (!currentFile) return;
  showFilesReport("Inspecting…");
  document.getElementById("files-name").textContent = currentFile.filename;
  document.getElementById("files-actions").classList.add("hidden");
  document.getElementById("files-download").classList.add("hidden");
  try {
    const res = await api(`/files/inspect/${currentFile.file_id}`, { method: "POST" });
    renderFileReport(res.detail);
    document.getElementById("files-actions").classList.remove("hidden");
    buildFileActions();
  } catch (e) {
    showFilesReport(`Inspect failed: ${e.message}`);
  }
}

function renderFileReport(detail) {
  const lines = [];
  lines.push(`kind: ${detail.kind || "unknown"} · exit_code: ${detail.exit_code ?? "?"}`);
  lines.push(`size: ${fmtBytes(detail.size)}`);
  if (detail.format) lines.push(`format: ${detail.format}`);
  lines.push("");

  const hits = detail.hits || [];
  lines.push(`suspicious: ${detail.suspicious_total ?? hits.length}`);
  hits.forEach((h) => {
    lines.push(`  • ${h.label || h.codepoint || JSON.stringify(h)} [${h.confidence}]`);
  });

  if (detail.actions && detail.actions.length) {
    lines.push("", "actions:");
    detail.actions.forEach((a) => lines.push(`  - ${a}`));
  }
  if (detail.still_has_c2pa) lines.push("", "⚠ residual C2PA signals may remain");
  if (detail.still_has_ai_metadata) lines.push("⚠ residual AI metadata may remain");

  showFilesReport(lines.join("\n"));
}

function buildFileActions() {
  const wrap = document.getElementById("files-actions");
  wrap.innerHTML = "";
  const btn = document.createElement("button");
  btn.className = "btn btn-primary";
  btn.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg><span class="btn-spinner spinner hidden"></span><span class="btn-label">Clean metadata</span>`;
  btn.dataset.label = "Clean metadata";
  btn.addEventListener("click", cleanCurrentFile);
  wrap.appendChild(btn);
}

async function cleanCurrentFile() {
  const btn = document.querySelector("#files-actions .btn-primary");
  setBusy(btn, true, "Cleaning…");
  try {
    const res = await api(`/files/clean/${currentFile.file_id}`, { method: "POST" });
    renderFileReport(res.detail);
    const dl = document.getElementById("files-download");
    dl.innerHTML = "";
    dl.classList.remove("hidden");
    const a = document.createElement("a");
    a.href = res.download_url;
    a.className = "btn btn-secondary";
    a.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg><span class="btn-label">Download cleaned file</span>`;
    a.download = "";
    dl.appendChild(a);
    toast(res.detail.residual ? "Cleaned (residual signals remain — best-effort)." : "File cleaned.", "success");
  } catch (e) {
    showFilesReport(`Clean failed: ${e.message}`);
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
}

/* ================= IMAGES ================= */

const imagesInput = document.getElementById("images-input");
const imagesDrop = document.getElementById("images-drop");
const imagesQueue = document.getElementById("images-queue");
const imagesReport = document.getElementById("images-report");
const imagesEmpty = document.getElementById("images-empty");
const imagesPreview = document.getElementById("images-preview");
let currentImage = null;

function showImagesReport(text) {
  imagesEmpty?.classList.add("hidden");
  imagesReport.classList.remove("hidden");
  if (text != null) imagesReport.textContent = text;
}

imagesDrop.addEventListener("click", () => imagesInput.click());
imagesInput.addEventListener("change", () => handleImage([...imagesInput.files]));
["dragenter", "dragover"].forEach((ev) =>
  imagesDrop.addEventListener(ev, (e) => { e.preventDefault(); imagesDrop.classList.add("dragover"); }));
["dragleave", "drop"].forEach((ev) =>
  imagesDrop.addEventListener(ev, (e) => { e.preventDefault(); imagesDrop.classList.remove("dragover"); }));
imagesDrop.addEventListener("drop", (e) => handleImage([...e.dataTransfer.files]));

async function handleImage(files) {
  const f = files[0];
  if (!f) return;
  const item = document.createElement("div");
  item.className = "queued-item";
  item.innerHTML = `<span>${esc(f.name)} <span class="theme-faint">(${fmtBytes(f.size)})</span></span><span class="spinner"></span>`;
  imagesQueue.appendChild(item);
  try {
    const data = await api("/images/upload", {
      method: "POST",
      body: (() => { const fd = new FormData(); fd.append("file", f); return fd; })(),
    });
    item.innerHTML = `<span class="theme-ok">${esc(f.name)} uploaded</span>`;
    currentImage = data;
    document.getElementById("images-name").textContent = data.filename;
    imagesPreview.classList.remove("hidden");
    document.getElementById("images-thumb").src = URL.createObjectURL(f);
    inspectCurrentImage();
  } catch (e) {
    item.innerHTML = `<span class="theme-err">${esc(f.name)} — ${esc(e.message)}</span>`;
  }
  imagesInput.value = "";
}

async function inspectCurrentImage() {
  showImagesReport("Inspecting…");
  document.getElementById("images-actions").classList.add("hidden");
  document.getElementById("images-download").classList.add("hidden");
  document.getElementById("images-task").classList.add("hidden");
  try {
    const res = await api(`/images/inspect/${currentImage.file_id}`, { method: "POST" });
    renderImageReport(res.detail);
    document.getElementById("images-actions").classList.remove("hidden");
    buildImageActions();
  } catch (e) {
    showImagesReport(`Inspect failed: ${e.message}`);
  }
}

function renderImageReport(detail) {
  const lines = [];
  lines.push(`format: ${detail.format || "?"} · exit_code: ${detail.exit_code ?? "?"}`);
  lines.push(`size: ${fmtBytes(detail.size)}`);
  const hits = detail.hits || [];
  lines.push(`suspicious: ${detail.suspicious_total ?? hits.length}`);
  hits.forEach((h) => lines.push(`  • ${h.label || h.codepoint || JSON.stringify(h)} [${h.confidence}]`));
  if (detail.synthid_score != null) lines.push(`synthid_score: ${detail.synthid_score}`);
  if (detail.actions && detail.actions.length) {
    lines.push("", "actions:");
    detail.actions.forEach((a) => lines.push(`  - ${a}`));
  }
  if (detail.still_has_c2pa) lines.push("", "⚠ residual C2PA signals may remain");
  showImagesReport(lines.join("\n"));
}

function buildImageActions() {
  const wrap = document.getElementById("images-actions");
  wrap.innerHTML = "";
  const clean = document.createElement("button");
  clean.className = "btn btn-primary";
  clean.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg><span class="btn-spinner spinner hidden"></span><span class="btn-label">Clean metadata</span>`;
  clean.dataset.label = "Clean metadata";
  clean.addEventListener("click", cleanCurrentImage);
  wrap.appendChild(clean);

  const score = document.createElement("button");
  score.className = "btn btn-secondary";
  score.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg><span class="btn-spinner spinner hidden"></span><span class="btn-label">SynthID score</span>`;
  score.dataset.label = "SynthID score";
  score.addEventListener("click", scoreCurrentImage);
  wrap.appendChild(score);

  const pixel = document.createElement("button");
  pixel.className = "btn btn-secondary";
  pixel.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M21 12a9 9 0 11-9-9" stroke-linecap="round"/><path d="M21 3v6h-6"/></svg><span class="btn-label">Remove pixel watermark (CtrlRegen)</span>`;
  pixel.dataset.label = "Remove pixel watermark (CtrlRegen)";
  pixel.addEventListener("click", startPixelRemoval);
  wrap.appendChild(pixel);
}

async function cleanCurrentImage() {
  const btn = document.querySelector("#images-actions .btn-primary");
  setBusy(btn, true, "Cleaning…");
  try {
    const res = await api(`/images/clean/${currentImage.file_id}`, { method: "POST" });
    renderImageReport(res.detail);
    const dl = document.getElementById("images-download");
    dl.innerHTML = "";
    dl.classList.remove("hidden");
    const a = document.createElement("a");
    a.href = res.download_url;
    a.className = "btn btn-secondary";
    a.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg><span class="btn-label">Download cleaned image</span>`;
    a.download = "";
    dl.appendChild(a);
    toast("Image cleaned.", "success");
  } catch (e) {
    showImagesReport(`Clean failed: ${e.message}`);
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
}

async function scoreCurrentImage() {
  const btn = document.querySelector("#images-actions .btn-secondary");
  setBusy(btn, true, "Scoring…");
  try {
    const res = await api(`/images/score/${currentImage.file_id}`, { method: "POST" });
    const score = res.detail.score ?? res.detail.synthid_score;
    showImagesReport(
      score != null
        ? `SynthID score: ${score}\n\n(interpretation depends on the scorer build — see raw output below)\n\n${JSON.stringify(res.detail, null, 2)}`
        : JSON.stringify(res.detail, null, 2)
    );
  } catch (e) {
    toast(`SynthID scoring failed: ${e.message}`, "error");
  } finally {
    setBusy(btn, false);
  }
}

async function startPixelRemoval() {
  const taskBox = document.getElementById("images-task");
  taskBox.classList.remove("hidden");
  taskBox.textContent = "Submitting CtrlRegen job…";
  try {
    const res = await api(`/images/remove-pixel/${currentImage.file_id}`, { method: "POST" });
    pollTask(res.task_id, taskBox, res.download_url);
  } catch (e) {
    taskBox.textContent = `Pixel removal unavailable: ${e.message}`;
  }
}

function pollTask(taskId, box, downloadUrl) {
  const tick = async () => {
    try {
      const s = await api(`/tasks/${taskId}`);
      if (s.state === "SUCCESS") {
        box.textContent = "✓ Pixel removal complete.";
        const dl = document.getElementById("images-download");
        dl.innerHTML = "";
        dl.classList.remove("hidden");
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.className = "btn btn-secondary";
        a.innerHTML = `<svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg><span class="btn-label">Download processed image</span>`;
        a.download = "";
        dl.appendChild(a);
        toast("Pixel watermark removal complete.", "success");
        return;
      }
      if (s.state === "FAILURE" || s.state === "REVOKED") {
        box.textContent = `Pixel removal ${s.state.toLowerCase()}.`;
        return;
      }
      const p = s.progress != null ? ` (${s.progress}%)` : "";
      box.textContent = `Processing… ${s.state}${p}`;
      setTimeout(tick, 2000);
    } catch (e) {
      box.textContent = `Task polling error: ${e.message}`;
    }
  };
  tick();
}
