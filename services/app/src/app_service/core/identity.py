"""业务操作人来源。

当前登录 API 尚未落地，因此先使用服务端配置身份，阻止客户端通过请求体
伪造 ``created_by``。认证完成后，此依赖应改为从已验证会话返回当前用户。
"""

from app_service.core.config import get_settings


def get_trusted_actor() -> str:
    """返回服务端控制的过渡期操作人标识。"""

    return get_settings().default_hr_id
