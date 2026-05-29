"""薄归一化层：Markdown → mistune AST → 我们的 Document IR。

为什么要这层"防腐"：适配器只认 Document IR，不直接碰 mistune 的 token 形状。
将来换解析器、加输入格式或让 LLM 改写 IR，都只改这一处，不波及任何适配器。
"""

from __future__ import annotations

import re

import mistune
import yaml

from .document import (
    Block,
    BlockQuote,
    CodeBlock,
    CodeSpan,
    Document,
    Emphasis,
    Heading,
    Image,
    Inline,
    LineBreak,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Strikethrough,
    Strong,
    Table,
    TableCell,
    Text,
    ThematicBreak,
    inline_to_text,
)

# 纯 AST 解析器（renderer=None 即返回 token 树），开启常用插件
_md = mistune.create_markdown(
    renderer=None,
    plugins=["table", "strikethrough", "url"],
)

_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_front_matter(text: str) -> tuple[dict, str]:
    """切出 YAML front-matter（标题/标签/封面等元数据）与正文。"""
    m = _FRONT_MATTER.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[m.end() :]


def parse(text: str) -> Document:
    meta, body = split_front_matter(text)
    blocks = _norm_blocks(_md(body))

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return Document(
        title=str(meta.get("title", "") or ""),
        blocks=blocks,
        tags=list(tags),
        cover=meta.get("cover"),
        summary=meta.get("summary"),
        raw_markdown=body,
    )


# ----------------------------- 块级归一化 -----------------------------
def _norm_blocks(tokens: list[dict]) -> list[Block]:
    out: list[Block] = []
    for tok in tokens:
        b = _norm_block(tok)
        if b is not None:
            out.append(b)
    return out


def _norm_block(tok: dict) -> Block | None:
    t = tok["type"]
    if t == "blank_line":
        return None
    if t == "heading":
        return Heading(level=tok["attrs"]["level"], children=_norm_inlines(tok.get("children", [])))
    if t == "paragraph":
        return Paragraph(children=_norm_inlines(tok.get("children", [])))
    if t == "block_code":
        info = (tok.get("attrs") or {}).get("info")
        lang = info.split()[0] if info else None
        code = tok.get("raw", "")
        return CodeBlock(code=code[:-1] if code.endswith("\n") else code, lang=lang)
    if t == "block_quote":
        return BlockQuote(children=_norm_blocks(tok.get("children", [])))
    if t == "list":
        ordered = bool(tok["attrs"].get("ordered", False))
        items = [ListItem(children=_norm_list_item(it)) for it in tok.get("children", [])]
        return ListBlock(ordered=ordered, items=items)
    if t == "thematic_break":
        return ThematicBreak()
    if t == "table":
        return _norm_table(tok)
    # 兜底：尽量不丢内容
    if t == "block_html":
        return Paragraph(children=[Text(tok.get("raw", ""))])
    if "children" in tok:
        return Paragraph(children=_norm_inlines(tok["children"]))
    return None


def _norm_list_item(item: dict) -> list[Block]:
    out: list[Block] = []
    for child in item.get("children", []):
        if child["type"] == "block_text":  # 紧凑列表项内容是 block_text
            out.append(Paragraph(children=_norm_inlines(child.get("children", []))))
        else:
            b = _norm_block(child)  # 松散列表/嵌套列表
            if b is not None:
                out.append(b)
    return out


def _norm_table(tok: dict) -> Table:
    header: list[TableCell] = []
    rows: list[list[TableCell]] = []
    for section in tok.get("children", []):
        if section["type"] == "table_head":
            header = [_norm_cell(c) for c in section.get("children", [])]
        elif section["type"] == "table_body":
            for row in section.get("children", []):
                rows.append([_norm_cell(c) for c in row.get("children", [])])
    return Table(header=header, rows=rows)


def _norm_cell(cell: dict) -> TableCell:
    return TableCell(
        children=_norm_inlines(cell.get("children", [])),
        align=(cell.get("attrs") or {}).get("align"),
    )


# ----------------------------- 行内归一化 -----------------------------
def _norm_inlines(tokens: list[dict]) -> list[Inline]:
    out: list[Inline] = []
    for tok in tokens:
        n = _norm_inline(tok)
        if n is not None:
            out.append(n)
    return out


def _norm_inline(tok: dict) -> Inline | None:
    t = tok["type"]
    if t == "text":
        return Text(tok.get("raw", ""))
    if t == "strong":
        return Strong(children=_norm_inlines(tok.get("children", [])))
    if t == "emphasis":
        return Emphasis(children=_norm_inlines(tok.get("children", [])))
    if t == "strikethrough":
        return Strikethrough(children=_norm_inlines(tok.get("children", [])))
    if t == "codespan":
        return CodeSpan(tok.get("raw", ""))
    if t == "link":
        attrs = tok.get("attrs") or {}
        return Link(
            url=attrs.get("url", ""),
            title=attrs.get("title"),
            children=_norm_inlines(tok.get("children", [])),
        )
    if t == "image":
        attrs = tok.get("attrs") or {}
        return Image(
            url=attrs.get("url", ""),
            alt=inline_to_text(_norm_inlines(tok.get("children", []))),
            title=attrs.get("title"),
        )
    if t == "linebreak":
        return LineBreak()
    if t == "softbreak":
        return Text(" ")  # 软换行当空格
    if t == "inline_html":
        return Text(tok.get("raw", ""))
    if t == "blank_line":
        return None
    # 兜底
    if "children" in tok:
        return Text(inline_to_text(_norm_inlines(tok["children"])))
    if "raw" in tok:
        return Text(tok["raw"])
    return None
