"""平台适配器契约。

新增平台只需实现 Platform.render 并用 @register 注册，核心代码零改动（开闭原则）。

设计取舍（相对早期文档的细化）：Platform 只负责 render（纯函数，无副作用）；
发布是独立关注点，由 Publisher 承担、pipeline 编排。这样每个平台不必知道"如何发布"。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .document import Document


@dataclass
class PlatformConstraints:
    """平台的硬约束，供适配器在 render 时校验并产出 warnings。"""

    supports_html: bool = False
    supports_markdown: bool = False
    max_title_len: int | None = None
    max_body_len: int | None = None
    max_images: int | None = None
    allows_external_links: bool = True
    emoji_style: str = "none"  # none | moderate | rich
    # 平台是否会自动嵌入/转存远程图（粘贴成品时图能直接显示）。
    # 公众号（外链转存）/知乎（markdown 导入）=True；B站/小红书=False，需手动上传，
    # 这类平台的图在正文里渲染成可见的「【图N】」占位，并配合图片清单引导手动上传。
    embeds_remote_images: bool = True


@dataclass
class ImageRef:
    """适配产物中的一张图片及其可发布性判定（基于粘贴验证结论）。"""

    url: str
    alt: str = ""
    is_local: bool = False
    note: str = ""  # 非空表示需人工处理，如"本地图需手动上传"


@dataclass
class RenderedContent:
    """单平台适配成品。Web 预览与（模拟）发布都消费它。"""

    platform: str
    title: str
    body: str
    body_format: str  # html | markdown | text
    images: list[ImageRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Platform(ABC):
    name: str = ""
    display_name: str = ""
    constraints: PlatformConstraints = PlatformConstraints()

    @abstractmethod
    def render(self, doc: Document, opts: dict | None = None) -> RenderedContent:
        """格式适配：IR → 平台成品。必须是无副作用的纯函数（便于实时预览 + 快照测试）。"""
        raise NotImplementedError


# ---------------- 共享：图片可发布性判定（编码自粘贴验证结论） ----------------
_REMOTE = re.compile(r"^(https?:)?//", re.IGNORECASE)


def make_image_ref(url: str, alt: str = "") -> ImageRef:
    """按验证结论标注图片：本地图✗、公网直链 png/jpg✓、svg✗（公众号不支持）。"""
    url = url or ""
    is_local = not bool(_REMOTE.match(url))
    note = ""
    if is_local:
        note = "本地图，发布前需手动上传到图床/平台"
    elif url.lower().split("?")[0].endswith(".svg"):
        # 平台中立：此辅助为所有平台共享，不假设调用者是哪个平台
        note = "SVG 内容图部分平台不支持（如公众号），建议转为 PNG/JPG"
    return ImageRef(url=url, alt=alt, is_local=is_local, note=note)
