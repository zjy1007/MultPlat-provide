"""平台适配器集合。导入即触发各适配器向 registry 注册。"""

from . import wechat, xiaohongshu  # noqa: F401  （导入以触发 @register）
