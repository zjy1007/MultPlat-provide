"""公众号（微信公众号）平台适配器。

公众号编辑器在粘贴时会**剥掉 class、只认内联 style**，因此本适配器把一套主题
样式直接内联进每个标签（不引第三方 CSS 内联库，确定性更好、利于快照测试）。

样式主题基准来自 validation/wechat-paste-test.html（已过真人粘贴验证：内联样式的
标题/加粗/引用/深色代码块/行内代码/列表粘进公众号能完整保留）。
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
# 主题：每种元素 → 内联 style 字符串（与验证页同风格）
# ---------------------------------------------------------------------------
_STYLE = {
    "h1": "font-size:22px;font-weight:bold;color:#222;margin:24px 0 16px;",
    "h2": (
        "font-size:18px;font-weight:bold;color:#222;margin:22px 0 14px;"
        "border-left:4px solid #07c160;padding-left:10px;"
    ),
    "h3": "font-size:16px;font-weight:bold;color:#222;margin:20px 0 12px;",
    "p": "font-size:16px;line-height:1.75;margin:16px 0;color:#3f3f3f;",
    "strong": "color:#07c160;font-weight:bold;",
    "em": "font-style:italic;",
    "del": "text-decoration:line-through;color:#999;",
    "codespan": (
        "background:#f3f3f3;padding:2px 5px;border-radius:3px;color:#c7254e;"
        "font-family:Menlo,monospace;"
    ),
    "pre": (
        "background:#282c34;color:#abb2bf;padding:16px;border-radius:6px;"
        "overflow-x:auto;font-size:13px;line-height:1.6;"
    ),
    "pre_code": "font-family:Menlo,monospace;",
    "blockquote": (
        "margin:16px 0;padding:12px 16px;background:#f7f7f7;border-left:4px solid #ddd;"
        "color:#666;font-size:15px;"
    ),
    "ul": "font-size:16px;line-height:1.8;margin:16px 0;padding-left:24px;color:#3f3f3f;",
    "ol": "font-size:16px;line-height:1.8;margin:16px 0;padding-left:24px;color:#3f3f3f;",
    "li": "margin:4px 0;",
    "a": "color:#576b95;text-decoration:none;",
    "img": "max-width:100%;border-radius:6px;",
    "img_placeholder": (
        "font-size:14px;color:#999;margin:8px 0;padding:10px 14px;"
        "background:#fafafa;border:1px dashed #ccc;border-radius:4px;"
    ),
    "hr": "border:none;border-top:1px solid #e5e5e5;margin:24px 0;",
    "table": "border-collapse:collapse;width:100%;margin:16px 0;font-size:14px;",
    "th": "border:1px solid #ddd;padding:8px 12px;background:#f7f7f7;font-weight:bold;",
    "td": "border:1px solid #ddd;padding:8px 12px;",
}

_LINK_WARNING = "公众号正式发文中正文外链对读者不可点（可后续做链接转脚注）"


def _esc(text: str) -> str:
    """转义正文/属性中的 < > & " ，防注入/破版。"""
    return html.escape(text, quote=True)


@register("wechat")
class WeChatPlatform(Platform):
    display_name = "公众号"
    constraints = PlatformConstraints(
        supports_html=True,
        supports_markdown=False,
        allows_external_links=False,
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
            return "".join(render_inline(n) for n in nodes)

        def render_inline(n: D.Inline) -> str:
            if isinstance(n, D.Text):
                return _esc(n.content)
            if isinstance(n, D.Strong):
                return f'<strong style="{_STYLE["strong"]}">{render_inlines(n.children)}</strong>'
            if isinstance(n, D.Emphasis):
                return f'<em style="{_STYLE["em"]}">{render_inlines(n.children)}</em>'
            if isinstance(n, D.Strikethrough):
                return f'<del style="{_STYLE["del"]}">{render_inlines(n.children)}</del>'
            if isinstance(n, D.CodeSpan):
                return f'<code style="{_STYLE["codespan"]}">{_esc(n.content)}</code>'
            if isinstance(n, D.Link):
                warn(_LINK_WARNING)
                inner = render_inlines(n.children) or _esc(n.url)
                return f'<a href="{_esc(n.url)}" style="{_STYLE["a"]}">{inner}</a>'
            if isinstance(n, D.Image):
                return render_image(n)
            if isinstance(n, D.LineBreak):
                return "<br/>"
            return ""

        def render_image(n: D.Image) -> str:
            ref = make_image_ref(n.url, n.alt)
            images.append(ref)
            if ref.note:
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
                # 代码内容 HTML 转义、保留换行
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
