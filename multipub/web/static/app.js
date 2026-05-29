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
  styledOverride: {}, // name -> rendered（LLM 风格化后的版本，应用中）
  styleInfo: {},      // name -> {styled_md, original_md, changed, note, unavailable}
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
  await refresh();
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
    state.receipts = {};       // 内容变了，旧回执作废
    state.styledOverride = {}; // 源文变了，旧的风格化版本作废
    state.styleInfo = {};
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
  const styled = !!state.styledOverride[name];
  const r = state.styledOverride[name] || state.results[name];
  const wrap = $("preview");
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

  const info = state.styleInfo[name];
  let styleHtml = "";
  if (info && info.unavailable) {
    styleHtml = `<div class="warnings">✨ ${escapeHtml(info.note || "风格适配不可用")}</div>`;
  } else if (styled && info) {
    styleHtml = `<div class="style-panel">✨ <b>已应用 LLM 风格化</b>（${info.changed ? "已按平台调性改写" : "与原文一致"}）—— 下方预览为风格化后的成品
      <details><summary>查看风格化后的 Markdown</summary><pre class="text-preview" style="background:#f7f8fa;border-radius:6px;">${escapeHtml(info.styled_md || "")}</pre></details></div>`;
  }

  let bodyHtml;
  if (r.body_format === "html") {
    bodyHtml = `<div class="card"><iframe class="html-preview" id="frame-${name}" sandbox></iframe></div>`;
  } else {
    bodyHtml = `<div class="card"><pre class="text-preview">${escapeHtml(r.body)}</pre></div>`;
  }

  const styleBtn = styled
    ? `<button class="ghost" id="revertBtn">↩︎ 还原原始适配</button>`
    : `<button class="ghost" id="styleBtn">✨ 用 LLM 适配风格</button>`;

  wrap.innerHTML = `
    ${receiptHtml}
    <div class="meta">
      <span>格式：${r.body_format}</span>
      ${countLabel}
      <span>图片 ${r.images.length} 张${r.images.filter((i) => i.note).length ? `（${r.images.filter((i) => i.note).length} 张需手动处理）` : ""}</span>
      ${styled ? '<span style="color:#fb7299">✨ LLM 风格化中</span>' : ""}
    </div>
    ${styleHtml}
    ${warningsHtml}
    ${r.title ? `<div style="font-size:13px;color:#666;margin-bottom:8px;">标题：${escapeHtml(r.title)}</div>` : ""}
    ${bodyHtml}
    <div class="toolbar">
      <button class="ghost" id="copyBtn">${r.body_format === "html" ? "复制为富文本（粘进公众号）" : "复制文案"}</button>
      ${styleBtn}
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
}

async function styleCurrent() {
  const name = state.active;
  if (!name) return;
  $("styleBtn") && ($("styleBtn").disabled = true);
  $("status").textContent = "✨ LLM 风格适配中…";
  try {
    const r = await fetch("/api/style", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: editor.value, platform: name }),
    }).then((res) => res.json());

    if (!r.available) {
      state.styleInfo[name] = { unavailable: true, note: r.note };
      $("status").textContent = "✨ " + (r.note || "不可用");
    } else if (r.error) {
      $("status").textContent = "✨ 失败：" + r.error;
    } else {
      state.styledOverride[name] = r.rendered;
      state.styleInfo[name] = { styled_md: r.styled, original_md: r.original, changed: r.changed, note: r.note };
      $("status").textContent = r.changed ? "✅ 已生成 LLM 风格化版本" : "风格化结果与原文一致";
    }
    renderActivePreview();
  } catch (e) {
    $("status").textContent = "✨ 失败：" + e.message;
  }
}

function revertStyle() {
  const name = state.active;
  delete state.styledOverride[name];
  delete state.styleInfo[name];
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

editor.addEventListener("input", debounce(refresh, 400));
$("publishBtn").addEventListener("click", publish);
init();
