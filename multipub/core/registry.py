"""平台注册表 —— 扩展性的核心。

内置平台用 @register 装饰器注册；第三方可通过 entry_points 注册（见 README/开发文档）。
"""

from __future__ import annotations

from .platform import Platform

_REGISTRY: dict[str, type[Platform]] = {}


def register(name: str):
    def deco(cls: type[Platform]) -> type[Platform]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def get_platform(name: str) -> Platform:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的平台: {name!r}（已注册: {sorted(_REGISTRY)}）")
    return _REGISTRY[name]()


def available_platforms() -> list[str]:
    return sorted(_REGISTRY)
