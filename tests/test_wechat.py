"""公众号适配器测试。

通过 import 触发注册，再走 parse + get_platform / pipeline.adapt 验证渲染产物。
"""

import multipub.platforms.wechat  # noqa: F401  导入即注册
from multipub.core.parser import parse
from multipub.core.pipeline import adapt
from multipub.core.registry import available_platforms, get_platform


def render(md: str):
    return get_platform("wechat").render(parse(md))


def test_registered():
    assert "wechat" in available_platforms()
    p = get_platform("wechat")
    assert p.name == "wechat"
    assert p.display_name == "公众号"
    assert p.constraints.supports_html is True
    assert p.constraints.supports_markdown is False
    assert p.constraints.allows_external_links is False
    assert p.constraints.emoji_style == "moderate"


def test_inline_styled_html():
    """① 标题/加粗/行内代码/链接/删除线都渲染成带内联 style 的 HTML。"""
    md = "# 标题\n\n正文**加粗**、`code`、[链接](https://x.com)、~~删除~~。\n"
    rc = render(md)
    assert rc.body_format == "html"
    b = rc.body
    assert '<h1 style="' in b
    assert "<strong style=" in b and "加粗" in b
    assert "<code style=" in b and "code" in b
    assert '<a href="https://x.com" style=' in b
    assert "<del style=" in b and "删除" in b
    # 链接告警
    assert any("外链" in w for w in rc.warnings)


def test_title_from_doc():
    md = "---\ntitle: 我的标题\n---\n\n正文\n"
    rc = render(md)
    assert rc.title == "我的标题"


def test_codeblock_escaped_and_preserved():
    """② 代码块内容被正确转义且保留换行。"""
    md = "```python\nif a < b & c > d:\n    print('x')\n```\n"
    rc = render(md)
    assert "<pre style=" in rc.body
    # 危险字符被转义
    assert "a &lt; b &amp; c &gt; d" in rc.body
    assert "&lt;" in rc.body and "<if" not in rc.body
    # 换行保留
    assert "\n    print(" in rc.body


def test_dangerous_text_escaped():
    """③ 含 <script> 的正文被转义（安全测试）。"""
    md = '正文 <script>alert("x")</script> 结束\n'
    rc = render(md)
    assert "<script>" not in rc.body
    assert "&lt;script&gt;" in rc.body
    assert "&quot;" in rc.body or "&#x27;" in rc.body or "alert" in rc.body


def test_local_and_svg_images_warn_and_collected():
    """④ 本地图与 svg 触发 warning 且进 images。"""
    md = "![本地](./a.png)\n\n![矢量](https://e.com/a.svg)\n"
    rc = render(md)
    assert len(rc.images) == 2
    # 都是需人工处理（note 非空），且无 <img 输出（占位）
    notes = [i.note for i in rc.images]
    assert all(n for n in notes)
    assert any("本地" in w for w in rc.warnings)
    assert any("SVG" in w for w in rc.warnings)
    assert "<img" not in rc.body
    # 本地图/svg 渲染成【图N】占位（与右侧清单对应）
    assert "【图1】" in rc.body and "【图2】" in rc.body


def test_remote_image_output():
    """⑤ 远程图正常输出 img。"""
    md = "![远程](https://e.com/a.jpg)\n"
    rc = render(md)
    assert len(rc.images) == 1
    assert rc.images[0].is_local is False
    assert rc.images[0].note == ""
    assert '<img src="https://e.com/a.jpg"' in rc.body
    assert 'alt="远程"' in rc.body


def test_empty_document():
    """⑥ 空文档不崩。"""
    rc = render("")
    assert rc.body == ""
    assert rc.title == ""
    assert rc.images == []


def test_no_title_plain_text():
    rc = render("就是一段纯文本，没有任何格式。\n")
    assert rc.title == ""
    assert "<p style=" in rc.body
    assert "纯文本" in rc.body


def test_blockquote_list_table_hr():
    md = (
        "> 引用\n\n"
        "- 项一\n- 项二\n\n"
        "1. 甲\n2. 乙\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "---\n"
    )
    rc = render(md)
    b = rc.body
    assert "<blockquote style=" in b
    assert "<ul style=" in b and "<li style=" in b
    assert "<ol style=" in b
    assert "<table style=" in b and "<th style=" in b and "<td style=" in b
    assert "<hr style=" in b


def test_via_adapt_pipeline():
    md = "# H\n\n正文\n"
    rc = adapt(md, ["wechat"])["wechat"]
    assert rc.platform == "wechat"
    assert "<h1 style=" in rc.body


def test_table_alignment():
    md = "| A | B |\n|:--|--:|\n| 1 | 2 |\n"
    rc = render(md)
    assert "text-align:left;" in rc.body
    assert "text-align:right;" in rc.body
