"""小红书适配器测试：确定性的「结构 → 纯文本」转换。"""

import multipub.platforms.xiaohongshu  # noqa: F401  触发 @register 注册
from multipub.core.parser import parse
from multipub.core.pipeline import adapt
from multipub.core.registry import get_platform

SAMPLE = """---
title: 测试标题
tags: [效率, Python]
---

# 一级标题

正文带**加粗**、`code`、[去看看](https://x.com)、~~删除~~。

> 引用块内容

```python
print(1)
```

- 项一
- 项二 **粗**

| A | B |
|---|---|
| 1 | 2 |

![本地图](./a.png)

![远程图](https://e.com/a.jpg)
"""


def _render(md):
    doc = parse(md)
    return get_platform("xiaohongshu").render(doc)


def test_registered_and_basics():
    rc = _render(SAMPLE)
    assert rc.platform == "xiaohongshu"
    assert rc.body_format == "text"
    assert rc.title == "测试标题"
    assert get_platform("xiaohongshu").display_name == "小红书"


def test_constraints():
    p = get_platform("xiaohongshu")
    assert p.constraints.supports_html is False
    assert p.constraints.supports_markdown is False
    assert p.constraints.max_title_len == 20
    assert p.constraints.max_body_len == 1000
    assert p.constraints.emoji_style == "rich"


def test_plain_text_no_markdown_symbols():
    rc = _render(SAMPLE)
    # 行内格式符号不应残留
    assert "**" not in rc.body
    assert "~~" not in rc.body
    assert "`" not in rc.body
    # 标题不带 markdown 的 # 前缀；正文里唯一允许的 # 是 #tag# 形式
    assert "# 一级标题" not in rc.body
    assert "> 引用" not in rc.body
    # 文字本身保留
    assert "一级标题" in rc.body
    assert "加粗" in rc.body
    assert "删除" in rc.body
    assert "print(1)" in rc.body  # 代码块原样


def test_link_rendered_as_text_paren_url():
    rc = _render(SAMPLE)
    assert "去看看(https://x.com)" in rc.body
    # 不残留 markdown 链接语法
    assert "[去看看]" not in rc.body


def test_list_and_quote():
    rc = _render(SAMPLE)
    assert "· 项一" in rc.body
    assert "· 项二 粗" in rc.body
    assert "「引用块内容」" in rc.body


def test_table_flattened():
    rc = _render(SAMPLE)
    assert "A | B" in rc.body
    assert "1 | 2" in rc.body


def test_tags_appended_as_topics():
    rc = _render(SAMPLE)
    assert rc.body.rstrip().endswith("#效率# #Python#")


def test_ordered_list():
    md = "1. 甲\n2. 乙\n"
    rc = _render(md)
    assert "1. 甲" in rc.body
    assert "2. 乙" in rc.body


def test_title_too_long_warns_no_truncate():
    long_title = "标" * 25
    md = f"---\ntitle: {long_title}\n---\n\n正文\n"
    rc = _render(md)
    assert rc.title == long_title  # 未截断
    assert len(rc.title) == 25
    assert any("标题" in w and "未自动截断" in w for w in rc.warnings)


def test_body_too_long_warns_no_truncate():
    body_src = "啊" * 1500
    md = f"---\ntitle: t\ntags: [x]\n---\n\n{body_src}\n\n![p](https://e.com/a.jpg)\n"
    rc = _render(md)
    # 原文长度仍在（未截断）
    assert body_src in rc.body
    assert len(rc.body) > 1000
    assert any("正文" in w and "未自动截断" in w for w in rc.warnings)


def test_no_image_warns():
    md = "---\ntitle: t\n---\n\n只有文字没有图片\n"
    rc = _render(md)
    assert rc.images == []
    assert any("图片优先" in w for w in rc.warnings)


def test_local_image_warns_and_collected():
    md = "---\ntitle: t\n---\n\n![本地](./a.png)\n\n![远程](https://e.com/a.jpg)\n"
    rc = _render(md)
    urls = [i.url for i in rc.images]
    assert urls == ["./a.png", "https://e.com/a.jpg"]
    local = next(i for i in rc.images if i.url == "./a.png")
    assert local.is_local
    assert any("本地" in w for w in rc.warnings)
    # 有图时不应再报"图片优先"建议
    assert not any("图片优先" in w for w in rc.warnings)


def test_empty_document_does_not_crash():
    rc = _render("")
    assert rc.body_format == "text"
    assert rc.title == ""
    # 空文档：无图片 → 配图建议
    assert any("图片优先" in w for w in rc.warnings)


def test_no_title_no_tags():
    md = "# 标题\n\n正文段落\n\n![p](https://e.com/a.jpg)\n"
    rc = _render(md)
    assert rc.title == ""
    assert "#" not in rc.body  # 无 tags 时不应出现 #


def test_via_adapt_pipeline():
    rc = adapt(SAMPLE, ["xiaohongshu"])["xiaohongshu"]
    assert rc.body_format == "text"
    assert "去看看(https://x.com)" in rc.body
