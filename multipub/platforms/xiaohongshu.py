"""小红书平台适配器。

小红书正文是**纯文本**：不支持 markdown / HTML，靠 emoji + `#话题#` + 图片承载表达力，
且图片优先（纯文案曝光有限）。

本模块只做**确定性的「结构 → 纯文本」转换**：
- 去掉所有 markdown 符号（`#` / `**` / `>` / `` ` `` 等），行内格式只留文字；
- 链接渲染成 `文字(URL)` 的括号注释形式（小红书正文不可点，URL 作可读注释）；
- 图片不进正文文字，统一走 RenderedContent.images 清单；
- tags 渲染成结尾的 `#标签1# #标签2#`。

**不做 LLM 改写、不自动插 emoji、不自动截断**——风格化（emoji/语气）是后续独立的
LLM 风格适配模块，放进确定性 render 会破坏快照测试。约束超限只告警、不动原文。
"""

from __future__ import annotations

from ..core import document as D
from ..core.platform import (
    Platform,
    PlatformConstraints,
    RenderedContent,
    make_image_ref,
)
from ..core.registry import register


def _inline_to_text(nodes: list[D.Inline]) -> str:
    """行内 → 纯文本，与 D.inline_to_text 基本一致，但把 Link 渲染成 `文字(URL)`。

    D.inline_to_text 会把 Link 拍成纯文字、丢掉 URL；小红书要求保留 URL 作括号注释，
    故在此自定义。Image 不出现在正文文字里（走 images 清单）。
    """
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, D.Text):
            parts.append(n.content)
        elif isinstance(n, D.CodeSpan):
            parts.append(n.content)
        elif isinstance(n, D.Link):
            text = _inline_to_text(n.children)
            url = n.url or ""
            if url and text:
                parts.append(f"{text}({url})")
            elif url:
                parts.append(url)
            else:
                parts.append(text)
        elif isinstance(n, (D.Strong, D.Emphasis, D.Strikethrough)):
            parts.append(_inline_to_text(n.children))
        elif isinstance(n, D.LineBreak):
            parts.append("\n")
        # Image: 跳过，正文文字里不出现
    return "".join(parts)


def _blocks_to_text(blocks: list[D.Block], depth: int = 0) -> list[str]:
    """块序列 → 段落字符串列表（已去掉空段）。"""
    out: list[str] = []
    for b in blocks:
        if isinstance(b, D.Heading):
            out.append(_inline_to_text(b.children))
        elif isinstance(b, D.Paragraph):
            out.append(_inline_to_text(b.children))
        elif isinstance(b, D.CodeBlock):
            out.append(b.code)
        elif isinstance(b, D.BlockQuote):
            inner = _blocks_to_text(b.children, depth)
            # 引用用「…」包裹，便于读者识别这是引述内容
            for line in inner:
                out.append(f"「{line}」")
        elif isinstance(b, D.ListBlock):
            out.append(_list_to_text(b, depth))
        elif isinstance(b, D.Table):
            out.append(_table_to_text(b))
        # ThematicBreak: 跳过（纯文本里分隔线无意义，靠空行分隔）
    return [p for p in out if p.strip()]


def _list_to_text(block: D.ListBlock, depth: int) -> str:
    indent = "  " * depth
    lines: list[str] = []
    for idx, item in enumerate(block.items, start=1):
        sub = _blocks_to_text(item.children, depth + 1)
        prefix = f"{idx}. " if block.ordered else "· "
        if not sub:
            lines.append(f"{indent}{prefix}")
            continue
        # 列表项首段带前缀，其余（嵌套列表/多段）原样接上
        lines.append(f"{indent}{prefix}{sub[0]}")
        for extra in sub[1:]:
            lines.append(extra)
    return "\n".join(lines)


def _table_to_text(table: D.Table) -> str:
    """表格拍平成可读文本，每行用 ' | ' 连接。"""
    rows: list[str] = []
    if table.header:
        rows.append(" | ".join(_inline_to_text(c.children) for c in table.header))
    for row in table.rows:
        rows.append(" | ".join(_inline_to_text(c.children) for c in row))
    return "\n".join(rows)


@register("xiaohongshu")
class Xiaohongshu(Platform):
    display_name = "小红书"
    constraints = PlatformConstraints(
        supports_html=False,
        supports_markdown=False,
        max_title_len=20,
        max_body_len=1000,
        emoji_style="rich",
    )

    def render(self, doc: D.Document, opts: dict | None = None) -> RenderedContent:
        warnings: list[str] = []

        # 1) 正文：结构 → 纯文本段落，空行分隔
        paragraphs = _blocks_to_text(doc.blocks)
        body = "\n\n".join(paragraphs)

        # 2) 话题标签追加到末尾
        tags = [str(t).strip() for t in (doc.tags or []) if str(t).strip()]
        if tags:
            tag_line = " ".join(f"#{t}#" for t in tags)
            body = f"{body}\n\n{tag_line}" if body else tag_line

        # 3) 图片清单（图片优先）
        images = [make_image_ref(img.url, img.alt) for img in D.iter_images(doc)]
        for ref in images:
            if ref.note:
                warnings.append(ref.note)
        if not images:
            warnings.append("小红书图片优先，建议配图（纯文案曝光有限）")

        # 4) 字数约束：破坏性，只告警不截断
        title = doc.title or ""
        if self.constraints.max_title_len is not None and len(title) > self.constraints.max_title_len:
            warnings.append(
                f"标题 {len(title)} 字，超过小红书上限 {self.constraints.max_title_len} 字（未自动截断，请手动精简）"
            )
        if self.constraints.max_body_len is not None and len(body) > self.constraints.max_body_len:
            warnings.append(
                f"正文 {len(body)} 字，超过小红书上限 {self.constraints.max_body_len} 字（未自动截断，请手动精简）"
            )

        return RenderedContent(
            platform=self.name,
            title=title,
            body=body,
            body_format="text",
            images=images,
            warnings=warnings,
        )
