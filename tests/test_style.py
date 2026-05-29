"""风格适配模块测试。LLM 调用全部用注入的假 complete，不打真实 API。"""

import pytest

from multipub.core.style import (
    DEFAULT_MODEL,
    LLMStyleAdapter,
    NoopStyleAdapter,
    PlatformProfile,
    StyleError,
    _strip_fence,
    get_profile,
    load_profiles,
    style_for_platform,
)


def test_profiles_loaded():
    profiles = load_profiles()
    assert {"wechat", "xiaohongshu", "zhihu", "bilibili"} <= set(profiles)
    xhs = profiles["xiaohongshu"]
    assert xhs.emoji == "rich"
    assert get_profile("zhihu").emoji == "none"
    assert get_profile("不存在") is None


def test_noop_passthrough():
    a = NoopStyleAdapter()
    assert a.available()
    assert a.adapt("# hi\n\ntext", get_profile("zhihu")) == "# hi\n\ntext"


def test_llm_availability():
    assert not LLMStyleAdapter(api_key=None).available()  # 无 key 不可用
    assert LLMStyleAdapter(api_key="sk-test").available()
    assert LLMStyleAdapter(complete=lambda s, u: u).available()  # 注入即可用


def test_llm_adapt_with_injected_complete():
    captured = {}

    def fake(system, user):
        captured["system"] = system
        captured["user"] = user
        return "改写后的小红书文案✨"

    out = LLMStyleAdapter(complete=fake).adapt("原始内容", get_profile("xiaohongshu"))
    assert out == "改写后的小红书文案✨"
    # 系统提示应带上画像信息
    assert "小红书" in captured["system"]
    assert "emoji" in captured["system"].lower() or "Emoji" in captured["system"]
    assert "原始内容" in captured["user"]


def test_llm_strips_code_fence():
    fake = lambda s, u: "```markdown\n# 标题\n\n正文\n```"
    out = LLMStyleAdapter(complete=fake).adapt("x", get_profile("wechat"))
    assert out == "# 标题\n\n正文"


def test_strip_fence_helper():
    assert _strip_fence("```\nabc\n```") == "abc"
    assert _strip_fence("```markdown\nabc\n```") == "abc"
    assert _strip_fence("no fence") == "no fence"


def test_empty_markdown_skips_llm():
    def boom(system, user):
        raise AssertionError("空内容不应调用 LLM")

    assert LLMStyleAdapter(complete=boom).adapt("   ", get_profile("zhihu")) == "   "


def test_no_key_raises_clear_error():
    with pytest.raises(StyleError) as e:
        LLMStyleAdapter(api_key=None).adapt("内容", get_profile("zhihu"))
    assert "ANTHROPIC_API_KEY" in str(e.value)


def test_style_for_platform_noop_unchanged():
    r = style_for_platform("# hi", "xiaohongshu")  # 默认 Noop
    assert not r.changed and r.styled == "# hi"


def test_style_for_platform_with_llm():
    adapter = LLMStyleAdapter(complete=lambda s, u: "活泼版✨")
    r = style_for_platform("原文", "xiaohongshu", adapter)
    assert r.changed and r.styled == "活泼版✨"
    assert r.original == "原文" and r.platform == "xiaohongshu"


def test_style_for_platform_unknown_platform():
    r = style_for_platform("x", "telegram")
    assert not r.changed and "无风格画像" in r.note


def test_default_model_is_a_claude_model():
    assert "claude" in DEFAULT_MODEL
