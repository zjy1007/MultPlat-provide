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


def test_style_unavailable_without_key(monkeypatch):
    # 工厂返回一个无 key 的适配器 → 优雅降级，不报错
    monkeypatch.setattr(webapp, "style_adapter_factory", lambda: LLMStyleAdapter(api_key=None))
    r = client.post("/api/style", json={"markdown": "内容", "platform": "xiaohongshu"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "ANTHROPIC_API_KEY" in body["note"]


def test_style_success_with_injected_adapter(monkeypatch):
    monkeypatch.setattr(
        webapp, "style_adapter_factory",
        lambda: LLMStyleAdapter(complete=lambda s, u: "活泼版✨ #测试#"),
    )
    r = client.post("/api/style", json={"markdown": "原文", "platform": "xiaohongshu"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["changed"] is True
    assert "活泼版" in body["styled"]
    assert body["rendered"]["body_format"] == "text"  # 风格化后仍走确定性 render


def test_style_unknown_platform():
    r = client.post("/api/style", json={"markdown": "x", "platform": "telegram"})
    assert r.json()["available"] is False
