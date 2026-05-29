"""平台无关的文档中间表示（IR）。

这是整个架构的基石：Markdown 先归一化成这棵树，各平台适配器只消费这棵树、
渲染各自格式。加平台 = 写一个消费 IR 的适配器，不动解析层。

设计要点（经架构评审锁定）：
- **行内结构 v1 就保留**（Strong/Emphasis/Link/CodeSpan/Image…），不塞进 text 字符串。
  因为行内变换正是平台差异最大处（公众号链接转脚注、小红书链接转括号注释等），
  推迟到 v2 会逼适配器二次解析字符串，越往后越脏。
- IR 自成一套节点，与解析库（mistune）的 AST 解耦：见 parser.py 的薄归一化层。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ============================ 行内节点 (inline) ============================
class Inline:
    """行内节点基类。"""


@dataclass
class Text(Inline):
    content: str


@dataclass
class Strong(Inline):
    children: list[Inline]


@dataclass
class Emphasis(Inline):
    children: list[Inline]


@dataclass
class Strikethrough(Inline):
    children: list[Inline]


@dataclass
class CodeSpan(Inline):
    content: str


@dataclass
class Link(Inline):
    url: str
    children: list[Inline]
    title: str | None = None


@dataclass
class Image(Inline):
    url: str
    alt: str = ""
    title: str | None = None


@dataclass
class LineBreak(Inline):
    pass


# ============================ 块级节点 (block) ============================
class Block:
    """块级节点基类。"""


@dataclass
class Heading(Block):
    level: int
    children: list[Inline]


@dataclass
class Paragraph(Block):
    children: list[Inline]


@dataclass
class CodeBlock(Block):
    code: str
    lang: str | None = None


@dataclass
class BlockQuote(Block):
    children: list[Block]  # 引用内部仍是块序列


@dataclass
class ListItem:
    children: list[Block]  # 列表项内部是块序列（支持嵌套列表/多段）


@dataclass
class ListBlock(Block):
    ordered: bool
    items: list[ListItem]


@dataclass
class ThematicBreak(Block):
    pass


@dataclass
class TableCell:
    children: list[Inline]
    align: str | None = None  # left | center | right | None


@dataclass
class Table(Block):
    header: list[TableCell]
    rows: list[list[TableCell]]


# ================================ 文档 ================================
@dataclass
class Document:
    title: str = ""
    blocks: list[Block] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    cover: str | None = None
    summary: str | None = None
    raw_markdown: str = ""  # 保留正文原文，供支持 markdown 的平台直用


# ============================ 遍历辅助 ============================
def inline_to_text(nodes: list[Inline]) -> str:
    """把行内节点拍平成纯文本（小红书等纯文本平台、alt 提取、字数统计用）。"""
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, Text):
            parts.append(n.content)
        elif isinstance(n, CodeSpan):
            parts.append(n.content)
        elif isinstance(n, (Strong, Emphasis, Strikethrough, Link)):
            parts.append(inline_to_text(n.children))
        elif isinstance(n, Image):
            parts.append(n.alt)
        elif isinstance(n, LineBreak):
            parts.append("\n")
    return "".join(parts)


def render_inline(nodes: list[Inline], visit) -> str:
    """通用行内遍历器，消除每个适配器重写递归骨架的重复。

    `visit(node, render_children) -> str`：适配器只写"每种节点产出什么"。
    `render_children()` 返回该节点子节点（如有）渲染拼接后的字符串。

    注意：`inline_to_text` 是「拍平成纯文本」（丢弃链接 URL 等格式信息，用于字数估算/
    alt 提取）；本函数是「按平台规则渲染」，能拿到 Link.url、自定义每种节点的输出，
    是适配器该用的入口。
    """

    def one(n: Inline) -> str:
        def render_children() -> str:
            kids = getattr(n, "children", None)
            return render_inline(kids, visit) if kids else ""

        return visit(n, render_children)

    return "".join(one(n) for n in nodes)


def iter_images(doc: Document) -> list[Image]:
    """深度遍历，收集文档中全部图片（用于图片清单/约束校验）。"""
    found: list[Image] = []

    def walk_inline(nodes: list[Inline]) -> None:
        for n in nodes:
            if isinstance(n, Image):
                found.append(n)
            elif isinstance(n, (Strong, Emphasis, Strikethrough, Link)):
                walk_inline(n.children)

    def walk_block(blocks: list[Block]) -> None:
        for b in blocks:
            if isinstance(b, (Heading, Paragraph)):
                walk_inline(b.children)
            elif isinstance(b, BlockQuote):
                walk_block(b.children)
            elif isinstance(b, ListBlock):
                for it in b.items:
                    walk_block(it.children)
            elif isinstance(b, Table):
                for c in b.header:
                    walk_inline(c.children)
                for row in b.rows:
                    for c in row:
                        walk_inline(c.children)

    walk_block(doc.blocks)
    return found


def plain_text(doc: Document) -> str:
    """整篇文档拍平成纯文本（粗略，用于字数估算/纯文本平台兜底）。"""
    out: list[str] = []

    def walk(blocks: list[Block]) -> None:
        for b in blocks:
            if isinstance(b, Heading):
                out.append(inline_to_text(b.children))
            elif isinstance(b, Paragraph):
                out.append(inline_to_text(b.children))
            elif isinstance(b, CodeBlock):
                out.append(b.code)
            elif isinstance(b, BlockQuote):
                walk(b.children)
            elif isinstance(b, ListBlock):
                for it in b.items:
                    walk(it.children)
            elif isinstance(b, Table):
                cells = [inline_to_text(c.children) for c in b.header]
                out.append(" ".join(cells))
                for row in b.rows:
                    out.append(" ".join(inline_to_text(c.children) for c in row))

    walk(doc.blocks)
    return "\n".join(p for p in out if p)
