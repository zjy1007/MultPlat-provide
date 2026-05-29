---
title: 我如何用一周搭出多平台发布工具
tags: [效率工具, Python, 创作者]
cover: https://example.com/cover.png
summary: 一份内容，自动适配公众号/知乎/B站/小红书。
---

## 背景

很多创作者需要在公众号、知乎、B站、小红书等平台**同步发布**，但每个平台
格式、风格、字数限制都不一样，手动适配很费时间。

> 一次写作，多平台适配。这是这个工具的全部目标。

## 核心做法

1. 只写一份 Markdown；
2. 解析成统一的中间表示（IR）；
3. 各平台适配器把 IR 渲染成各自格式。

```python
def adapt(markdown_text, platforms):
    doc = parse(markdown_text)
    return {p: get_platform(p).render(doc) for p in platforms}
```

更多细节见我的 [GitHub 仓库](https://github.com/example/multipub)。

![架构示意图](https://example.com/arch.png)
