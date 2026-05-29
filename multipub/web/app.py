"""FastAPI 入口：把核心 pipeline 暴露为 HTTP，并托管零构建单页前端。

接口：
- GET  /api/platforms  → 平台列表 + 约束（前端建 Tab/字数提示用）
- POST /api/adapt       → 确定性适配（实时预览走这条，无副作用）
- POST /api/publish     → 适配 + 模拟发布（一键发布走这条）

核心层完全复用：本文件不含任何适配逻辑，只做 HTTP 编排。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import multipub.platforms  # noqa: F401  导入以触发平台注册
from multipub.core.pipeline import adapt, run
from multipub.core.platform import RenderedContent
from multipub.core.registry import available_platforms, get_platform
from multipub.core.style import LLMStyleAdapter, StyleAdapter, StyleError, style_for_platform
from multipub.publishers.base import MockPublisher

app = FastAPI(title="MultiPub")
STATIC = Path(__file__).parent / "static"

# 可注入的风格适配器工厂（测试时可替换，避免打真实 API）
style_adapter_factory = lambda: LLMStyleAdapter()  # noqa: E731


class ContentRequest(BaseModel):
    markdown: str = ""
    platforms: list[str] | None = None


class StyleRequest(BaseModel):
    markdown: str = ""
    platform: str


def _known(platforms: list[str] | None) -> list[str]:
    """过滤出已注册的平台，未知的忽略（保持接口稳健）。"""
    valid = set(available_platforms())
    if not platforms:
        return available_platforms()
    return [p for p in platforms if p in valid]


def _rc_dict(rc: RenderedContent) -> dict:
    return {
        "platform": rc.platform,
        "title": rc.title,
        "body": rc.body,
        "body_format": rc.body_format,
        "images": [asdict(i) for i in rc.images],
        "warnings": rc.warnings,
    }


@app.get("/api/platforms")
def api_platforms() -> dict:
    out = []
    for name in available_platforms():
        p = get_platform(name)
        c = p.constraints
        out.append(
            {
                "name": name,
                "display_name": p.display_name,
                "constraints": {
                    "supports_html": c.supports_html,
                    "supports_markdown": c.supports_markdown,
                    "max_title_len": c.max_title_len,
                    "max_body_len": c.max_body_len,
                    "emoji_style": c.emoji_style,
                },
            }
        )
    return {"platforms": out}


@app.post("/api/adapt")
def api_adapt(req: ContentRequest) -> dict:
    results = adapt(req.markdown, _known(req.platforms))
    return {"results": {name: _rc_dict(rc) for name, rc in results.items()}}


@app.post("/api/publish")
def api_publish(req: ContentRequest) -> dict:
    results = run(req.markdown, _known(req.platforms), MockPublisher())
    return {
        "results": {
            name: {
                "rendered": _rc_dict(pr.rendered),
                "published": asdict(pr.published) if pr.published else None,
            }
            for name, pr in results.items()
        }
    }


@app.post("/api/style")
def api_style(req: StyleRequest) -> dict:
    """LLM 风格适配（按钮触发，不进实时预览链路）。

    无 key / 未知平台 / 调用失败都优雅返回，不抛 500。
    """
    if req.platform not in available_platforms():
        return {"available": False, "note": f"未知平台：{req.platform}"}

    adapter: StyleAdapter = style_adapter_factory()
    if not adapter.available():
        return {
            "available": False,
            "note": "未配置 ANTHROPIC_API_KEY，无法使用 LLM 风格适配。设置后重启服务即可启用。",
        }
    try:
        result = style_for_platform(req.markdown, req.platform, adapter)
    except StyleError as e:
        return {"available": True, "error": str(e)}

    rendered = adapt(result.styled, [req.platform]).get(req.platform)
    return {
        "available": True,
        "original": result.original,
        "styled": result.styled,
        "changed": result.changed,
        "note": result.note,
        "rendered": _rc_dict(rendered) if rendered else None,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
