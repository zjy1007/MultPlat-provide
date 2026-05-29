"""发布器契约。

v1 仅 MockPublisher（不调用任何平台 API）。真实发布（如公众号草稿 API）
未来只需新增一个 Publisher 实现，核心与适配器零改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.platform import RenderedContent


@dataclass
class PublishResult:
    platform: str
    success: bool
    mode: str  # mock | live
    message: str
    detail: dict = field(default_factory=dict)


class Publisher(ABC):
    @abstractmethod
    def publish(self, content: RenderedContent, creds: dict | None = None) -> PublishResult:
        raise NotImplementedError


class MockPublisher(Publisher):
    """模拟发布：返回可信回执，不触达任何外部服务。"""

    def publish(self, content: RenderedContent, creds: dict | None = None) -> PublishResult:
        pending = [img for img in content.images if img.note]
        return PublishResult(
            platform=content.platform,
            success=True,
            mode="mock",
            message=f"[模拟发布] 「{content.title or '(无标题)'}」已生成 {content.platform} 成品",
            detail={
                "body_format": content.body_format,
                "body_len": len(content.body),
                "images_total": len(content.images),
                "images_need_manual": len(pending),
                "warnings": content.warnings,
            },
        )
