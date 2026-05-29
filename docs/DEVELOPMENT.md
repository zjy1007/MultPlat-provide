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
                    │  —— 源 Markdown + 平台画像，输出平台化 Markdown│
                    │     （按钮触发，不进实时预览链路；产物再走 render）│
                    └───────────────────┬─────────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                          ▼
        ┌───────────┐            ┌───────────┐             ┌───────────┐
        │ WeChat    │            │ Zhihu     │             │ Xiaohongshu│   …每个平台一个适配器
        │ Platform  │            │ Platform  │             │ Platform   │   （仅 render，纯函数）
        │ render()  │            │ render()  │             │ render()   │
        └─────┬─────┘            └─────┬─────┘             └─────┬─────┘
              ▼                        ▼                         ▼
        RenderedContent          RenderedContent           RenderedContent
              │                        │                         │
              ▼                        ▼                         ▼
        Publisher (v1 仅 Mock | 未来 WeChatDraft…)  ──► PublishResult
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

IR 是整个架构的基石——它让"加平台"互相解耦：加平台只需写一个消费 IR 的适配器，不动解析层。

**关键决策：行内结构 v1 就保留**（不塞进 `text` 字符串）。因为行内变换正是平台差异最大处——公众号链接转脚注、小红书链接转 `文字(URL)`、纯文本平台去强调——若推迟到 v2，会逼适配器二次解析字符串，越往后越脏。所以 IR 是一棵「块级 + 行内」双层节点树（实际实现见 `multipub/core/document.py`）：

```python
# document.py —— 平台无关的文档中间表示（节选）
# 行内节点
class Inline: ...
@dataclass class Text(Inline):          content: str
@dataclass class Strong(Inline):        children: list[Inline]
@dataclass class Emphasis(Inline):      children: list[Inline]
@dataclass class Strikethrough(Inline): children: list[Inline]
@dataclass class CodeSpan(Inline):      content: str
@dataclass class Link(Inline):          url: str; children: list[Inline]; title: str | None = None
@dataclass class Image(Inline):         url: str; alt: str = ""; title: str | None = None
@dataclass class LineBreak(Inline):     pass

# 块级节点
class Block: ...
@dataclass class Heading(Block):      level: int; children: list[Inline]
@dataclass class Paragraph(Block):    children: list[Inline]
@dataclass class CodeBlock(Block):    code: str; lang: str | None = None
@dataclass class BlockQuote(Block):   children: list[Block]
@dataclass class ListItem:            children: list[Block]
@dataclass class ListBlock(Block):    ordered: bool; items: list[ListItem]
@dataclass class ThematicBreak(Block): pass
@dataclass class TableCell:           children: list[Inline]; align: str | None = None
@dataclass class Table(Block):        header: list[TableCell]; rows: list[list[TableCell]]

@dataclass
class Document:
    title: str = ""
    blocks: list[Block] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    cover: str | None = None
    summary: str | None = None
    raw_markdown: str = ""               # 保留原文，供需要 markdown 的平台直用
```

**配套遍历辅助**（`document.py`）：
- `inline_to_text(nodes)` —— 拍平成纯文本（用于字数估算 / 图片 alt 提取，**会丢弃链接 URL**）。
- `render_inline(nodes, visit)` —— 通用行内遍历器，`visit(node, render_children)->str`，适配器只写"每种节点产出什么"，递归骨架复用。**这是适配器渲染行内的入口**（能拿到 `Link.url`）。
- `iter_images(doc)` / `plain_text(doc)` —— 收集全部图片 / 整篇拍平。

> 解析层 `parser.py` 是一层「薄归一化」：mistune 的 AST → 上述 IR。换解析器或加输入格式只改这一处，不波及任何适配器。

---

## 5. 平台适配器接口

新增平台只需实现这一个抽象类并注册，**不触碰核心**（开闭原则）。

**设计细化（相对早期草案）**：`Platform` 只负责 `render`（纯函数、无副作用，利于实时预览与快照测试）；**发布是独立关注点**，由 `Publisher` 承担、`pipeline` 编排——每个平台不必知道"如何发布"。

```python
# platform.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class PlatformConstraints:
    supports_html: bool = False       # 公众号/知乎/B站=True
    supports_markdown: bool = False   # 知乎=True，小红书=False
    max_title_len: int | None = None  # 小红书标题 20 字
    max_body_len: int | None = None   # 小红书正文 1000 字
    max_images: int | None = None
    allows_external_links: bool = True
    emoji_style: str = "none"         # "none" | "moderate" | "rich"

@dataclass
class ImageRef:                       # 适配产物中的图片及其可发布性判定
    url: str
    alt: str = ""
    is_local: bool = False
    note: str = ""                    # 非空表示需人工处理（本地图/svg 等）

@dataclass
class RenderedContent:
    platform: str
    title: str
    body: str                         # HTML / 文本 / markdown
    body_format: str                  # "html" | "markdown" | "text"
    images: list[ImageRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # 约束告警，不静默截断

class Platform(ABC):
    name: str = ""
    display_name: str = ""
    constraints: PlatformConstraints = PlatformConstraints()

    @abstractmethod
    def render(self, doc: "Document", opts: dict | None = None) -> RenderedContent:
        """格式适配：IR → 平台成品。纯函数，无副作用。"""

# 共享辅助：make_image_ref(url, alt) 按统一规则判定本地/公网/svg（编码自粘贴验证结论）
# 发布：见 publishers/base.py —— Publisher 抽象 + MockPublisher（v1 仅 Mock）
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

### 风格适配（StyleAdapter，`core/style.py`）
LLM 作**前置改写器**：源 Markdown → 平台化 Markdown（产物可被用户继续编辑，再走确定性 render）。因此 LLM **永不进实时预览/防抖链路**，下游全程可快照、可复现。

```python
class StyleAdapter(ABC):
    def available(self) -> bool: ...                       # 当前是否可用（LLM 需 key/SDK）
    def adapt(self, markdown: str, profile: PlatformProfile) -> str: ...  # MD → 平台化 MD

class NoopStyleAdapter(StyleAdapter): ...   # 直通，默认（= 关闭风格适配，回退纯格式适配）
class LLMStyleAdapter(StyleAdapter): ...    # 调用 Claude；complete 可注入便于测试；
                                            # 无 ANTHROPIC_API_KEY/SDK 时优雅降级（抛 StyleError）
```
平台画像 `PlatformProfile`（调性、目标读者、长度偏好、emoji 密度、宜忌）以 **`multipub/profiles/*.yaml`** 描述，便于不写代码就调风格。系统提示按平台稳定，开启 prompt caching 降本提速。

---

## 7. 富文本处理策略（行内结构 v1 已落地）

行内格式（加粗、链接、行内代码、删除线、图片）是平台差异最大、最容易踩坑的地方。实现选择：
- **IR 内置行内节点**（`Text/Strong/Emphasis/Strikethrough/CodeSpan/Link/Image/LineBreak`），用 `mistune` 的树状 AST 解析后归一化得到——**v1 就做，不推迟**。
- 适配器用 `render_inline(nodes, visit)` 精确控制每种平台对每种行内元素的呈现：公众号→内联样式 HTML、知乎→Markdown、小红书→纯文本且链接转 `文字(URL)`、B站→HTML。
- 已覆盖表格（`Table`）；公式、脚注等长尾元素为后续可扩展项。

> 这套行内结构正是「并行评审」推动落地的：早期草案曾想把行内推到 v2，评审指出会反噬，遂在 v1 落地——并在 Phase 1 两个适配器并行实现时，反向补出了 `render_inline` 通用遍历器（消除各适配器重复的递归骨架）。

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

## 9. 技术选型（实际实现）

| 项 | 选型 | 理由 |
|---|---|---|
| 语言 | **Python 3.11+** | Markdown 生态成熟、适配逻辑表达力强 |
| Markdown 解析 | **`mistune` 3.x** | 产出**树状 AST 且带行内子节点**，天然支撑"行内 v1"，比扁平 token 流更适合本场景 |
| front-matter | **`pyyaml`** | 解析标题/标签/封面等元数据 |
| LLM | **Anthropic Claude**（`anthropic` SDK，可选 `[llm]`） | 风格适配，开启 prompt caching；无 key 优雅降级 |
| **Web 后端** | **FastAPI + uvicorn**（可选 `[web]`） | 暴露 pipeline，异步、自带 OpenAPI 文档 |
| **Web 前端** | **原生 HTML + JS（零构建）** | 单页编辑 + 预览，无 Node 构建链；复杂化后再迁 React |
| 测试 | **`pytest`** | 适配是确定性转换，最适合回归；LLM 路径用注入的假 complete，不打真实 API |

---

## 10. 目录结构（实际）

```
multipub/
├── core/
│   ├── document.py        # IR：行内/块级节点 + 遍历辅助(inline_to_text/render_inline/iter_images)
│   ├── parser.py          # 薄归一化层：mistune AST → Document IR（含 front-matter）
│   ├── platform.py        # Platform 抽象 + RenderedContent/Constraints/ImageRef + make_image_ref
│   ├── registry.py        # @register 平台注册表
│   ├── pipeline.py        # 编排：adapt()只适配 / run()适配+发布
│   └── style.py           # StyleAdapter / NoopStyleAdapter / LLMStyleAdapter + 画像加载
├── platforms/             # 每个平台一个适配器（render-only），import 即注册
│   ├── wechat.py          # 公众号 → 内联样式 HTML
│   ├── xiaohongshu.py     # 小红书 → 纯文本 + 话题
│   ├── zhihu.py           # 知乎 → Markdown
│   └── bilibili.py        # B站专栏 → HTML
├── publishers/
│   └── base.py            # Publisher 抽象 + MockPublisher（v1 仅此）
├── profiles/              # 各平台风格画像（YAML）：wechat/xiaohongshu/zhihu/bilibili
├── web/
│   ├── app.py             # FastAPI：/api/platforms /api/adapt /api/publish /api/style
│   └── static/            # index.html + app.js（单页：编辑器 + 多平台实时预览）
tests/                     # test_core_contract / test_<platform> / test_web / test_style
examples/article.md · validation/（粘贴验证套件）
```

> 实测兑现"加平台零改核心"：知乎、B站两个适配器各只新增 `platforms/<name>.py` + 注册一行，`core/` 一行未改。

---

## 11. 关键风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 平台格式细节多、易变 | 适配产物不达预期 | 快照测试 + `warnings` 透出 + 真人 review 样例 |
| 公众号发布门槛（认证/白名单） | 真实发布跑不通 | 默认 Mock，真实发布作为可选；文档写清前置条件 |
| 富文本（表格/公式/行内）覆盖不全 | 复杂文章失真 | §7 渐进策略，先覆盖高频元素 |
| LLM 改写不稳定/有成本 | 风格适配不可控 | 可关闭；输出可 diff 预览；prompt 模板化 + 缓存 |
| 图片上传链路（公众号 media_id） | 真实发布失败 | 单独的图片处理子流程 + 重试 |
