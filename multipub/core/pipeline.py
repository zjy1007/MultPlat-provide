"""编排层：parse → render →（模拟）publish。

两个入口分工明确：
- adapt(): 只做确定性适配，不发布。**Web 实时预览走这条**（无副作用、可快照）。
- run():   适配 + 发布（默认 MockPublisher）。一键发布走这条。
LLM 风格适配是 adapt 之前的可选前置步骤，永不进实时预览链路（见开发文档）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..publishers.base import MockPublisher, Publisher, PublishResult
from .parser import parse
from .platform import RenderedContent
from .registry import get_platform


@dataclass
class PlatformResult:
    rendered: RenderedContent
    published: PublishResult | None = None


def adapt(markdown_text: str, platforms: list[str], opts: dict | None = None) -> dict[str, RenderedContent]:
    doc = parse(markdown_text)
    return {name: get_platform(name).render(doc, opts) for name in platforms}


def run(
    markdown_text: str,
    platforms: list[str],
    publisher: Publisher | None = None,
    opts: dict | None = None,
) -> dict[str, PlatformResult]:
    doc = parse(markdown_text)
    publisher = publisher or MockPublisher()
    results: dict[str, PlatformResult] = {}
    for name in platforms:
        rendered = get_platform(name).render(doc, opts)
        results[name] = PlatformResult(rendered=rendered, published=publisher.publish(rendered))
    return results
