"""Phase 0 契约验证：解析 → IR → 注册/渲染 → pipeline → 模拟发布 全链路。

真实平台适配器是 Phase 1，这里用一个一次性 DebugPlatform 证明契约可用。
"""

from multipub.core import document as D
from multipub.core.parser import parse
from multipub.core.pipeline import adapt, run
from multipub.core.platform import (
    Platform,
    PlatformConstraints,
    RenderedContent,
    make_image_ref,
)
from multipub.core.registry import available_platforms, get_platform, register
from multipub.publishers.base import MockPublisher

SAMPLE = """---
title: 测试文章
tags: [效率, Python]
cover: ./cover.png
---

# 一级标题

正文带**加粗**、`code`、[链接](https://x.com)、~~删除~~。

> 引用块

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

![矢量图](https://e.com/a.svg)
"""


def test_front_matter():
    doc = parse(SAMPLE)
    assert doc.title == "测试文章"
    assert doc.tags == ["效率", "Python"]
    assert doc.cover == "./cover.png"


def test_block_structure():
    doc = parse(SAMPLE)
    kinds = {type(b).__name__ for b in doc.blocks}
    assert {"Heading", "Paragraph", "CodeBlock", "BlockQuote", "ListBlock", "Table"} <= kinds
    assert isinstance(doc.blocks[0], D.Heading) and doc.blocks[0].level == 1


def test_inline_structure_preserved():
    """行内结构 v1 就在：加粗/行内代码/链接/删除线都应是独立节点，不是字符串。"""
    doc = parse(SAMPLE)
    para = next(
        b for b in doc.blocks
        if isinstance(b, D.Paragraph) and any(isinstance(c, D.Strong) for c in b.children)
    )
    kinds = {type(c).__name__ for c in para.children}
    assert {"Strong", "CodeSpan", "Link", "Strikethrough"} <= kinds
    link = next(c for c in para.children if isinstance(c, D.Link))
    assert link.url == "https://x.com"


def test_code_block():
    doc = parse(SAMPLE)
    cb = next(b for b in doc.blocks if isinstance(b, D.CodeBlock))
    assert cb.lang == "python"
    assert cb.code == "print(1)"  # 尾部换行已去除


def test_table():
    doc = parse(SAMPLE)
    tb = next(b for b in doc.blocks if isinstance(b, D.Table))
    assert D.inline_to_text(tb.header[0].children) == "A"
    assert D.inline_to_text(tb.rows[0][1].children) == "2"


def test_iter_images():
    doc = parse(SAMPLE)
    urls = [i.url for i in D.iter_images(doc)]
    assert urls == ["./a.png", "https://e.com/a.jpg", "https://e.com/a.svg"]


def test_image_classification():
    assert make_image_ref("./a.png").is_local
    assert not make_image_ref("https://e.com/a.jpg").is_local
    assert "本地" in make_image_ref("./a.png").note
    assert make_image_ref("https://e.com/a.jpg").note == ""
    assert "SVG" in make_image_ref("https://e.com/a.svg").note


def test_pipeline_end_to_end():
    @register("debug")
    class DebugPlatform(Platform):
        display_name = "调试"
        constraints = PlatformConstraints(supports_markdown=True)

        def render(self, doc, opts=None):
            imgs = [make_image_ref(i.url, i.alt) for i in D.iter_images(doc)]
            return RenderedContent(
                platform=self.name,
                title=doc.title,
                body=doc.raw_markdown,
                body_format="markdown",
                images=imgs,
                warnings=[i.note for i in imgs if i.note],
            )

    assert "debug" in available_platforms()
    assert isinstance(get_platform("debug"), DebugPlatform)

    # adapt：纯适配（预览路径）
    rc = adapt(SAMPLE, ["debug"])["debug"]
    assert rc.title == "测试文章"
    assert any("本地" in w for w in rc.warnings)
    assert any("SVG" in w for w in rc.warnings)

    # run：适配 + 模拟发布
    res = run(SAMPLE, ["debug"], MockPublisher())["debug"]
    assert res.published.success and res.published.mode == "mock"
    assert res.published.detail["images_total"] == 3
    assert res.published.detail["images_need_manual"] == 2  # 本地图 + svg
