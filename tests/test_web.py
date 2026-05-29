"""Web 层冒烟测试：三个接口 + 静态首页。"""

from fastapi.testclient import TestClient

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
