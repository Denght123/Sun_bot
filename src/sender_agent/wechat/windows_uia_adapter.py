from __future__ import annotations

import time
from typing import Any

from sender_agent.errors import (
    WechatAutomationError,
    WechatChatNotFoundError,
    WechatLoggedOutError,
    WechatWindowNotFoundError,
)
from sender_agent.wechat.base import WechatAutomation, WechatLoginStatus


class WindowsUiaWechatAutomation(WechatAutomation):
    def __init__(
        self,
        *,
        window_title_hint: str = "微信",
        send_delay_ms: int = 300,
        search_timeout_seconds: int = 10,
    ) -> None:
        self.window_title_hint = window_title_hint
        self.send_delay_seconds = max(0, send_delay_ms) / 1000
        self.search_timeout_seconds = max(1, search_timeout_seconds)
        self._available = False
        self._auto: Any | None = None
        try:
            import uiautomation as auto
        except ImportError:
            return
        self._auto = auto
        self._available = True

    def check_login_status(self) -> WechatLoginStatus:
        if not self._available:
            return "unknown"
        window = self._find_window(raise_on_missing=False)
        if window is None:
            raise WechatWindowNotFoundError("WeChat desktop window was not found")
        if self._looks_logged_out(window):
            return "logged_out"
        return "logged_in"

    def ensure_ready(self) -> None:
        if not self._available or self._auto is None:
            raise WechatAutomationError("uiautomation dependency is not installed")
        window = self._find_window(raise_on_missing=True)
        if self._looks_logged_out(window):
            raise WechatLoggedOutError("WeChat is not logged in; please re-login manually")
        try:
            window.SetActive()
        except Exception as exc:  # pragma: no cover - depends on Windows UI runtime
            raise WechatAutomationError(f"Failed to activate WeChat window: {exc}") from exc

    def open_chat(self, target_user: str) -> None:
        self.ensure_ready()
        if not target_user.strip():
            raise ValueError("target_user must not be empty")
        window = self._find_window(raise_on_missing=True)
        search_box = self._find_search_box(window)
        if search_box is None:
            raise WechatAutomationError("Unable to locate WeChat search box")

        self._focus_control(search_box)
        self._clear_text(search_box)
        self._paste_text(target_user)
        time.sleep(min(self.send_delay_seconds, 0.5))

        chat_item = self._find_chat_item(window, target_user)
        if chat_item is None:
            raise WechatChatNotFoundError(f"WeChat chat with remark name '{target_user}' was not found")

        try:
            chat_item.Click(simulateMove=False)
        except Exception as exc:  # pragma: no cover - depends on Windows UI runtime
            raise WechatAutomationError(f"Failed to open WeChat chat '{target_user}': {exc}") from exc

    def send_text(self, text: str) -> None:
        self.ensure_ready()
        if not text:
            raise ValueError("text must not be empty")
        window = self._find_window(raise_on_missing=True)
        editor = self._find_message_editor(window)
        if editor is None:
            raise WechatAutomationError("Unable to locate WeChat message input editor")

        self._focus_control(editor)
        self._paste_text(text)
        try:
            self._auto.SendKeys("{Enter}")
        except Exception as exc:  # pragma: no cover - depends on Windows UI runtime
            raise WechatAutomationError(f"Failed to send WeChat message: {exc}") from exc
        time.sleep(self.send_delay_seconds)

    def _find_window(self, *, raise_on_missing: bool) -> Any | None:
        assert self._auto is not None
        title_hints = [self.window_title_hint, "微信", "WeChat"]
        for hint in title_hints:
            window = self._auto.WindowControl(searchDepth=1, Name=hint)
            if window.Exists(maxSearchSeconds=1):
                return window
        if raise_on_missing:
            raise WechatWindowNotFoundError("WeChat desktop window was not found")
        return None

    def _looks_logged_out(self, window: Any) -> bool:
        login_indicators = ["登录", "扫码登录", "手机确认登录"]
        for name in login_indicators:
            try:
                control = window.TextControl(Name=name)
                if control.Exists(maxSearchSeconds=0.2):
                    return True
            except Exception:  # pragma: no cover - depends on Windows UI runtime
                continue
        return False

    def _find_search_box(self, window: Any) -> Any | None:
        candidates = [
            lambda: window.EditControl(foundIndex=1),
            lambda: window.EditControl(Name="搜索"),
            lambda: window.Control(searchDepth=8, ClassName="EditWnd"),
        ]
        return self._first_existing(candidates)

    def _find_chat_item(self, window: Any, target_user: str) -> Any | None:
        candidates = [
            lambda: window.ListItemControl(Name=target_user),
            lambda: window.TextControl(Name=target_user),
            lambda: window.ButtonControl(Name=target_user),
        ]
        return self._first_existing(candidates, timeout=self.search_timeout_seconds)

    def _find_message_editor(self, window: Any) -> Any | None:
        candidates = [
            lambda: window.EditControl(foundIndex=2),
            lambda: window.Control(searchDepth=12, ClassName="RichEdit50W"),
            lambda: window.Control(searchDepth=12, ClassName="EditWnd"),
        ]
        return self._first_existing(candidates)

    def _first_existing(self, factories: list[Any], timeout: float = 1) -> Any | None:
        for factory in factories:
            try:
                control = factory()
                if control is not None and control.Exists(maxSearchSeconds=timeout):
                    return control
            except Exception:  # pragma: no cover - depends on Windows UI runtime
                continue
        return None

    def _focus_control(self, control: Any) -> None:
        try:
            control.Click(simulateMove=False)
        except Exception as exc:  # pragma: no cover - depends on Windows UI runtime
            raise WechatAutomationError(f"Failed to focus WeChat control: {exc}") from exc

    def _clear_text(self, control: Any) -> None:
        try:
            control.SendKeys("{Ctrl}a{Del}")
        except Exception:  # pragma: no cover - depends on Windows UI runtime
            self._auto.SendKeys("{Ctrl}a{Del}")

    def _paste_text(self, text: str) -> None:
        assert self._auto is not None
        try:
            self._auto.SetClipboardText(text)
            self._auto.SendKeys("{Ctrl}v")
        except Exception as exc:  # pragma: no cover - depends on Windows UI runtime
            raise WechatAutomationError(f"Failed to paste text into WeChat: {exc}") from exc
