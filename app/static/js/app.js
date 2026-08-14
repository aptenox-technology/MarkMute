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
  btn.dataset.orig = btn.dataset.orig || btn.textContent;
  btn.innerHTML = busy
    ? `<span class="spinner"></span> ${label || "Working…"}`
    : btn.dataset.orig;
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

api("/health").then((h) => {
  const badge = document.getElementById("health-badge");
  badge.textContent = `API online · SynthID ${h.synthid_available ? "✓" : "✗"} · CtrlRegen ${h.ctrlregen_available ? "✓" : "✗"}`;
  badge.classList.remove("text-slate-400", "border-slate-700");
  badge.classList.add("text-emerald-400", "border-emerald-600");
}).catch(() => {
  const badge = document.getElementById("health-badge");
  badge.textContent = "API offline";
  badge.classList.add("badge-error");
});

/* ================= TEXT ================= */

const textInput = document.getElementById("text-input");
const textOutput = document.getElementById("text-output");
const textReport = document.getElementById("text-report");
const textVerdict = document.getElementById("text-verdict");

function renderTextHits(data) {
  textReport.classList.remove("empty");
  const hits = data.hits || [];
  if (data.suspicious_total === 0) {
    textReport.textContent = "✓ No invisible Unicode characters or space homoglyphs detected.";
    textVerdict.className = "badge-clean text-xs font-semibold px-3 py-1 rounded-full";
    textVerdict.textContent = "CLEAN";
    textVerdict.classList.remove("hidden");
    return;
  }
  const lines = [`⚠ ${data.suspicious_total} suspicious character class(es) found (${data.length} chars scanned):`, ""];
  hits.forEach((h) => {
    lines.push(`• ${h.codepoint} — ${h.label}`);
    lines.push(`  kind: ${h.kind} · confidence: ${h.confidence} · count: ${h.count}`);
  });
  textReport.textContent = lines.join("\n");
  textVerdict.className = "badge-suspicious text-xs font-semibold px-3 py-1 rounded-full";
  textVerdict.textContent = "SUSPICIOUS";
  textVerdict.classList.remove("hidden");
}

document.getElementById("text-paste").addEventListener("click", async () => {
  try { textInput.value = await navigator.clipboard.readText(); } catch { toast("Clipboard unavailable", "error"); }
});

document.getElementById("text-clear").addEventListener("click", () => {
  textInput.value = "";
  textOutput.value = "";
  textOutput.classList.add("hidden");
  textReport.textContent = "Paste text and run Inspect.";
  textReport.classList.add("empty");
  textVerdict.classList.add("hidden");
  document.getElementById("text-copy").classList.add("hidden");
  document.getElementById("text-rewrite-settings").classList.add("hidden");
});

document.getElementById("text-inspect").addEventListener("click", async () => {
  const btn = document.getElementById("text-inspect");
  const text = textInput.value;
  if (!text) return toast("Paste some text first.", "error");
  setBusy(btn, true);
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
  setBusy(btn, true);
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
    document.getElementById("text-copy").classList.remove("hidden");
    const st = data.stats || {};
    textReport.textContent =
      `✓ Cleaned. removed=${st.removed_count ?? "?"} replaced=${st.replaced_count ?? "?"} ` +
      `length ${st.input_length ?? "?"} → ${st.output_length ?? "?"}`;
    toast("Text cleaned.", "success");
  } catch (e) {
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

  setBusy(btn, true);
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
    document.getElementById("text-copy").classList.remove("hidden");
    const st = data.stats || {};
    textReport.textContent =
      backend === "print-prompt"
        ? "Rewrite prompt printed (no LLM call). Configure OLLAMA_HOST or an API key to run for real."
        : `✓ Rewritten via ${backend}/${strength}. tokens_in=${st.tokens_in ?? "?"} tokens_out=${st.tokens_out ?? "?"}`;
    toast("Rewrite complete.", "success");
  } catch (e) {
    textReport.textContent = `Rewrite failed: ${e.message}`;
    toast(e.message, "error");
  } finally {
    setBusy(btn, false);
  }
});

document.getElementById("text-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(textOutput.value);
    toast("Copied to clipboard.", "success");
  } catch { toast("Copy failed", "error"); }
});

/* ================= FILES ================= */

const filesInput = document.getElementById("files-input");
const filesDrop = document.getElementById("files-drop");
const filesQueue = document.getElementById("files-queue");
const filesReport = document.getElementById("files-report");
let currentFile = null;

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
    item.innerHTML = `<span>${esc(f.name)} <span class="text-slate-400">(${fmtBytes(f.size)})</span></span><span class="spinner"></span>`;
    filesQueue.appendChild(item);
    try {
      const data = await api("/files/upload", {
        method: "POST",
        body: (() => { const fd = new FormData(); fd.append("file", f); return fd; })(),
      });
      item.innerHTML = `<span>${esc(f.name)} → <span class="text-emerald-400">${data.file_id.slice(0, 8)}</span></span><button class="btn-ghost text-xs inspect-this" data-fid="${data.file_id}">Inspect</button>`;
      item.querySelector(".inspect-this").addEventListener("click", () => {
        currentFile = data;
        inspectCurrentFile();
      });
    } catch (e) {
      item.innerHTML = `<span class="text-rose-400">${esc(f.name)} — ${esc(e.message)}</span>`;
    }
  }
  filesInput.value = "";
}

async function inspectCurrentFile() {
  if (!currentFile) return;
  setBusy(null, true);
  filesReport.textContent = "Inspecting…";
  filesReport.classList.remove("empty");
  document.getElementById("files-name").textContent = currentFile.filename;
  document.getElementById("files-actions").classList.add("hidden");
  document.getElementById("files-download").classList.add("hidden");
  try {
    const res = await api(`/files/inspect/${currentFile.file_id}`, { method: "POST" });
    renderFileReport(res.detail);
    document.getElementById("files-actions").classList.remove("hidden");
    buildFileActions();
  } catch (e) {
    filesReport.textContent = `Inspect failed: ${e.message}`;
  } finally {
    setBusy(null, false);
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

  filesReport.textContent = lines.join("\n");
}

function buildFileActions() {
  const wrap = document.getElementById("files-actions");
  wrap.innerHTML = "";
  const btn = document.createElement("button");
  btn.className = "btn-primary";
  btn.textContent = "Clean metadata";
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
    a.className = "btn-secondary";
    a.textContent = "⬇ Download cleaned file";
    a.download = "";
    dl.appendChild(a);
    toast(res.detail.residual ? "Cleaned (residual signals remain — best-effort)." : "File cleaned.", "success");
  } catch (e) {
    filesReport.textContent = `Clean failed: ${e.message}`;
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
const imagesPreview = document.getElementById("images-preview");
let currentImage = null;

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
  item.innerHTML = `<span>${esc(f.name)} <span class="text-slate-400">(${fmtBytes(f.size)})</span></span><span class="spinner"></span>`;
  imagesQueue.appendChild(item);
  try {
    const data = await api("/images/upload", {
      method: "POST",
      body: (() => { const fd = new FormData(); fd.append("file", f); return fd; })(),
    });
    item.innerHTML = `<span class="text-emerald-400">${esc(f.name)} uploaded</span>`;
    currentImage = data;
    document.getElementById("images-name").textContent = data.filename;
    imagesPreview.classList.remove("hidden");
    document.getElementById("images-thumb").src = URL.createObjectURL(f);
    inspectCurrentImage();
  } catch (e) {
    item.innerHTML = `<span class="text-rose-400">${esc(f.name)} — ${esc(e.message)}</span>`;
  }
  imagesInput.value = "";
}

async function inspectCurrentImage() {
  imagesReport.textContent = "Inspecting…";
  imagesReport.classList.remove("empty");
  document.getElementById("images-actions").classList.add("hidden");
  document.getElementById("images-download").classList.add("hidden");
  document.getElementById("images-task").classList.add("hidden");
  try {
    const res = await api(`/images/inspect/${currentImage.file_id}`, { method: "POST" });
    renderImageReport(res.detail);
    document.getElementById("images-actions").classList.remove("hidden");
    buildImageActions();
  } catch (e) {
    imagesReport.textContent = `Inspect failed: ${e.message}`;
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
  imagesReport.textContent = lines.join("\n");
}

function buildImageActions() {
  const wrap = document.getElementById("images-actions");
  wrap.innerHTML = "";
  const clean = document.createElement("button");
  clean.className = "btn-primary";
  clean.textContent = "Clean metadata";
  clean.addEventListener("click", cleanCurrentImage);
  wrap.appendChild(clean);

  const score = document.createElement("button");
  score.className = "btn-secondary";
  score.textContent = "SynthID score";
  score.addEventListener("click", scoreCurrentImage);
  wrap.appendChild(score);

  const pixel = document.createElement("button");
  pixel.className = "btn-secondary";
  pixel.textContent = "Remove pixel watermark (CtrlRegen)";
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
    a.className = "btn-secondary";
    a.textContent = "⬇ Download cleaned image";
    a.download = "";
    dl.appendChild(a);
    toast("Image cleaned.", "success");
  } catch (e) {
    imagesReport.textContent = `Clean failed: ${e.message}`;
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
    imagesReport.textContent =
      score != null
        ? `SynthID score: ${score}\n\n(interpretation depends on the scorer build — see raw output below)\n\n${JSON.stringify(res.detail, null, 2)}`
        : JSON.stringify(res.detail, null, 2);
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
        a.className = "btn-secondary";
        a.textContent = "⬇ Download processed image";
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
