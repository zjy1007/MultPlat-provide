"""B站专栏平台适配器。

B站专栏编辑器是 HTML 富文本，粘贴时也主要认内联 style（与公众号同思路），因此本
适配器把一套主题样式直接内联进每个标签（不引第三方 CSS 内联库，确定性更好、利于
快照测试）。配色用 B站粉 #fb7299 作主色，整体干净。

行内渲染统一走 core.document.render_inline 通用遍历器：适配器只声明「每种节点产出
什么」，递归骨架不重写。

图片注意：B站专栏不接受外链图，发布前需把图重新上传到站内。本适配器对本地图/svg
（make_image_ref 给出 note 的）输出占位说明并告警；对远程图正常输出 <img>，但仍统一
追加一条「需上传到站内」的提醒。
"""

from __future__ import annotations

import html

from ..core import document as D
from ..core.platform import (
    ImageRef,
    Platform,
    PlatformConstraints,
    RenderedContent,
    make_image_ref,
)
from ..core.registry import register

# ---------------------------------------------------------------------------
# 主题：每种元素 → 内联 style 字符串（B站粉 #fb7299 主色，干净排版）
# ---------------------------------------------------------------------------
_STYLE = {
    "h1": "font-size:24px;font-weight:bold;color:#18191c;margin:24px 0 16px;",
    "h2": (
        "font-size:20px;font-weight:bold;color:#18191c;margin:22px 0 14px;"
        "border-left:4px solid #fb7299;padding-left:10px;"
    ),
    "h3": "font-size:17px;font-weight:bold;color:#18191c;margin:20px 0 12px;",
    "p": "font-size:16px;line-height:1.8;margin:16px 0;color:#222;",
    "strong": "color:#fb7299;font-weight:bold;",
    "em": "font-style:italic;",
    "del": "text-decoration:line-through;color:#999;",
    "codespan": (
        "background:#fff0f5;padding:2px 5px;border-radius:3px;color:#fb7299;"
        "font-family:Menlo,Consolas,monospace;"
    ),
    "pre": (
        "background:#1f2227;color:#d7dae0;padding:16px;border-radius:6px;"
        "overflow-x:auto;font-size:13px;line-height:1.6;"
    ),
    "pre_code": "font-family:Menlo,Consolas,monospace;",
    "blockquote": (
        "margin:16px 0;padding:12px 16px;background:#fafbfc;"
        "border-left:4px solid #fb7299;color:#61666d;font-size:15px;"
    ),
    "ul": "font-size:16px;line-height:1.8;margin:16px 0;padding-left:24px;color:#222;",
    "ol": "font-size:16px;line-height:1.8;margin:16px 0;padding-left:24px;color:#222;",
    "li": "margin:4px 0;",
    "a": "color:#fb7299;text-decoration:none;",
    "img": "max-width:100%;border-radius:6px;",
    "img_placeholder": (
        "font-size:14px;color:#999;margin:8px 0;padding:10px 14px;"
        "background:#fafafa;border:1px dashed #fb7299;border-radius:4px;"
    ),
    "hr": "border:none;border-top:1px solid #e3e5e7;margin:24px 0;",
    "table": "border-collapse:collapse;width:100%;margin:16px 0;font-size:14px;",
    "th": "border:1px solid #e3e5e7;padding:8px 12px;background:#fafbfc;font-weight:bold;",
    "td": "border:1px solid #e3e5e7;padding:8px 12px;",
}

# B站专栏不接受外链图，无论远程/本地都提醒一次。
_IMG_UPLOAD_WARNING = "B站专栏图片需上传到站内，外链图可能无法显示"


def _esc(text: str) -> str:
    """转义正文/属性中的 < > & " ，防注入/破版。"""
    return html.escape(text, quote=True)


@register("bilibili")
class BilibiliPlatform(Platform):
    display_name = "B站专栏"
    constraints = PlatformConstraints(
        supports_html=True,
        supports_markdown=False,
        allows_external_links=True,
        emoji_style="moderate",
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
        def render_inlines(nodes: list[D.Inline]) -> str:
            # 复用通用遍历器：只声明每种节点的产出，递归骨架不重写。
            return D.render_inline(nodes, visit)

        def visit(n: D.Inline, render_children) -> str:
            if isinstance(n, D.Text):
                return _esc(n.content)
            if isinstance(n, D.Strong):
                return f'<strong style="{_STYLE["strong"]}">{render_children()}</strong>'
            if isinstance(n, D.Emphasis):
                return f'<em style="{_STYLE["em"]}">{render_children()}</em>'
            if isinstance(n, D.Strikethrough):
                return f'<del style="{_STYLE["del"]}">{render_children()}</del>'
            if isinstance(n, D.CodeSpan):
                return f'<code style="{_STYLE["codespan"]}">{_esc(n.content)}</code>'
            if isinstance(n, D.Link):
                # B站允许外链，保留 href。
                inner = render_children() or _esc(n.url)
                return f'<a href="{_esc(n.url)}" style="{_STYLE["a"]}">{inner}</a>'
            if isinstance(n, D.Image):
                return render_image(n)
            if isinstance(n, D.LineBreak):
                return "<br/>"
            return ""

        def render_image(n: D.Image) -> str:
            ref = make_image_ref(n.url, n.alt)
            images.append(ref)
            # 不论远程还是本地，都提醒图片需上传到站内。
            warn(_IMG_UPLOAD_WARNING)
            if ref.note:
                # 本地图/svg：输出占位说明，把 note 也加进 warnings。
                warn(ref.note)
                label = _esc(ref.alt or n.url or "图片")
                return (
                    f'<p style="{_STYLE["img_placeholder"]}">'
                    f"[图片待处理] {label} —— {_esc(ref.note)}</p>"
                )
            return (
                f'<img src="{_esc(ref.url)}" alt="{_esc(ref.alt)}" '
                f'style="{_STYLE["img"]}" />'
            )

        # ----------------------------- 块级 -----------------------------
        def render_blocks(blocks: list[D.Block]) -> str:
            return "".join(render_block(b) for b in blocks)

        def render_block(b: D.Block) -> str:
            if isinstance(b, D.Heading):
                level = b.level if b.level in (1, 2, 3) else 3
                tag = f"h{level}"
                return f'<{tag} style="{_STYLE[tag]}">{render_inlines(b.children)}</{tag}>'
            if isinstance(b, D.Paragraph):
                return f'<p style="{_STYLE["p"]}">{render_inlines(b.children)}</p>'
            if isinstance(b, D.CodeBlock):
                # 代码内容 HTML 转义、保留换行。
                code = _esc(b.code)
                return (
                    f'<pre style="{_STYLE["pre"]}">'
                    f'<code style="{_STYLE["pre_code"]}">{code}</code></pre>'
                )
            if isinstance(b, D.BlockQuote):
                return (
                    f'<blockquote style="{_STYLE["blockquote"]}">'
                    f"{render_blocks(b.children)}</blockquote>"
                )
            if isinstance(b, D.ListBlock):
                tag = "ol" if b.ordered else "ul"
                items = "".join(
                    f'<li style="{_STYLE["li"]}">{render_blocks(it.children)}</li>'
                    for it in b.items
                )
                return f'<{tag} style="{_STYLE[tag]}">{items}</{tag}>'
            if isinstance(b, D.Table):
                return render_table(b)
            if isinstance(b, D.ThematicBreak):
                return f'<hr style="{_STYLE["hr"]}" />'
            return ""

        def render_table(b: D.Table) -> str:
            def cell(c: D.TableCell, tag: str) -> str:
                style = _STYLE[tag]
                if c.align:
                    style = style + f"text-align:{c.align};"
                return f'<{tag} style="{style}">{render_inlines(c.children)}</{tag}>'

            head = ""
            if b.header:
                head_cells = "".join(cell(c, "th") for c in b.header)
                head = f"<thead><tr>{head_cells}</tr></thead>"
            body_rows = "".join(
                "<tr>" + "".join(cell(c, "td") for c in row) + "</tr>" for row in b.rows
            )
            body = f"<tbody>{body_rows}</tbody>" if body_rows else ""
            return f'<table style="{_STYLE["table"]}">{head}{body}</table>'

        body = render_blocks(doc.blocks)

        return RenderedContent(
            platform=self.name,
            title=doc.title,
            body=body,
            body_format="html",
            images=images,
            warnings=warnings,
        )
