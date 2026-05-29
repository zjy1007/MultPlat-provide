"""FastAPI 入口：把核心 pipeline 暴露为 HTTP，并托管零构建单页前端。

接口：
- GET  /api/platforms  → 平台列表 + 约束（前端建 Tab/字数提示用）
- POST /api/adapt       → 确定性适配（实时预览走这条，无副作用）
- POST /api/publish     → 适配 + 模拟发布（一键发布走这条）
- POST /api/style       → LLM 风格适配（按钮触发，不进实时预览链路）
- POST /api/upload      → 粘贴/上传图片 → 返回可访问 URL（让预览能显示图片）

核心层完全复用：本文件不含任何适配逻辑，只做 HTTP 编排。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import multipub.platforms  # noqa: F401  导入以触发平台注册
from multipub.core.pipeline import adapt, run
from multipub.core.platform import RenderedContent
from multipub.core.registry import available_platforms, get_platform
from multipub.core.style import (
    PROVIDERS,
    StyleError,
    make_style_adapter,
    style_for_platform,
)
from multipub.publishers.base import MockPublisher

from .imagehost import make_image_host

app = FastAPI(title="MultiPub")
STATIC = Path(__file__).parent / "static"
UPLOADS = STATIC / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)

# 允许上传的图片扩展名（svg 仍可上传，但适配器会按平台告警）
_IMG_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}

# 可注入的风格适配器工厂（测试时可替换，避免打真实 API）。
# 入参 (provider, api_key, model) 来自页面「LLM 设置」，key 仅在内存中流转、不落盘。
style_adapter_factory = make_style_adapter


class ContentRequest(BaseModel):
    markdown: str = ""
    platforms: list[str] | None = None


class StyleRequest(BaseModel):
    markdown: str = ""
    platform: str
    provider: str | None = None   # deepseek | qwen | doubao（页面选择）
    api_key: str | None = None    # 页面填写，仅内存流转、不落盘
    model: str | None = None      # 可选，覆盖该 provider 默认模型（豆包常需填接入点 id）


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
                    "embeds_remote_images": c.embeds_remote_images,
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


@app.get("/api/providers")
def api_providers() -> dict:
    """供前端「LLM 设置」下拉用：可选模型厂商 + 默认模型 + 提示。"""
    return {
        "providers": [
            {"name": k, "label": v.label, "default_model": v.default_model, "note": v.note}
            for k, v in PROVIDERS.items()
        ]
    }


@app.post("/api/style")
def api_style(req: StyleRequest) -> dict:
    """LLM 风格适配（按钮触发，不进实时预览链路）。

    provider/api_key/model 来自页面「LLM 设置」，key 仅内存流转、不落盘、不记日志。
    无 key / 未知平台 / 调用失败都优雅返回，不抛 500。
    """
    if req.platform not in available_platforms():
        return {"available": False, "note": f"未知平台：{req.platform}"}

    adapter = style_adapter_factory(req.provider, req.api_key, req.model)
    if not adapter.available():
        return {
            "available": False,
            "note": "未填写 API key —— 请在页面顶部「LLM 设置」选择模型厂商并填入对应 key。",
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


@app.post("/api/upload")
async def api_upload(request: Request, file: UploadFile) -> dict:
    """保存粘贴/上传的图片，返回可访问 URL。

    图床可插拔（见 imagehost.py）：默认本地（返回绝对 http URL，仅本机预览可见）；
    配置 MULTIPUB_IMAGE_HOST=imgbb + IMGBB_KEY 后转存公网，复制到平台才能带图。
    返回绝对 URL 很关键：make_image_ref 把单斜杠开头判为本地图、会出占位。
    """
    ext = (file.filename or "image.png").rsplit(".", 1)[-1].lower()
    if ext not in _IMG_EXTS:
        return {"error": f"不支持的图片格式：.{ext}"}
    data = await file.read()
    try:
        host = make_image_host(UPLOADS)
        url = host.save(data, file.filename or "image.png", str(request.base_url))
    except Exception as e:
        return {"error": f"上传失败：{e}"}
    return {"url": url, "public": host.public, "filename": file.filename}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
