# MultiPub —— 多平台内容发布工具

> 一次写作，自动适配 **公众号 / 知乎 / B站专栏 / 小红书** 的格式与风格，左写右预览，一键（模拟）发布。

🎬 **演示视频**：https://www.bilibili.com/video/BV12eVU6nEqP/?vd_source=89c4b5f63bc49edbb0e747603e076480
<img width="1470" height="832" alt="image" src="https://github.com/user-attachments/assets/38487693-d702-49c0-a6f2-5439b08aa9de" />

---

## 📌 题目与解法

> **题目二｜多平台内容发布工具**：很多创作者需要在公众号、知乎、B站、小红书等平台同步发布内容，但格式适配很麻烦。要求：用户输入内容后**自动适配各平台格式与风格**，支持**一键发布（可选模拟发布）**，并给出**扩展更多平台的架构设计**。

MultiPub 的回答：创作者只写**一份 Markdown**，工具把它解析成一棵**平台无关的中间表示（IR）**，再由各平台适配器渲染成各自的成品——

| 题目要求 | 本项目实现 |
|---|---|
| 自动适配各平台**格式** | `Markdown → IR → Platform.render` 确定性渲染，4 平台开箱即用，实时预览 |
| 自动适配各平台**风格** | 可选 LLM 按平台画像改写语气，与格式适配**严格分离**、不污染确定性链路 |
| **一键发布（可选模拟）** | `Publisher` 接口 + 一键模拟发布回执；真实发布接口已预留 |
| **扩展更多平台的架构** | 注册表 + 纯函数适配器：新增平台核心层零改动（见 [§扩展更多平台](#-扩展更多平台)） |

---

## ✨ 核心能力

- **统一写作**：只写一份 Markdown（支持 front-matter 元数据：标题、标签、封面）。
- **格式适配**：自动转换为各平台需要的格式
  - 公众号 → 带**内联样式**的 HTML（公众号编辑器会剥 class，必须内联）
  - 知乎 → 编辑器支持的 Markdown/HTML
  - B站专栏 → HTML 片段
  - 小红书 → 口语化纯文本 + emoji + 话题标签 + 字数约束提示
- **风格适配（可选）**：调用 LLM 按平台调性改写语气，结果以「待采用」呈现，用户**采用 / 舍弃**，绝不自动覆盖原文。
- **实时预览 + 一键模拟发布**：左侧写、右侧实时看各平台成品；一键模拟发布得到回执，成品可直接复制去平台粘贴/上传。
- **图片清单**：逐图列出可发布性（远程直链✓ / 本地图需手动上传✗ / SVG 部分平台不支持），正文里渲染成可见的「【图N】」占位与之对应。
- **可扩展架构**：新增一个平台 = 实现一个 `Platform` 适配器并注册，核心代码零改动。

---

## 🚀 快速开始

```bash
# 安装依赖（含 Web 与可选 LLM 风格适配）
pip install -e ".[web,llm]"

# 启动 Web 工具
uvicorn multipub.web.app:app --reload
# 打开 http://127.0.0.1:8000 ，左侧写 Markdown，右侧实时多平台预览
```

> **LLM 风格适配（可选）**：在页面顶部「✨ LLM 设置」选择厂商（DeepSeek / 千问 Qwen / 豆包 Doubao）并粘贴对应 API key 即可，**无需改环境变量**。key 仅存于浏览器、随请求内存流转，**不落服务器、不入日志**。
> 不填 key 也能用：格式适配、实时预览、模拟发布全部可用。

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

---

## 🧱 支持平台

| 平台 | 格式适配 | 风格适配(可选) | 发布 | 关键约束 |
|---|---|---|---|---|
| 公众号 | ✅ HTML 内联样式 | ✅ | 模拟 | 外链不可点（提示转脚注） |
| 小红书 | ✅ 纯文本+emoji+话题 | ✅ | 模拟 | 标题 ≤20 字、正文 ≤1000 字 |
| 知乎 | ✅ Markdown/HTML | ✅ | 模拟 | — |
| B站专栏 | ✅ HTML | ✅ | 模拟 | — |

---

## 🏗️ 架构设计

分层清晰、单一职责，**解析 / 适配 / 风格 / 发布 / Web** 各司其职：

```
 Markdown
    │  parse（mistune 薄归一化层）
    ▼
 Document  ← 平台无关的中间表示 IR（保留行内结构：链接/加粗/图片…）
    │
    ├──（可选）StyleAdapter：LLM 按平台画像改写语气   ← 非确定性，按钮触发
    │                                                  永不进实时预览链路
    ▼
 Platform.render(doc) ──┐  纯函数、无副作用（可快照测试）
                        │  + PlatformConstraints 约束校验 → warnings
    ▼                   │
 RenderedContent  ──────┘  (title / body / body_format / images / warnings)
    │
    ▼  Publisher.publish()
 PublishResult  ← MockPublisher（v1）｜真实发布器（接口已预留）
```

**关键设计决策**

- **平台无关 IR**：先把 Markdown 归一化成一棵树，适配器只消费 IR。行内结构（链接、加粗）**v1 就保留**——因为平台差异最大处正是行内变换（公众号链接转脚注、小红书转括号注释），塞进字符串会逼适配器二次解析。
- **`render` 是纯函数**：无副作用 → 实时预览可随输入防抖刷新，且能做**快照测试**。
- **格式适配 vs 风格适配分离**：格式适配确定性、可复现；LLM 风格改写是**可选前置改写器**（输出仍是 Markdown，可继续编辑再走确定性 render），永不进预览/防抖链路。
- **约束驱动告警**：每个平台用 `PlatformConstraints` 声明硬约束，超限只告警、不擅自改稿。
- **发布是独立关注点**：平台只管 `render`，不必知道"如何发布"；发布由 `Publisher` 承担、`pipeline` 编排。

**目录结构**

```
multipub/
├── core/
│   ├── document.py    # IR 节点定义 + 遍历辅助
│   ├── parser.py      # Markdown → IR（解耦 mistune AST）
│   ├── platform.py    # Platform 契约 / Constraints / ImageRef
│   ├── registry.py    # @register 平台注册表（扩展核心）
│   ├── pipeline.py    # 编排：adapt()（预览）/ run()（发布）
│   └── style.py       # LLM 风格适配（可选、可注入、优雅降级）
├── platforms/         # 各平台适配器（wechat / zhihu / bilibili / xiaohongshu）
├── profiles/          # 各平台风格画像 *.yaml（喂 LLM，非程序员可调）
├── publishers/        # Publisher 契约 + MockPublisher
└── web/
    ├── app.py         # FastAPI：/api/{platforms,adapt,publish,style,providers,upload}
    ├── imagehost.py   # 可插拔图床（本地 / imgbb）
    └── static/        # 零构建单页前端（实时预览 + 可拖拽分栏）
```

---

## 🧩 扩展更多平台

新增一个平台**不动核心层**，三步即可：

```python
# 1) multipub/platforms/toutiao.py
from ..core.platform import Platform, PlatformConstraints, RenderedContent
from ..core.registry import register

@register("toutiao")
class ToutiaoPlatform(Platform):
    display_name = "今日头条"
    constraints = PlatformConstraints(supports_html=True, max_title_len=30)

    def render(self, doc, opts=None) -> RenderedContent:
        ...  # 消费 IR，产出该平台成品（纯函数）
        return RenderedContent(platform=self.name, title=doc.title,
                               body=body, body_format="html")
```

```python
# 2) multipub/platforms/__init__.py —— 导入以触发 @register
from . import bilibili, wechat, xiaohongshu, zhihu, toutiao
```

```yaml
# 3)（可选）multipub/profiles/toutiao.yaml —— 风格画像，启用 LLM 风格适配
display_name: 今日头条
tone: 通俗、信息密度高、强标题
audience: 资讯类泛读者
```

完成后：`/api/platforms` 自动多出该平台，前端自动出 Tab、字数提示、预览与模拟发布——**parser / pipeline / registry / web 全部零改动**（开闭原则）。可选再加 `tests/test_toutiao.py` 快照测试锁定输出。

> 同理，**真实发布**只需新增一个 `Publisher` 实现（如公众号官方草稿 API），适配器与核心零改动。

---

## 🔬 工程质量

| 维度 | 现状 |
|---|---|
| 测试 | **100 个测试全绿**（8 个文件）：每平台快照测试 + 核心契约 + Web 接口 + LLM 风格 + 图床 |
| 协作 | **12 个合并 PR**，按功能分支开发（core → adapters → web → llm → ui …），commit 粒度清晰 |
| 健壮性 | LLM 缺 key / 缺依赖 / API 报错全部**优雅降级**，主流程不崩；上传校验扩展名；HTML 输出全程转义防注入 |
| 可读性 | ABC 接口契约、dataclass 数据模型、纯函数渲染、模块级中文 docstring 说明设计取舍 |

```bash
pip install -e ".[dev,web,llm]"
pytest -q          # 100 passed
```

---

## 💡 创新与亮点

- **平台无关 IR + 行内结构保留**：把"平台差异最大"的行内变换收敛到统一遍历器，新平台白拿。
- **风格适配「待采用」工作流**：LLM 改写先预览、用户采用/舍弃，可控、可回退，不黑箱覆盖。
- **网页直填多供应商 key、仅内存流转不落盘**：零配置启用 LLM，又不牺牲凭证安全。
- **图片可发布性判定**（编码自真人粘贴验证结论）：远程直链✓ / 本地✗ / SVG✗，配「【图N】」占位 + 清单，把"复制过去图丢了"这类坑前置暴露。
- **交互**：实时预览、可拖拽分栏自适应、Tab 文件夹页签随平台主题色变化。

---

## 🧭 设计边界

> **v1 全程模拟发布**：生成"可直接粘贴/上传"的成品 + 模拟回执，不接任何平台 API（无凭证/认证门槛，开箱即用）。真实发布（如公众号官方草稿 API）作为未来扩展，`Publisher` 接口已预留。详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) §8 可行性分析。

## 📁 文档

- [开发文档 DEVELOPMENT.md](docs/DEVELOPMENT.md) —— 架构、数据模型、平台适配器、扩展方式
- [计划文档 PLAN.md](docs/PLAN.md) —— 分阶段里程碑、范围与风险

## 📄 License

MIT
