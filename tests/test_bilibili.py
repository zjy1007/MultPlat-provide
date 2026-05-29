"""B站专栏适配器测试。

通过 import 触发注册，再走 parse + get_platform / pipeline.adapt 验证渲染产物。
"""

import multipub.platforms.bilibili  # noqa: F401  导入即注册
from multipub.core.parser import parse
from multipub.core.pipeline import adapt
from multipub.core.registry import available_platforms, get_platform


def render(md: str):
    return get_platform("bilibili").render(parse(md))


def test_registered():
    assert "bilibili" in available_platforms()
    p = get_platform("bilibili")
    assert p.name == "bilibili"
    assert p.display_name == "B站专栏"
    assert p.constraints.supports_html is True
    assert p.constraints.supports_markdown is False
    assert p.constraints.allows_external_links is True
    assert p.constraints.emoji_style == "moderate"


def test_body_format_html():
    """① body_format 为 html。"""
    rc = render("# 标题\n\n正文\n")
    assert rc.body_format == "html"


def test_inline_html_tags():
    """② 加粗/链接/行内代码/删除线渲染成对应 HTML 标签。"""
    md = "正文**加粗**、`code`、[链接](https://x.com)、~~删除~~。\n"
    rc = render(md)
    b = rc.body
    assert "<strong style=" in b and "加粗" in b
    assert "<code style=" in b and "code" in b
    assert '<a href="https://x.com" style=' in b
    assert "链接</a>" in b  # 外链保留 href + 文字
    assert "<del style=" in b and "删除" in b
    assert "<em style=" not in b  # 没用到斜体不该出现


def test_emphasis_and_linebreak():
    md = "*斜体*文字\n"
    rc = render(md)
    assert "<em style=" in rc.body and "斜体" in rc.body


def test_codeblock_escaped_and_preserved():
    """③ 代码块内容被转义且保留换行。"""
    md = "```python\nif a < b & c > d:\n    print('x')\n```\n"
    rc = render(md)
    assert "<pre style=" in rc.body
    assert "a &lt; b &amp; c &gt; d" in rc.body
    assert "&lt;" in rc.body and "<if" not in rc.body
    assert "\n    print(" in rc.body  # 换行保留


def test_dangerous_text_escaped():
    """④ 含 <script> 等危险字符被转义（安全测试）。"""
    md = '正文 <script>alert("x")</script> 结束\n'
    rc = render(md)
    assert "<script>" not in rc.body
    assert "&lt;script&gt;" in rc.body


def test_dangerous_link_href_escaped():
    """链接文字里的引号被转义；属性里不应出现可逃逸的裸引号。"""
    md = '[a"onmouseover="alert(1)](https://x.com)\n'
    rc = render(md)
    # 链接文字含裸引号，渲染进 <a> 内容须被转义，不得逃逸破坏 HTML
    assert 'onmouseover="alert' not in rc.body
    assert "&quot;" in rc.body


def test_table_rendered():
    """⑤ 表格渲染成 <table>。"""
    md = "| A | B |\n|:--|--:|\n| 1 | 2 |\n"
    rc = render(md)
    b = rc.body
    assert "<table style=" in b and "<th style=" in b and "<td style=" in b
    assert "text-align:left;" in b
    assert "text-align:right;" in b


def test_local_image_warns_and_collected():
    """⑥ 本地图触发 warning 且进 images，输出【图N】占位而非 <img>。"""
    md = "![本地](./a.png)\n"
    rc = render(md)
    assert len(rc.images) == 1
    assert rc.images[0].is_local is True
    assert rc.images[0].note
    assert "【图1】" in rc.body
    assert "<img" not in rc.body
    # 站内上传提醒
    assert any("上传到站内" in w for w in rc.warnings)
    # 本地图 note 也进 warnings
    assert any("本地" in w for w in rc.warnings)


def test_remote_image_is_placeholder_not_img():
    """⑥ B站不接受外链图：远程图也渲染成【图N】占位（而非会裂的 <img>）。"""
    md = "![远程](https://e.com/a.jpg)\n"
    rc = render(md)
    assert len(rc.images) == 1
    assert rc.images[0].is_local is False
    assert rc.images[0].note == ""
    assert "【图1】" in rc.body and "远程" in rc.body
    assert "<img" not in rc.body  # 关键：不再输出会在 B站 裂掉的外链 <img>
    assert any("上传到站内" in w for w in rc.warnings)


def test_warnings_deduped():
    """多张本地图，站内上传提醒只出现一次（warnings 去重）。"""
    md = "![a](./a.png)\n\n![b](./b.png)\n"
    rc = render(md)
    upload = [w for w in rc.warnings if "上传到站内" in w]
    assert len(upload) == 1


def test_blockquote_list_hr():
    md = (
        "> 引用\n\n"
        "- 项一\n- 项二\n\n"
        "1. 甲\n2. 乙\n\n"
        "---\n"
    )
    rc = render(md)
    b = rc.body
    assert "<blockquote style=" in b
    assert "<ul style=" in b and "<li style=" in b
    assert "<ol style=" in b
    assert "<hr style=" in b


def test_heading_levels_clamped():
    md = "#### 四级标题\n"
    rc = render(md)
    assert "<h3 style=" in rc.body  # level>3 收敛到 h3


def test_title_from_doc():
    md = "---\ntitle: 我的标题\n---\n\n正文\n"
    rc = render(md)
    assert rc.title == "我的标题"


def test_empty_document():
    """⑦ 空文档不崩。"""
    rc = render("")
    assert rc.body == ""
    assert rc.title == ""
    assert rc.images == []
    assert rc.warnings == []


def test_via_adapt_pipeline():
    md = "# H\n\n正文\n"
    rc = adapt(md, ["bilibili"])["bilibili"]
    assert rc.platform == "bilibili"
    assert "<h1 style=" in rc.body
