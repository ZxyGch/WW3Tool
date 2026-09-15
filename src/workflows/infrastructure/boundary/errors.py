"""外部边界谱错误码与异常。"""

from __future__ import annotations

from typing import Any


class BoundaryError(RuntimeError):
    """边界功能失败。CLI/JSON 使用稳定 ``code``；GUI 使用翻译后的 ``message``。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        hints: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = dict(context or {})
        self.hints = list(hints or [])

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }
        if self.hints:
            payload["hints"] = list(self.hints)
        return payload
