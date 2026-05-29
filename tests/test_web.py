"""Web 层冒烟测试：接口 + 静态首页 + 风格适配。"""

from fastapi.testclient import TestClient

import multipub.web.app as webapp
from multipub.core.style import LLMStyleAdapter
from multipub.web.app import app

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "MultiPub" in r.text


def test_platforms_list():
    r = client.get("/api/platforms")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["platforms"]}
    assert {"wechat", "xiaohongshu"} <= names


def test_adapt_formats():
    r = client.post("/api/adapt", json={
        "markdown": "## 标题\n\n正文**粗**和[链接](https://x.com)。",
        "platforms": ["wechat", "xiaohongshu"],
    })
    assert r.status_code == 200
    res = r.json()["results"]
    assert res["wechat"]["body_format"] == "html"
    assert "<h2" in res["wechat"]["body"]
    assert res["xiaohongshu"]["body_format"] == "text"
    assert "链接(https://x.com)" in res["xiaohongshu"]["body"]  # 链接转括号注释


def test_publish_mock_receipt():
    r = client.post("/api/publish", json={"markdown": "# hi\n\ntext", "platforms": ["wechat"]})
    assert r.status_code == 200
    pub = r.json()["results"]["wechat"]["published"]
    assert pub["success"] and pub["mode"] == "mock"


def test_unknown_platform_ignored():
    r = client.post("/api/adapt", json={"markdown": "x", "platforms": ["wechat", "nope"]})
    assert r.status_code == 200
    assert set(r.json()["results"].keys()) == {"wechat"}


def test_providers_listed():
    r = client.get("/api/providers")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["providers"]}
    assert {"deepseek", "qwen", "doubao"} <= names


def test_style_unavailable_without_key(monkeypatch):
    # 工厂收 (provider, api_key, model)；无 key → 优雅降级，不报错
    monkeypatch.setattr(webapp, "style_adapter_factory",
                        lambda *a, **k: LLMStyleAdapter(api_key=None))
    r = client.post("/api/style", json={"markdown": "内容", "platform": "xiaohongshu"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "API key" in body["note"]


def test_style_success_with_injected_adapter(monkeypatch):
    monkeypatch.setattr(
        webapp, "style_adapter_factory",
        lambda *a, **k: LLMStyleAdapter(complete=lambda s, u: "活泼版✨ #测试#"),
    )
    r = client.post("/api/style", json={"markdown": "原文", "platform": "xiaohongshu",
                                         "provider": "deepseek", "api_key": "sk-x"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["changed"] is True
    assert "活泼版" in body["styled"]
    assert body["rendered"]["body_format"] == "text"  # 风格化后仍走确定性 render


def test_style_unknown_platform():
    r = client.post("/api/style", json={"markdown": "x", "platform": "telegram"})
    assert r.json()["available"] is False


# 1x1 透明 PNG
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f6e0000000049454e44ae426082"
)


def test_upload_returns_absolute_url_and_serves_file():
    r = client.post("/api/upload", files={"file": ("a.png", _PNG, "image/png")})
    assert r.status_code == 200
    url = r.json()["url"]
    # 必须是绝对 http URL（否则会被 make_image_ref 判为本地图而出占位）
    assert url.startswith("http") and "/static/uploads/" in url and url.endswith(".png")
    # 上传后能被静态服务取到
    path = url.split("/static/", 1)[1]
    assert client.get("/static/" + path).status_code == 200


def test_upload_rejects_non_image_ext():
    r = client.post("/api/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert "error" in r.json()
