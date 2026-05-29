"""知乎平台适配器。

知乎编辑器对 Markdown 支持良好：允许外链、支持公式与代码块。因此本适配器做的本质是
**「IR → 规范 Markdown」的回写**——把归一化后的 Document IR 重新序列化成一份干净、
可直接粘贴的合法 Markdown。

设计与 wechat/xiaohongshu 一致的取舍：
- 确定性纯函数，无副作用、无 LLM 改写、不自动截断（利于快照测试）；
- 行内渲染走核心 `D.render_inline(nodes, visit)` 通用遍历器，不自己重写递归骨架；
- 图片统一过 `make_image_ref` 收进 images 清单；本地图/SVG 的 note 进 warnings
  （知乎需自行上传本地图），但 Markdown 正文仍照常写 `![alt](url)`，保留可读性；
- 话题 tags 是独立元数据，不污染正文结构——仅在末尾附一行 `话题：xxx` 提示。
"""

from __future__ import annotations

from ..core import document as D
from ..core.platform import (
    ImageRef,
    Platform,
    PlatformConstraints,
    RenderedContent,
    make_image_ref,
)
from ..core.registry import register

# 列表嵌套缩进单位（两个空格，符合 Markdown 子列表惯例）
_INDENT = "  "

# Markdown 对齐行：依据 TableCell.align 给出 :---/:--:/---: 形态
_ALIGN_RULE = {
    "left": ":---",
    "center": ":--:",
    "right": "---:",
    None: "---",
}


@register("zhihu")
class ZhihuPlatform(Platform):
    display_name = "知乎"
    constraints = PlatformConstraints(
        supports_html=True,
        supports_markdown=True,
        allows_external_links=True,
        emoji_style="none",
    )

    def render(self, doc: D.Document, opts: dict | None = None) -> RenderedContent:
        images: list[ImageRef] = []
        warnings: list[str] = []
        _seen_warnings: set[str] = set()

        def warn(msg: str) -> None:
            if msg and msg not in _seen_warnings:
                _seen_warnings.add(msg)
                warnings.append(msg)

        # ----------------------------- 行内 -----------------------------
        # 用核心通用遍历器：只声明「每种节点产出什么」，递归骨架由 render_inline 提供。
        def visit(n: D.Inline, render_children) -> str:
            if isinstance(n, D.Text):
                return n.content
            if isinstance(n, D.Strong):
                return f"**{render_children()}**"
            if isinstance(n, D.Emphasis):
                return f"*{render_children()}*"
            if isinstance(n, D.Strikethrough):
                return f"~~{render_children()}~~"
            if isinstance(n, D.CodeSpan):
                return f"`{n.content}`"
            if isinstance(n, D.Link):
                text = render_children() or (n.url or "")
                return f"[{text}]({n.url or ''})"
            if isinstance(n, D.Image):
                # 知乎允许外链，正文照常写 Markdown 图片；同时收进清单并校验可发布性。
                ref = make_image_ref(n.url, n.alt)
                images.append(ref)
                if ref.note:
                    warn(ref.note)
                return f"![{n.alt}]({n.url or ''})"
            if isinstance(n, D.LineBreak):
                # Markdown 软换行：行尾两个空格 + 换行（保持在同一段落内）
                return "  \n"
            return ""

        def render_inlines(nodes: list[D.Inline]) -> str:
            return D.render_inline(nodes, visit)

        # ----------------------------- 块级 -----------------------------
        # 每个块渲染成一个「字符串块」，最终用空行连接（块间空行分隔）。
        def render_blocks(blocks: list[D.Block]) -> list[str]:
            out: list[str] = []
            for b in blocks:
                rendered = render_block(b)
                if rendered:
                    out.append(rendered)
            return out

        def render_block(b: D.Block) -> str:
            if isinstance(b, D.Heading):
                level = b.level if 1 <= b.level <= 6 else 6
                return f"{'#' * level} {render_inlines(b.children)}"
            if isinstance(b, D.Paragraph):
                return render_inlines(b.children)
            if isinstance(b, D.CodeBlock):
                lang = b.lang or ""
                # 保留 lang 与代码原文换行；用围栏包裹。
                return f"```{lang}\n{b.code}\n```"
            if isinstance(b, D.BlockQuote):
                inner = "\n\n".join(render_blocks(b.children))
                # 引用内每一行（含块间空行）都加 `> ` 前缀。
                return "\n".join(
                    f">{' ' + line if line else ''}" for line in inner.split("\n")
                )
            if isinstance(b, D.ListBlock):
                return render_list(b, depth=0)
            if isinstance(b, D.Table):
                return render_table(b)
            if isinstance(b, D.ThematicBreak):
                return "---"
            return ""

        def render_list(block: D.ListBlock, depth: int) -> str:
            indent = _INDENT * depth
            lines: list[str] = []
            for idx, item in enumerate(block.items, start=1):
                marker = f"{idx}. " if block.ordered else "- "
                sub = render_item(item, depth, marker)
                lines.append(sub)
            return "\n".join(lines)

        def render_item(item: D.ListItem, depth: int, marker: str) -> str:
            """渲染单个列表项：首块带 marker，后续块（嵌套列表/多段）按层级缩进对齐。"""
            indent = _INDENT * depth
            # marker 之后内容的悬挂缩进，使续行与首字符对齐。
            hang = indent + " " * len(marker)
            pieces: list[str] = []
            for i, b in enumerate(item.children):
                if isinstance(b, D.ListBlock):
                    # 嵌套列表：深一层缩进，整体作为独立块接在后面。
                    pieces.append(render_list(b, depth + 1))
                    continue
                text = render_block(b)
                if not text:
                    continue
                lines = text.split("\n")
                if not pieces and i == 0:
                    # 首块首行带 marker，其余行悬挂缩进。
                    rendered = (indent + marker + lines[0])
                    rendered = "\n".join(
                        [rendered] + [hang + ln for ln in lines[1:]]
                    )
                else:
                    rendered = "\n".join(hang + ln for ln in lines)
                pieces.append(rendered)
            if not pieces:
                return indent + marker.rstrip()
            return "\n".join(pieces)

        def render_table(b: D.Table) -> str:
            # 知乎支持标准 Markdown 表格；无表头时用空表头占位以保证表格合法。
            header = b.header or []
            ncols = len(header)
            if ncols == 0 and b.rows:
                ncols = max(len(r) for r in b.rows)

            def row_line(cells: list[D.TableCell]) -> str:
                texts = [render_inlines(c.children) for c in cells]
                # 补齐列数，避免列数不一致导致表格失效。
                texts += [""] * (ncols - len(texts))
                return "| " + " | ".join(texts) + " |"

            lines: list[str] = []
            if header:
                lines.append(row_line(header))
                rules = [_ALIGN_RULE.get(c.align, "---") for c in header]
            else:
                lines.append("| " + " | ".join([""] * ncols) + " |")
                rules = ["---"] * ncols
            lines.append("| " + " | ".join(rules) + " |")
            for row in b.rows:
                lines.append(row_line(row))
            return "\n".join(lines)

        # ------------------------------ 组装 ------------------------------
        parts = render_blocks(doc.blocks)
        body = "\n\n".join(parts)

        # 话题：独立元数据，不进正文结构，仅末尾附提示行。
        tags = [str(t).strip() for t in (doc.tags or []) if str(t).strip()]
        if tags:
            tag_line = "话题：" + " ".join(f"#{t}#" for t in tags)
            body = f"{body}\n\n{tag_line}" if body else tag_line

        return RenderedContent(
            platform=self.name,
            title=doc.title or "",
            body=body,
            body_format="markdown",
            images=images,
            warnings=warnings,
        )
