"""图床抽象测试。ImgBB 路径用 monkeypatch 假 httpx，不联网、不需要真实 key。"""

import pytest

import multipub.web.imagehost as ih
from multipub.web.imagehost import ImgbbImageHost, LocalImageHost, make_image_host


def test_default_is_local(monkeypatch, tmp_path):
    monkeypatch.delenv("MULTIPUB_IMAGE_HOST", raising=False)
    host = make_image_host(tmp_path)
    assert isinstance(host, LocalImageHost)
    assert host.public is False


def test_local_saves_file_and_returns_absolute_url(tmp_path):
    host = LocalImageHost(tmp_path)
    url = host.save(b"\x89PNG-data", "a.png", "http://x:8000/")
    assert url.startswith("http://x:8000/static/uploads/") and url.endswith(".png")
    name = url.rsplit("/", 1)[-1]
    assert (tmp_path / name).read_bytes() == b"\x89PNG-data"


def test_imgbb_calls_httpx_and_parses_url(monkeypatch):
    captured = {}

    class FakeResp:
        def json(self):
            return {"success": True, "data": {"url": "https://i.ibb.co/abc/x.png"}}

    def fake_post(url, data=None, timeout=None):
        captured.update(url=url, key=data["key"], has_image=bool(data["image"]))
        return FakeResp()

    monkeypatch.setattr(ih.httpx, "post", fake_post)
    out = ImgbbImageHost("KEY123").save(b"\x89PNG", "a.png", "http://ignored/")
    assert out == "https://i.ibb.co/abc/x.png"
    assert captured["url"] == ImgbbImageHost.UPLOAD
    assert captured["key"] == "KEY123" and captured["has_image"]


def test_imgbb_raises_on_failure(monkeypatch):
    class FakeResp:
        def json(self):
            return {"success": False, "error": {"message": "bad key"}}

    monkeypatch.setattr(ih.httpx, "post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError):
        ImgbbImageHost("BAD").save(b"x", "a.png", "http://x/")


def test_factory_imgbb_requires_key(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTIPUB_IMAGE_HOST", "imgbb")
    monkeypatch.delenv("IMGBB_KEY", raising=False)
    with pytest.raises(RuntimeError):
        make_image_host(tmp_path)


def test_factory_imgbb_builds_with_key(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTIPUB_IMAGE_HOST", "imgbb")
    monkeypatch.setenv("IMGBB_KEY", "K")
    assert isinstance(make_image_host(tmp_path), ImgbbImageHost)
