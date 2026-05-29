"""风格适配（可选模块）：按平台调性用 LLM 改写文案。

与「格式适配」严格分离：
- 格式适配（platform.render）是确定性的、无副作用的，走实时预览与快照测试。
- 风格适配（本模块）是**可选**的、由按钮触发的、非确定性的（LLM）改写。

定位：LLM 是**前置改写器**——输入源 Markdown + 平台画像，输出"平台化后的 Markdown"，
该产物可被用户继续编辑，再走确定性 render。因此 LLM **永不进实时预览/防抖链路**，
下游全程保持可快照、可复现。

无 DEEPSEEK_API_KEY 或未安装 httpx 时优雅降级（available()=False + 清晰错误），
绝不让主流程崩溃。

LLM 后端用 DeepSeek（deepseek-chat，OpenAI 兼容 API，httpx 直调）。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"

# 风格改写求"贴原意、稳定" → 低温度（用户选定 0.4）。
TEMPERATURE = 0.4


@dataclass
class ProviderSpec:
    label: str
    base_url: str       # OpenAI 兼容的 chat/completions 端点
    default_model: str
    note: str = ""      # 给前端的提示（如豆包需填接入点 id）


# 三家都是 OpenAI 兼容 API：同一套 chat/completions 协议，只是 base_url / 默认模型不同。
PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        "DeepSeek", "https://api.deepseek.com/chat/completions", "deepseek-chat"
    ),
    "qwen": ProviderSpec(
        "千问 Qwen",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "qwen-plus",
    ),
    "doubao": ProviderSpec(
        "豆包 Doubao",
        "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "doubao-pro-32k",
        note="豆包的「模型」通常填你在火山方舟创建的接入点 id（ep-xxxx）",
    ),
}
DEFAULT_PROVIDER = "deepseek"


class StyleError(RuntimeError):
    """风格适配不可用或调用失败（如缺 key / 缺 SDK / API 报错）。"""


@dataclass
class PlatformProfile:
    """平台风格画像。以 YAML 描述，便于非程序员调风格。"""

    name: str
    display_name: str = ""
    tone: str = ""
    audience: str = ""
    emoji: str = "none"  # none | moderate | rich
    length: str = ""
    dos: list[str] = field(default_factory=list)
    donts: list[str] = field(default_factory=list)


@dataclass
class StyleResult:
    platform: str
    original: str
    styled: str
    changed: bool
    note: str = ""


def load_profiles() -> dict[str, PlatformProfile]:
    """读取 profiles/*.yaml → {platform_name: PlatformProfile}。"""
    out: dict[str, PlatformProfile] = {}
    if not _PROFILE_DIR.is_dir():
        return out
    for path in sorted(_PROFILE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = path.stem
        out[name] = PlatformProfile(
            name=name,
            display_name=data.get("display_name", ""),
            tone=data.get("tone", ""),
            audience=data.get("audience", ""),
            emoji=data.get("emoji", "none"),
            length=data.get("length", ""),
            dos=list(data.get("dos", []) or []),
            donts=list(data.get("donts", []) or []),
        )
    return out


def get_profile(platform: str) -> PlatformProfile | None:
    return load_profiles().get(platform)


# --------------------------------------------------------------------------
# 适配器
# --------------------------------------------------------------------------
class StyleAdapter(ABC):
    @abstractmethod
    def available(self) -> bool:
        """当前是否可用（如 LLM 需要 key/SDK）。"""

    @abstractmethod
    def adapt(self, markdown: str, profile: PlatformProfile) -> str:
        """源 Markdown → 平台化 Markdown。"""


class NoopStyleAdapter(StyleAdapter):
    """直通：原样返回。默认行为 = 关闭风格适配，回退纯格式适配。"""

    def available(self) -> bool:
        return True

    def adapt(self, markdown: str, profile: PlatformProfile) -> str:
        return markdown


class LLMStyleAdapter(StyleAdapter):
    """按平台画像改写文案，调用 OpenAI 兼容 API（DeepSeek / 千问 / 豆包）。

    `complete` 可注入（签名 (system:str, user:str)->str），用于测试时绕过真实 API。
    """

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com/chat/completions",
        api_key: str | None = None,
        model: str = "deepseek-chat",
        complete=None,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._complete = complete

    def available(self) -> bool:
        return self._complete is not None or bool(self._api_key)

    def adapt(self, markdown: str, profile: PlatformProfile) -> str:
        if not markdown.strip():
            return markdown
        system = self._system_prompt(profile)
        user = self._user_prompt(markdown)
        complete = self._complete or self._call_llm
        return _strip_fence(complete(system, user)).strip()

    # ---- 提示词 ----
    @staticmethod
    def _system_prompt(profile: PlatformProfile) -> str:
        dos = "\n".join(f"- {d}" for d in profile.dos) or "-（无）"
        donts = "\n".join(f"- {d}" for d in profile.donts) or "-（无）"
        emoji_rule = {
            "none": "不要使用 emoji。",
            "moderate": "可适度使用 emoji 点缀，不过量。",
            "rich": "积极使用 emoji 增强亲和力与节奏感，但不堆砌。",
        }.get(profile.emoji, "按内容自然决定 emoji。")
        return (
            f"你是「{profile.display_name or profile.name}」平台的资深内容编辑。"
            f"把用户给的 Markdown 文章改写成符合本平台调性的版本。\n\n"
            f"## 平台画像\n"
            f"- 目标读者：{profile.audience or '通用'}\n"
            f"- 语气风格：{profile.tone or '自然'}\n"
            f"- 篇幅偏好：{profile.length or '依内容而定'}\n"
            f"- Emoji：{emoji_rule}\n"
            f"- 应该：\n{dos}\n"
            f"- 避免：\n{donts}\n\n"
            f"## 硬规则\n"
            f"1. 只改写语气、措辞、节奏、emoji；**不要编造原文没有的事实/数据/链接**。\n"
            f"2. 保留 Markdown 结构与语法（标题、列表、代码块、链接、图片照常）。\n"
            f"3. 代码块内容原样保留，不要改写代码。\n"
            f"4. **只输出改写后的 Markdown 正文本身**，不要任何前后说明、不要包代码围栏。"
        )

    @staticmethod
    def _user_prompt(markdown: str) -> str:
        return f"请改写下面这篇 Markdown：\n\n{markdown}"

    def _call_llm(self, system: str, user: str) -> str:
        """通用 OpenAI 兼容调用（DeepSeek/千问/豆包 同协议，只是 base_url/model 不同）。"""
        if not self._api_key:
            raise StyleError("未配置 LLM API key —— 请在页面顶部「LLM 设置」里选模型并填写 key")
        try:
            import httpx
        except ImportError as e:  # pragma: no cover - 依赖缺失路径
            raise StyleError("未安装 httpx，请 pip install 'multipub[llm]'") from e
        try:
            resp = httpx.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": TEMPERATURE,
                    "stream": False,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # 网络/鉴权/限流等
            raise StyleError(f"LLM 调用失败：{e}") from e
        return data["choices"][0]["message"]["content"]


def _strip_fence(text: str) -> str:
    """模型偶尔会把输出包进 ```markdown ... ```，去掉外层围栏。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def make_style_adapter(
    provider: str | None,
    api_key: str | None,
    model: str | None = None,
    complete=None,
) -> LLMStyleAdapter:
    """按 provider 名构造适配器；key/model 来自页面输入（不落盘）。

    complete 可注入用于测试，绕过真实网络调用。
    """
    spec = PROVIDERS.get(provider or DEFAULT_PROVIDER, PROVIDERS[DEFAULT_PROVIDER])
    return LLMStyleAdapter(
        base_url=spec.base_url,
        api_key=api_key,
        model=model or spec.default_model,
        complete=complete,
    )


def style_for_platform(
    markdown: str,
    platform: str,
    adapter: StyleAdapter | None = None,
) -> StyleResult:
    """对指定平台做风格适配。无画像时直通；adapter 默认 Noop（关闭）。"""
    adapter = adapter or NoopStyleAdapter()
    profile = get_profile(platform)
    if profile is None:
        return StyleResult(platform, markdown, markdown, changed=False, note="该平台无风格画像，未改写")
    styled = adapter.adapt(markdown, profile)
    return StyleResult(
        platform=platform,
        original=markdown,
        styled=styled,
        changed=styled.strip() != markdown.strip(),
        note="" if styled.strip() != markdown.strip() else "改写结果与原文一致",
    )
