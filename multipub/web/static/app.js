"use strict";

const DEFAULT_MD = `---
title: 我的第一篇多平台内容
tags: [效率工具, 创作者]
---

## 大家好

这是一份**同时**适配多个平台的内容。左边写 Markdown，右边实时看各平台成品。

> 一次写作，多平台适配。

- 支持标题、加粗、列表
- 支持代码、引用、表格
- 链接会按平台规则处理：[示例](https://example.com)

\`\`\`python
print("hello multiplatform")
\`\`\`

![配图（远程直链才能粘贴转存）](https://example.com/cover.png)
`;

const state = {
  platforms: [],      // [{name, display_name, constraints}]
  selected: new Set(),
  active: null,       // 当前激活的 tab name
  results: {},        // name -> rendered（确定性适配）
  receipts: {},       // name -> published
  // name -> { styled_md, original_md, rendered, changed, note, status:'pending'|'applied' } 或 { unavailable, note }
  styleInfo: {},
};

const $ = (id) => document.getElementById(id);
const editor = $("editor");

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

async function init() {
  editor.value = DEFAULT_MD;
  const res = await fetch("/api/platforms").then((r) => r.json());
  state.platforms = res.platforms;
  state.platforms.forEach((p) => state.selected.add(p.name));
  state.active = state.platforms[0]?.name ?? null;
  renderPlatformToggles();
  renderTabs();
  await initLLM();
  await refresh();
}

// ---- LLM 设置（厂商 / key / 模型），key 仅存浏览器 sessionStorage，不落服务器 ----
const LLM = { providers: [] };

async function initLLM() {
  const sel = $("llm-provider");
  try {
    const res = await fetch("/api/providers").then((r) => r.json());
    LLM.providers = res.providers || [];
    sel.innerHTML = LLM.providers.map((p) => `<option value="${p.name}">${p.label}</option>`).join("");
  } catch (_) {}
  const saved = JSON.parse(sessionStorage.getItem("llm") || "{}");
  if (saved.provider) sel.value = saved.provider;
  $("llm-key").value = saved.key || "";
  $("llm-model").value = saved.model || "";
  syncLLMHint();
  sel.addEventListener("change", () => { $("llm-model").value = ""; syncLLMHint(); saveLLM(); });
  $("llm-key").addEventListener("input", saveLLM);
  $("llm-model").addEventListener("input", saveLLM);
}

function currentProvider() {
  return LLM.providers.find((p) => p.name === $("llm-provider").value);
}
function syncLLMHint() {
  const p = currentProvider();
  $("llm-model").placeholder = p ? `模型（默认 ${p.default_model}）` : "模型（留空用默认）";
  $("llm-hint").textContent = p && p.note ? "💡 " + p.note : "";
}
function saveLLM() {
  sessionStorage.setItem("llm", JSON.stringify({
    provider: $("llm-provider").value, key: $("llm-key").value, model: $("llm-model").value,
  }));
}
function llmSettings() {
  return {
    provider: $("llm-provider").value,
    api_key: $("llm-key").value.trim(),
    model: $("llm-model").value.trim() || null,
  };
}

function renderPlatformToggles() {
  $("platforms").innerHTML = state.platforms
    .map(
      (p) => `<label><input type="checkbox" data-name="${p.name}" ${
        state.selected.has(p.name) ? "checked" : ""
      }/> ${p.display_name}</label>`
    )
    .join("");
  $("platforms").querySelectorAll("input").forEach((cb) =>
    cb.addEventListener("change", (e) => {
      const name = e.target.dataset.name;
      e.target.checked ? state.selected.add(name) : state.selected.delete(name);
      if (!state.selected.has(state.active)) state.active = [...state.selected][0] ?? null;
      renderTabs();
      refresh();
    })
  );
}

function renderTabs() {
  const tabs = state.platforms.filter((p) => state.selected.has(p.name));
  $("tabs").innerHTML = tabs
    .map((p) => {
      const r = state.results[p.name];
      const warn = r && r.warnings && r.warnings.length ? '<span class="badge warn"></span>' : "";
      return `<div class="tab ${p.name === state.active ? "active" : ""}" data-name="${p.name}">${p.display_name}${warn}</div>`;
    })
    .join("");
  $("tabs").querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      state.active = t.dataset.name;
      renderTabs();
      renderActivePreview();
    })
  );
}

async function refresh() {
  const platforms = [...state.selected];
  if (!platforms.length) { $("preview").innerHTML = '<p style="color:#999">请至少选择一个平台</p>'; return; }
  $("status").textContent = "适配中…";
  try {
    const res = await fetch("/api/adapt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: editor.value, platforms }),
    }).then((r) => r.json());
    state.results = res.results;
    state.receipts = {};   // 内容变了，旧回执作废
    state.styleInfo = {};  // 源文变了，旧的风格化结果（待采用/已采用）一并作废
    $("status").textContent = "已更新";
    renderTabs();
    renderActivePreview();
  } catch (e) {
    $("status").textContent = "适配失败：" + e.message;
  }
}

function platformMeta(name) {
  return state.platforms.find((p) => p.name === name);
}

function renderActivePreview() {
  const name = state.active;
  const info = state.styleInfo[name];
  // 待采用(pending) 或 已采用(applied) 时，预览展示风格化结果；否则展示原始适配
  const styledActive = !!(info && info.rendered && (info.status === "pending" || info.status === "applied"));
  const r = styledActive ? info.rendered : state.results[name];
  const wrap = $("preview");
  // 预览卡外框跟随当前平台主题色（CSS 按 .preview-card.<name> 上色）
  const card = $("previewCard");
  if (card) card.className = "preview-card" + (name ? " " + name : "");
  if (!r) { wrap.innerHTML = ""; return; }
  const meta = platformMeta(name);
  const maxBody = meta?.constraints?.max_body_len ?? null;
  const bodyLen = r.body.length;
  const over = maxBody != null && bodyLen > maxBody;

  const countLabel = maxBody
    ? `<span class="count ${over ? "over" : ""}">正文 ${bodyLen} / ${maxBody} 字</span>`
    : `<span class="count">正文 ${bodyLen} 字</span>`;

  const receipt = state.receipts[name];
  const receiptHtml = receipt
    ? `<div class="receipt ok">✅ ${escapeHtml(receipt.message)}</div>`
    : "";

  const warningsHtml = r.warnings && r.warnings.length
    ? `<div class="warnings">⚠️ 适配提示：<ul>${r.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>`
    : "";

  let styleHtml = "";
  if (info && info.unavailable) {
    styleHtml = `<div class="info">✨ ${escapeHtml(info.note || "风格适配不可用")}</div>`;
  } else if (info && info.status === "pending") {
    styleHtml = `<div class="style-panel">✨ <b>LLM 风格化结果（待你决定）</b> —— ${info.changed ? "已按平台调性改写，下方为预览" : "改写结果与原文基本一致"}。请审阅后点 <b>采用</b> 或 <b>舍弃</b>。
      <details open><summary>查看改写后的 Markdown</summary><pre class="text-preview" style="background:#fff;border:1px solid var(--line);border-radius:var(--r-sm);">${escapeHtml(info.styled_md || "")}</pre></details></div>`;
  } else if (info && info.status === "applied") {
    styleHtml = `<div class="style-panel">✨ <b>已采用 LLM 风格化版本</b>（下方预览为风格化成品）
      <details><summary>查看改写后的 Markdown</summary><pre class="text-preview" style="background:#fff;border:1px solid var(--line);border-radius:var(--r-sm);">${escapeHtml(info.styled_md || "")}</pre></details></div>`;
  }

  // 图片清单：列出每张图（与正文【图N】对应），可复制链接；标注是否需手动上传
  const embeds = meta?.constraints?.embeds_remote_images !== false;
  let manifestHtml = "";
  if (r.images && r.images.length) {
    const rows = r.images.map((img, i) => {
      const manual = img.note || !embeds;
      const tag = manual
        ? '<span class="img-tag manual">需手动上传</span>'
        : '<span class="img-tag auto">随成品带入</span>';
      const thumb = img.is_local
        ? '<span class="img-thumb none">本地</span>'
        : `<img class="img-thumb" src="${escapeAttr(img.url)}" alt="" />`;
      return `<li>
        <span class="img-no">图${i + 1}</span>
        ${thumb}
        <span class="img-alt">${escapeHtml(img.alt || "（无 alt）")}</span>
        ${tag}
        <button class="link-copy" data-url="${escapeAttr(img.url)}">复制链接</button>
      </li>`;
    }).join("");
    manifestHtml = `<div class="manifest">
      <div class="manifest-head">🖼 图片清单（${r.images.length} 张）
        <button class="ghost mini" id="copyAllImgs">复制全部链接</button></div>
      <ul>${rows}</ul></div>`;
  }

  let bodyHtml;
  if (r.body_format === "html") {
    bodyHtml = `<div class="card"><iframe class="html-preview" id="frame-${name}" sandbox="allow-same-origin"></iframe></div>`;
  } else {
    bodyHtml = `<div class="card"><pre class="text-preview">${escapeHtml(r.body)}</pre></div>`;
  }

  let styleBtns;
  if (info && info.status === "pending") {
    styleBtns = `<button id="adoptBtn">✅ 采用</button><button class="ghost" id="discardBtn">✕ 舍弃</button>`;
  } else if (info && info.status === "applied") {
    styleBtns = `<button class="ghost" id="revertBtn">↩︎ 还原原始适配</button>`;
  } else {
    styleBtns = `<button class="ghost" id="styleBtn">✨ 用 LLM 适配风格</button>`;
  }
  const styledTag = info && info.status === "pending" ? '<span style="color:var(--style)">✨ 待采用</span>'
    : info && info.status === "applied" ? '<span style="color:var(--style)">✨ 已采用风格</span>' : "";

  wrap.innerHTML = `
    ${receiptHtml}
    <div class="meta">
      <span>格式：${r.body_format}</span>
      ${countLabel}
      <span>图片 ${r.images.length} 张${r.images.filter((i) => i.note).length ? `（${r.images.filter((i) => i.note).length} 张需手动处理）` : ""}</span>
      ${styledTag}
    </div>
    ${styleHtml}
    ${warningsHtml}
    ${r.title ? `<div style="font-size:13px;color:#666;margin-bottom:8px;">标题：${escapeHtml(r.title)}</div>` : ""}
    ${bodyHtml}
    ${manifestHtml}
    <div class="toolbar">
      <button class="ghost" id="copyBtn">${r.body_format === "html" ? "复制为富文本（粘进公众号）" : "复制文案"}</button>
      ${styleBtns}
    </div>`;

  if (r.body_format === "html") {
    const frame = $("frame-" + name);
    const doc = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{margin:0;padding:16px;font-family:-apple-system,"PingFang SC",sans-serif;}</style></head><body>${r.body}</body></html>`;
    frame.srcdoc = doc;
    frame.onload = () => {
      try { frame.style.height = frame.contentDocument.body.scrollHeight + 32 + "px"; } catch (_) {}
    };
  }
  $("copyBtn").addEventListener("click", () => copyResult(r));
  const sb = $("styleBtn");
  if (sb) sb.addEventListener("click", styleCurrent);
  const rb = $("revertBtn");
  if (rb) rb.addEventListener("click", revertStyle);
  const ab = $("adoptBtn");
  if (ab) ab.addEventListener("click", adoptStyle);
  const db = $("discardBtn");
  if (db) db.addEventListener("click", discardStyle);

  // 图片清单：单张复制 / 全部复制
  wrap.querySelectorAll(".link-copy").forEach((b) =>
    b.addEventListener("click", async () => {
      await navigator.clipboard.writeText(b.dataset.url);
      $("status").textContent = "✅ 已复制图片链接";
    })
  );
  const copyAll = $("copyAllImgs");
  if (copyAll) copyAll.addEventListener("click", async () => {
    const urls = (r.images || []).map((i) => i.url).join("\n");
    await navigator.clipboard.writeText(urls);
    $("status").textContent = `✅ 已复制 ${r.images.length} 个图片链接`;
  });
}

async function styleCurrent() {
  const name = state.active;
  if (!name) return;
  const llm = llmSettings();
  if (!llm.api_key) {
    $("status").textContent = "✨ 请先在顶部「LLM 设置」选择厂商并填写 API key";
    return;
  }
  $("styleBtn") && ($("styleBtn").disabled = true);
  $("status").textContent = `✨ ${currentProvider()?.label || ""} 风格适配中…`;
  try {
    const r = await fetch("/api/style", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: editor.value, platform: name, ...llm }),
    }).then((res) => res.json());

    if (!r.available) {
      state.styleInfo[name] = { unavailable: true, note: r.note };
      $("status").textContent = "✨ " + (r.note || "不可用");
    } else if (r.error) {
      $("status").textContent = "✨ 失败：" + r.error;
    } else {
      // 进入「待采用」审阅态：预览展示改写结果，但尚未提交，由用户决定采用/舍弃
      state.styleInfo[name] = {
        styled_md: r.styled, original_md: r.original, rendered: r.rendered,
        changed: r.changed, note: r.note, status: "pending",
      };
      $("status").textContent = r.changed ? "✨ 已生成改写，请采用或舍弃" : "改写结果与原文基本一致，待你决定";
    }
    renderActivePreview();
  } catch (e) {
    $("status").textContent = "✨ 失败：" + e.message;
  }
}

function adoptStyle() {
  const info = state.styleInfo[state.active];
  if (info) info.status = "applied"; // 采用：保留为该平台的风格化成品（复制/预览都用它）
  $("status").textContent = "✅ 已采用 LLM 风格化版本";
  renderActivePreview();
}

function discardStyle() {
  delete state.styleInfo[state.active]; // 舍弃：丢掉改写结果，回到原始适配
  $("status").textContent = "已舍弃，回到原始适配";
  renderActivePreview();
}

function revertStyle() {
  delete state.styleInfo[state.active]; // 已采用后还原
  renderActivePreview();
}

async function copyResult(r) {
  try {
    if (r.body_format === "html") {
      // 复用已验证的富文本复制机制：写 text/html flavor，粘进公众号保样式
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([r.body], { type: "text/html" }),
          "text/plain": new Blob([r.body], { type: "text/plain" }),
        }),
      ]);
    } else {
      await navigator.clipboard.writeText(r.body);
    }
    $("status").textContent = "✅ 已复制";
  } catch (e) {
    $("status").textContent = "复制失败：" + e.message;
  }
}

async function publish() {
  const platforms = [...state.selected];
  if (!platforms.length) return;
  $("publishBtn").disabled = true;
  $("status").textContent = "模拟发布中…";
  try {
    const res = await fetch("/api/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: editor.value, platforms }),
    }).then((r) => r.json());
    Object.entries(res.results).forEach(([name, pr]) => {
      state.results[name] = pr.rendered;
      state.receipts[name] = pr.published;
    });
    $("status").textContent = "✅ 已模拟发布 " + platforms.length + " 个平台";
    renderTabs();
    renderActivePreview();
  } catch (e) {
    $("status").textContent = "发布失败：" + e.message;
  } finally {
    $("publishBtn").disabled = false;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const escapeAttr = escapeHtml; // 属性值同样需要转义引号

editor.addEventListener("input", debounce(refresh, 400));
$("publishBtn").addEventListener("click", publish);

// 拖拽中间分隔条调整左右宽度；右栏 flex:1 始终吃掉剩余 → 两栏永远铺满
(function initSplit() {
  const main = document.querySelector("main");
  const left = document.querySelector(".pane.left");
  const gutter = $("gutter");
  if (!main || !left || !gutter) return;
  const PAD = 16, GUT = 12, MIN = 22, MAX = 78; // 左右最小/最大占比(%)
  let dragging = false;
  gutter.addEventListener("mousedown", (e) => {
    dragging = true;
    gutter.classList.add("dragging");
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const rect = main.getBoundingClientRect();
    const usable = rect.width - PAD * 2 - GUT;
    const pct = Math.max(MIN, Math.min(MAX, ((e.clientX - rect.left - PAD) / usable) * 100));
    left.style.flexBasis = pct + "%";
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    gutter.classList.remove("dragging");
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
  });
  gutter.addEventListener("dblclick", () => { left.style.flexBasis = "50%"; }); // 复位 50/50
})();

// 粘贴剪贴板图片：上传 → 在光标处插入 markdown 图片语法 → 预览自动显示
editor.addEventListener("paste", async (e) => {
  const items = e.clipboardData ? e.clipboardData.files : null;
  const img = items && [...items].find((f) => f.type.startsWith("image/"));
  if (!img) return; // 非图片，走默认文本粘贴
  e.preventDefault();
  $("status").textContent = "📎 上传图片中…";
  try {
    const fd = new FormData();
    fd.append("file", img, img.name || "pasted.png");
    const res = await fetch("/api/upload", { method: "POST", body: fd }).then((r) => r.json());
    if (res.error) { $("status").textContent = "上传失败：" + res.error; return; }
    insertAtCursor(`![pasted image](${res.url})`);
    $("status").textContent = res.public
      ? "✅ 图片已上传公网图床（可随成品复制到平台）"
      : "✅ 图片已插入（仅本机预览；复制到平台需配置公网图床）";
    refresh();
  } catch (err) {
    $("status").textContent = "上传失败：" + err.message;
  }
});

function insertAtCursor(text) {
  const s = editor.selectionStart, eend = editor.selectionEnd;
  editor.value = editor.value.slice(0, s) + text + editor.value.slice(eend);
  const pos = s + text.length;
  editor.selectionStart = editor.selectionEnd = pos;
  editor.focus();
}

init();
