# MultiPub —— 多平台内容发布工具

> 一次写作，多平台适配，一键（模拟）发布。

创作者用 Markdown 写一次内容，**Web 工具**自动适配 **公众号 / 知乎 / B站专栏 / 小红书** 等平台的格式与风格，左边写、右边实时预览各平台成品，一键模拟发布。

---

## ✨ 核心能力

- **统一写作**：只写一份 Markdown（带可选 front-matter 元数据：标题、标签、封面）。
- **格式适配**：自动转换为各平台需要的格式
  - 公众号 → 带内联样式的 HTML（编辑器会剥离 class，必须内联）
  - 知乎 → 其编辑器支持的格式
  - B站专栏 → HTML 片段
  - 小红书 → 口语化纯文本 + emoji + 话题标签 + 字数裁剪
- **风格适配（可选）**：调用 LLM 按平台调性改写语气（小红书活泼带 emoji、知乎专业长文等）。
- **实时预览 + 一键模拟发布**：浏览器里左侧写 Markdown，右侧实时看各平台成品；一键模拟发布得到回执，可直接复制成品去平台粘贴/上传。
- **可扩展架构**：新增一个平台 = 实现一个 `Platform` 适配器并注册，无需改动核心。

## 🚀 快速开始

```bash
# 安装依赖（含 Web 与可选 LLM 风格适配）
pip install -e ".[web,llm]"

# 启动 Web 工具
uvicorn multipub.web.app:app --reload
# 打开 http://127.0.0.1:8000 ，左侧写 Markdown，右侧实时多平台预览

# （可选）启用 LLM 风格适配：配置 key 后重启
export ANTHROPIC_API_KEY=sk-...
```

> 不配 `ANTHROPIC_API_KEY` 也能用：格式适配、实时预览、模拟发布全部可用；仅“✨ LLM 风格适配”按钮会提示未启用并优雅降级。

### 输入示例 `article.md`

```markdown
---
title: 我如何用一周搭出多平台发布工具
tags: [效率工具, Python]
cover: ./cover.png
---

## 背景

很多创作者需要在多个平台同步发布……

![架构图](./arch.png)

> 一次写作，多平台适配。
```

## 🧱 支持平台

| 平台 | 格式适配 | 风格适配(可选) | 发布 |
|---|---|---|---|
| 公众号 | ✅ HTML 内联样式 | ✅ | 模拟 |
| 小红书 | ✅ 纯文本+emoji+话题 | ✅ | 模拟 |
| 知乎 | ✅ Markdown/HTML | ✅ | 模拟 |
| B站专栏 | ✅ HTML | ✅ | 模拟 |

> **v1 全程模拟发布**：生成"可直接粘贴/上传"的成品 + 模拟回执，不接任何平台 API（无凭证/认证门槛）。真实发布（如公众号官方草稿 API）作为未来扩展，`Publisher` 接口已预留。详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) §8 可行性分析。

## 📁 文档

- [开发文档 DEVELOPMENT.md](docs/DEVELOPMENT.md) —— 架构、数据模型、平台适配器、扩展方式
- [计划文档 PLAN.md](docs/PLAN.md) —— 分阶段里程碑、范围与风险

## 📄 License

MIT
