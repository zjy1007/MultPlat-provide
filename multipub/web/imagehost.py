"""可插拔图床。

- 默认 `local`：存到 static/uploads，返回本机 URL —— 仅本机预览可见。
- `imgbb`：上传 ImgBB（免费），返回公网 URL —— 复制到公众号等平台才够得到、能带图。

通过环境变量切换：MULTIPUB_IMAGE_HOST=local|imgbb，imgbb 需 IMGBB_KEY。
密钥只从环境变量读取，绝不硬编码、不入库。
"""

from __future__ import annotations

import base64
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx


class ImageHost(ABC):
    public: bool = False  # True 表示返回的是公网 URL（可被平台转存）

    @abstractmethod
    def save(self, data: bytes, filename: str, base_url: str) -> str:
        """保存图片，返回可访问的 URL。"""


class LocalImageHost(ImageHost):
    """存本地 static/uploads，返回基于请求 base_url 的绝对 URL（仅本机预览可见）。"""

    public = False

    def __init__(self, uploads_dir: Path):
        self.dir = uploads_dir

    def save(self, data: bytes, filename: str, base_url: str) -> str:
        ext = (filename or "image.png").rsplit(".", 1)[-1].lower()
        name = f"{uuid.uuid4().hex}.{ext}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / name).write_bytes(data)
        return f"{base_url.rstrip('/')}/static/uploads/{name}"


class ImgbbImageHost(ImageHost):
    """上传 ImgBB（免费图床），返回公网 URL（形如 https://i.ibb.co/xxx/x.png）。"""

    public = True
    UPLOAD = "https://api.imgbb.com/1/upload"

    def __init__(self, key: str):
        self.key = key

    def save(self, data: bytes, filename: str, base_url: str) -> str:
        b64 = base64.b64encode(data).decode()
        resp = httpx.post(self.UPLOAD, data={"key": self.key, "image": b64}, timeout=30)
        j = resp.json()
        if j.get("success"):
            return j["data"]["url"]
        raise RuntimeError(f"ImgBB 上传失败：{j.get('error', j)}")


def make_image_host(uploads_dir: Path) -> ImageHost:
    """按环境变量选择图床；默认本地，配置不全时回退本地不影响主流程。"""
    kind = os.environ.get("MULTIPUB_IMAGE_HOST", "local").lower()
    if kind == "imgbb":
        key = os.environ.get("IMGBB_KEY")
        if not key:
            raise RuntimeError("MULTIPUB_IMAGE_HOST=imgbb 但未设置 IMGBB_KEY")
        return ImgbbImageHost(key)
    return LocalImageHost(uploads_dir)
