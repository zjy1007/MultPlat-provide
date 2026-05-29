"""知乎适配器测试。

通过 import 触发注册，再走 parse + get_platform / pipeline.adapt 验证渲染产物。
知乎产物是规范 Markdown（body_format == "markdown"）。
"""

import multipub.platforms.zhihu  # noqa: F401  导入即注册
from multipub.core.parser import parse
from multipub.core.pipeline import adapt
from multipub.core.registry import available_platforms, get_platform


def render(md: str):
    return get_platform("zhihu").render(parse(md))


def test_registered():
    assert "zhihu" in available_platforms()
    p = get_platform("zhihu")
    assert p.name == "zhihu"
    assert p.display_name == "知乎"
    assert p.constraints.supports_html is True
    assert p.constraints.supports_markdown is True
    assert p.constraints.allows_external_links is True
    assert p.constraints.emoji_style == "none"


def test_body_format_markdown():
    """① body_format == 'markdown'。"""
    rc = render("# H\n\n正文\n")
    assert rc.body_format == "markdown"


def test_inline_markdown_roundtrip():
    """② 加粗/斜体/行内代码/删除线回写成正确的 Markdown 标记。"""
    md = "正文**加粗**、*斜体*、`code`、~~删除~~。\n"
    rc = render(md)
    b = rc.body
    assert "**加粗**" in b
    assert "*斜体*" in b
    assert "`code`" in b
    assert "~~删除~~" in b


def test_link_url_preserved():
    """③ 链接 URL 被保留为 [文字](https://…)。"""
    md = "看 [知乎](https://www.zhihu.com/q/1) 吧\n"
    rc = render(md)
    assert "[知乎](https://www.zhihu.com/q/1)" in rc.body


def test_heading_levels():
    md = "# 一级\n\n## 二级\n\n### 三级\n"
    rc = render(md)
    b = rc.body
    assert "# 一级" in b
    assert "## 二级" in b
    assert "### 三级" in b


def test_codeblock_fenced_with_lang():
    """④ 代码块带语言围栏，内容与换行保留。"""
    md = "```python\nif a < b:\n    print('x')\n```\n"
    rc = render(md)
    b = rc.body
    assert "```python" in b
    assert "if a < b:\n    print('x')" in b
    # 围栏成对闭合
    assert b.count("```") == 2


def test_table_valid_markdown():
    """⑤ 表格回写成合法 Markdown 表格（含对齐行）。"""
    md = "| A | B | C |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n"
    rc = render(md)
    b = rc.body
    assert "| A | B | C |" in b
    # 对齐行依据 align
    assert ":---" in b  # left
    assert ":--:" in b  # center
    assert "---:" in b  # right
    assert "| 1 | 2 | 3 |" in b


def test_blockquote():
    md = "> 引用一行\n> 引用二行\n"
    rc = render(md)
    for line in rc.body.split("\n"):
        if line.strip():
            assert line.startswith(">")


def test_nested_list():
    md = "- 外层\n  - 内层\n- 外层二\n"
    rc = render(md)
    b = rc.body
    assert "- 外层" in b
    # 内层有缩进
    assert "  - 内层" in b


def test_ordered_list():
    md = "1. 甲\n2. 乙\n"
    rc = render(md)
    b = rc.body
    assert "1. 甲" in b
    assert "2. 乙" in b


def test_thematic_break():
    rc = render("上\n\n---\n\n下\n")
    assert "---" in rc.body


def test_local_image_warns_and_collected():
    """⑥ 本地图触发 warning 且进 images；远程图正常。"""
    md = "![本地](./a.png)\n\n![远程](https://e.com/a.jpg)\n"
    rc = render(md)
    assert len(rc.images) == 2
    locals_ = [i for i in rc.images if i.is_local]
    remotes = [i for i in rc.images if not i.is_local]
    assert len(locals_) == 1 and locals_[0].note
    assert len(remotes) == 1 and remotes[0].note == ""
    assert any("本地" in w for w in rc.warnings)
    # Markdown 正文仍照常写图片
    assert "![本地](./a.png)" in rc.body
    assert "![远程](https://e.com/a.jpg)" in rc.body


def test_remote_image_no_warning():
    rc = render("![远程](https://e.com/a.jpg)\n")
    assert len(rc.images) == 1
    assert rc.images[0].is_local is False
    assert rc.warnings == []


def test_title_from_doc():
    rc = render("---\ntitle: 我的标题\n---\n\n正文\n")
    assert rc.title == "我的标题"


def test_empty_document():
    """⑦ 空文档不崩。"""
    rc = render("")
    assert rc.body == ""
    assert rc.title == ""
    assert rc.images == []


def test_plain_text_no_format():
    rc = render("就是一段纯文本，没有任何格式。\n")
    assert rc.title == ""
    assert "纯文本" in rc.body
    assert rc.body_format == "markdown"


def test_via_adapt_pipeline():
    rc = adapt("# H\n\n正文\n", ["zhihu"])["zhihu"]
    assert rc.platform == "zhihu"
    assert rc.body_format == "markdown"
    assert "# H" in rc.body


def test_blocks_separated_by_blank_line():
    rc = render("# 标题\n\n第一段\n\n第二段\n")
    assert "\n\n" in rc.body
    parts = rc.body.split("\n\n")
    assert len(parts) >= 3
