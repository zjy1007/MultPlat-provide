# 开发文档 —— MultiPub 多平台内容发布工具

## 1. 目标与非目标

### 目标
1. 创作者**只写一份 Markdown**，工具自动适配多平台格式与风格。
2. 适配**确定、可预览、可复用**：同样输入产出同样结果。
3. **一键发布**：默认模拟发布；公众号支持真实草稿箱发布。
4. 架构**易扩展**：新增平台不改核心代码。

### 非目标（v1 明确不做）
- **不接任何平台真实发布 API**（含公众号）—— v1 全程模拟发布，避免凭证/认证/IP 白名单/反爬等门槛拖慢核心价值落地。`Publisher` 接口已为真实发布预留，未来扩展不动核心（见 §8）。
- 不做内容创作/选题/配图生成（聚焦"适配 + 发布"环节）。
- 不做多账号矩阵管理、数据分析看板（后续可扩展）。

### 已确认形态
- **Web 可视化优先**：FastAPI 后端复用核心适配层，轻量单页前端做编辑 + 多平台实时预览（见 §3.1）。
- 四平台全做（公众号、小红书先行），LLM 风格适配为可选模块。

---

## 2. 可行性结论（先读这一节）

| 能力 | 结论 | 依据 |
|---|---|---|
| 格式适配 | ✅ 核心可行 | 本地确定性转换，技术成熟（Markdown AST → 各平台渲染） |
| 风格适配 | ✅ 可行（可选） | LLM 改写，按平台 prompt 模板；可降级为纯格式适配 |
| 公众号真实发布 | 🟡 可行有门槛 | 官方 `draft/add` API，需**已认证服务号**的 appid/secret + IP 白名单 |
| 知乎/B站/小红书真实发布 | 🔴 不做 | 无官方开放发布 API；逆向登录态对抗反爬，违反 ToS 且维护成本极高 |
| 模拟发布 | ✅ 可行 | 产出可直接粘贴/上传的成品 + 模拟回执 |

**设计取舍**：把"真实发布"从核心路径中解耦成一个可插拔的 `Publisher`，默认 `MockPublisher`。这样工具的主价值（适配 + 预览成品）**不依赖任何平台 API 的可用性**，既能立刻落地，又给未来真实发布留好接口。

---

## 3. 整体架构

采用经典的**编译器式分层管线**：源格式 → 中间表示(IR) → 各目标格式。这是支撑"一次写作、多平台输出"和"易扩展"的关键。

```
                    ┌─────────────────────────────────────────────┐
   article.md ──►   │  Parser:  Markdown + front-matter → Document │
   (+ 元数据)        │           (统一中间表示 IR / AST)            │
                    └───────────────────┬─────────────────────────┘
                                        │  Document(IR)
                                        ▼
                    ┌─────────────────────────────────────────────┐
                    │  StyleAdapter (可选):  LLM 按平台调性改写     │
                    │  —— 输入 IR + 平台画像，输出改写后的 IR       │
                    └───────────────────┬─────────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                          ▼
        ┌───────────┐            ┌───────────┐             ┌───────────┐
        │ WeChat    │            │ Zhihu     │             │ Xiaohongshu│   …每个平台一个适配器
        │ Platform  │            │ Platform  │             │ Platform   │
        │ render()  │            │ render()  │             │ render()   │
        │ publish() │            │ publish() │             │ publish()  │
        └─────┬─────┘            └─────┬─────┘             └─────┬─────┘
              ▼                        ▼                         ▼
        RenderedContent          RenderedContent           RenderedContent
              │                        │                         │
              ▼                        ▼                         ▼
        Publisher (Mock | WeChatDraft | …)  ──► PublishResult ──► report.json
```

### 分层职责
| 层 | 职责 | 是否依赖外部服务 |
|---|---|---|
| **Parser** | Markdown + front-matter → `Document` IR | 否 |
| **StyleAdapter**（可选） | 按平台调性改写 IR（语气/长度/emoji） | 是（LLM） |
| **Platform.render** | IR → 该平台 `RenderedContent`（格式适配） | 否 |
| **Platform.publish** | 调用对应 `Publisher` 发布 | 取决于 Publisher |
| **Publisher** | 模拟发布（v1 仅 Mock），返回回执 | Mock=否 |
| **Pipeline** | 编排上述步骤、聚合报告 | 否 |
| **Web API / 前端** | HTTP 暴露 pipeline + 编辑/预览 UI | 否 |

### 3.1 Web 形态架构

核心层（Parser/Platform/Publisher/Pipeline）是纯逻辑库，**与入口无关**。Web 只是在其外包一层 HTTP + UI；未来加 CLI 同理，核心零改动。

```
┌──────────────────────────────────────────────────────────┐
│  前端单页（零构建：HTML + 原生 JS）                          │
│  ┌──────────────────┐   ┌──────────────────────────────┐  │
│  │ Markdown 编辑器    │   │ 多平台预览 Tab               │  │
│  │ (左)              │──►│ 公众号(iframe渲染HTML)        │  │
│  │ 输入防抖 →fetch    │   │ 小红书(文本+字数/告警)        │  │
│  │                  │◄──│ 知乎 / B站 …                  │  │
│  └──────────────────┘   │ [模拟发布] [复制成品]         │  │
│                         └──────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────┘
                                 │  HTTP (JSON)
                                 ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI                                                   │
│   POST /api/adapt    {markdown, platforms[], style?}       │
│        → pipeline.adapt → RenderedContent[]（含 warnings） │
│   POST /api/publish  {markdown, platforms[]}               │
│        → MockPublisher → PublishResult[]                   │
│   GET  /api/platforms → 各平台元数据（约束、画像、是否支持）│
└───────────────────────────────┬──────────────────────────┘
                                 ▼
                       core 层（与 CLI 完全复用）
```

**前端选型**：v1 用零构建的单页（静态 HTML + 原生 JS，FastAPI `StaticFiles` 托管），避免 Node 构建链拖慢启动。HTML 类平台预览用 sandbox `iframe` 隔离渲染；若后续 UI 复杂化再迁移到 React/Vite，后端不变。

---

## 4. 数据模型（中间表示 IR）

IR 是整个架构的基石——**它让"加平台"和"加输入格式"互相解耦**（N 个输入 + M 个平台从 N×M 降为 N+M）。

```python
# document.py —— 平台无关的文档中间表示
from dataclasses import dataclass, field
from enum import Enum

class BlockType(Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    IMAGE = "image"
    CODE = "code"
    QUOTE = "quote"
    LIST = "list"
    TABLE = "table"
    DIVIDER = "divider"

@dataclass
class Block:
    type: BlockType
    text: str = ""                       # 纯文本/富文本
    level: int = 0                       # heading 级别 / list 缩进
    meta: dict = field(default_factory=dict)  # 如 image: {src, alt}; code: {lang}

@dataclass
class Document:
    title: str
    blocks: list[Block]
    tags: list[str] = field(default_factory=list)
    cover: str | None = None
    summary: str | None = None
    raw_markdown: str = ""               # 保留原文，供需要 markdown 的平台直用
```

> 富文本（加粗/链接/行内代码）的处理方式由实现深度决定：v1 可先用"段落级 HTML 内联 span"或保留行内 markdown，§7 详述渐进策略。

---

## 5. 平台适配器接口

新增平台只需实现这一个抽象类并注册，**不触碰核心**（开闭原则）。

```python
# platform.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PlatformConstraints:
    supports_html: bool          # 公众号/B站=True
    supports_markdown: bool      # 知乎=部分True，小红书=False
    max_title_len: int | None    # 小红书标题 20 字
    max_body_len: int | None     # 小红书正文 1000 字
    max_images: int | None
    allows_external_links: bool  # 公众号正文不能放外链
    emoji_style: str             # "none" | "moderate" | "rich"

@dataclass
class RenderedContent:
    platform: str
    title: str
    body: str                    # HTML 或 文本 或 markdown
    body_format: str             # "html" | "markdown" | "text"
    images: list[str]
    warnings: list[str]          # 适配过程中触发的约束告警（如截断）

class Platform(ABC):
    name: str
    constraints: PlatformConstraints

    @abstractmethod
    def render(self, doc: "Document", opts: dict) -> RenderedContent:
        """格式适配：IR → 平台成品。纯函数，无副作用。"""

    @abstractmethod
    def publish(self, content: RenderedContent, creds: dict | None) -> "PublishResult":
        """发布：默认委托给注入的 Publisher。"""
```

### 注册机制（插件化）
```python
# registry.py
_REGISTRY: dict[str, type[Platform]] = {}

def register(name: str):
    def deco(cls):
        _REGISTRY[name] = cls
        return cls
    return deco

def get_platform(name: str) -> Platform:
    return _REGISTRY[name]()

# 扩展方式一：内置平台用装饰器注册
@register("xiaohongshu")
class Xiaohongshu(Platform): ...

# 扩展方式二：第三方通过 entry_points 注册（pyproject.toml）
#   [project.entry-points."multipub.platforms"]
#   wechat = "multipub.platforms.wechat:WeChat"
```

---

## 6. 各平台适配规则（关键差异）

| 平台 | 输出格式 | 关键约束/处理 |
|---|---|---|
| **公众号** | HTML（**样式必须内联** `style="..."`） | 编辑器剥离 class；正文禁外链（转脚注/“阅读原文”）；图片需先传素材库换 media_id |
| **知乎** | Markdown / HTML | 代码块、公式（`$$`）支持好；外链可保留；标签映射到话题 |
| **B站专栏** | HTML 片段 | 图片需上传换站内链接；支持卡片；emoji 适度 |
| **小红书** | 纯文本 | 标题 ≤20 字、正文 ≤1000 字（超出告警/截断）；**口语化 + emoji + `#话题#`**；图文为主，长文需拆分配图建议 |

### 图片处理（v1，粘贴验证已确认 2026-05-29）

手工粘贴验证结论：公众号粘贴**保留全部内联样式**（标题/加粗/引用/深色代码块/行内代码/列表均存活）；图片方面——

| 图片来源 | 结果 | v1 处理 |
|---|---|---|
| 本地图 `./x.png` | ✗ 带不过去 | 检测为本地 → 报 `warning` + 列入「待手动上传清单」 |
| 公网直链 `.png`/`.jpg` | ✓ 粘贴可显示 | 直接放行 |
| `.svg` | ✗ 公众号不支持内容 SVG | 报 `warning`，建议转 png |

> 隐藏前置：公网图需「图床直链 + 不被防盗链拦 + host 可达」。v1 不做上传管线，只做检测/告警 + 有序图片清单。
> 已知发布期细节：公众号**正式发文**中正文外链对读者不可点（平台禁用）。因此「链接转脚注」保留为**可配置项**，后续实现，不影响 v1。

**两类适配要分清**：
1. **格式适配（确定性，必做）**：结构转换、内联样式、字数约束、图片占位。`render()` 内完成。
2. **风格适配（LLM，可选）**：语气改写、emoji 注入、长度伸缩。`StyleAdapter` 完成，可关闭。

### 风格适配（StyleAdapter）
```python
class StyleAdapter(ABC):
    @abstractmethod
    def adapt(self, doc: Document, platform: PlatformProfile) -> Document: ...

# LLM 实现：按平台画像构造 prompt，调用 LLM API
class LLMStyleAdapter(StyleAdapter): ...
# 降级实现：原样返回（无 LLM 时）
class NoopStyleAdapter(StyleAdapter): ...
```
平台画像 `PlatformProfile`（调性、目标读者、长度偏好、emoji 密度、禁忌）以**配置/YAML**描述，便于不写代码就调风格。

---

## 7. 富文本处理的渐进策略

行内格式（加粗、链接、行内代码、图片）是最容易踩坑的地方，分三档落地：
- **v1（够用）**：用成熟库（`markdown-it-py` / `mistune`）把每个块渲染成 HTML，平台 renderer 在块级 HTML 上做内联样式替换 / 文本提取。小红书走"strip 成纯文本 + 保留链接为括号注释"。
- **v2（精细）**：IR 内引入行内节点（`InlineText/Bold/Link/Code`），renderer 精确控制每种平台对行内元素的呈现。
- **v3**：表格、公式、脚注等长尾元素的逐平台优化。

---

## 8. 真实发布的可行性细节（v1 不做，仅记录与预留）

> v1 全程模拟发布。以下为未来扩展真实发布时的参考，`Publisher` 接口已为此预留，届时新增实现即可，不动核心。

### 公众号（唯一可靠的真实通道）
- API：`https://api.weixin.qq.com/cgi-bin/draft/add`（新增草稿）。
- 前置：**已认证的服务号**、`AppID/AppSecret`、服务器 IP 加入白名单、`access_token` 缓存（7200s）。
- 图片：正文图片须先 `media/uploadimg` 或 `material/add_material` 换 `media_id/url`，再嵌入 HTML。
- 设计：`WeChatDraftPublisher` 实现 `Publisher`，凭证从环境变量/配置读取，**绝不硬编码**。失败要有清晰错误（token 过期、IP 未白名单、未认证）。

### 知乎 / B站 / 小红书
- 均**无官方开放的内容发布 API**。
- 逆向方案（模拟登录、抓 cookie、构造私有接口）的问题：违反平台 ToS、有账号封禁风险、接口随时变更、需处理验证码/风控——**不适合作为产品能力**。
- v1 处理：生成**可直接粘贴的成品**（小红书给纯文案、知乎给 markdown、B站给 HTML）+ `MockPublisher` 模拟回执。这覆盖了创作者 90% 的实际痛点（适配麻烦），而非发布动作本身。
- 留口：`Publisher` 是接口，未来若某平台开放 API（或用户自担风险接半自动浏览器方案），新增一个 Publisher 即可，不动核心。

---

## 9. 技术选型（推荐，待确认）

| 项 | 选型 | 理由 |
|---|---|---|
| 语言 | **Python 3.11+** | Markdown 生态成熟、适配逻辑表达力强、易写 CLI |
| Markdown 解析 | `markdown-it-py` | token 流可控，扩展性好 |
| CLI | `typer` / `click` | 子命令清晰 |
| 配置 | `pydantic` + YAML | 平台画像/约束声明式管理 |
| LLM | LLM API | 风格适配，带缓存 |
| **Web 后端** | **FastAPI + uvicorn** | 暴露 pipeline，异步、自带 OpenAPI 文档 |
| **Web 前端** | **原生 HTML + JS（零构建）** | 单页编辑 + 预览，无 Node 构建链；复杂化后再迁 React |
| 测试 | `pytest` + 快照测试 | 适配是确定性转换，最适合快照回归 |

---

## 10. 目录结构（规划）

```
multipub/
├── core/
│   ├── document.py        # IR 数据模型
│   ├── parser.py          # markdown → Document
│   ├── platform.py        # Platform / RenderedContent / Constraints 抽象
│   ├── registry.py        # 平台注册表
│   ├── pipeline.py        # 编排：parse → adapt → render → publish
│   └── style/
│       ├── adapter.py     # StyleAdapter 抽象 + Noop
│       └── llm.py         # LLMStyleAdapter
├── platforms/
│   ├── wechat.py
│   ├── zhihu.py
│   ├── bilibili.py
│   └── xiaohongshu.py
├── publishers/
│   └── base.py            # Publisher 抽象 + MockPublisher（v1 仅此）
├── profiles/              # 各平台风格画像（YAML）
│   ├── wechat.yaml
│   └── xiaohongshu.yaml
├── web/
│   ├── app.py             # FastAPI：/api/adapt /api/publish /api/platforms
│   └── static/
│       ├── index.html     # 单页：编辑器 + 多平台预览
│       └── app.js
└── tests/
    ├── fixtures/          # 输入样例 + 期望产物快照
    └── test_*.py
```

---

## 11. 关键风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 平台格式细节多、易变 | 适配产物不达预期 | 快照测试 + `warnings` 透出 + 真人 review 样例 |
| 公众号发布门槛（认证/白名单） | 真实发布跑不通 | 默认 Mock，真实发布作为可选；文档写清前置条件 |
| 富文本（表格/公式/行内）覆盖不全 | 复杂文章失真 | §7 渐进策略，先覆盖高频元素 |
| LLM 改写不稳定/有成本 | 风格适配不可控 | 可关闭；输出可 diff 预览；prompt 模板化 + 缓存 |
| 图片上传链路（公众号 media_id） | 真实发布失败 | 单独的图片处理子流程 + 重试 |
