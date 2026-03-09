from __future__ import annotations

from types import SimpleNamespace

import pytest

from sender_agent.errors import WechatAutomationError, WechatLoggedOutError, WechatWindowNotFoundError
from sender_agent.wechat.windows_uia_adapter import WindowsUiaWechatAutomation


class FakeControl:
    def __init__(self, *, exists: bool = True, fail_click: bool = False, fail_send_keys: bool = False) -> None:
        self._exists = exists
        self.fail_click = fail_click
        self.fail_send_keys = fail_send_keys
        self.clicked = False
        self.sent_keys: list[str] = []

    def Exists(self, maxSearchSeconds=0):
        return self._exists

    def Click(self, simulateMove=False):
        if self.fail_click:
            raise RuntimeError("click failed")
        self.clicked = True

    def SendKeys(self, value: str):
        if self.fail_send_keys:
            raise RuntimeError("send keys failed")
        self.sent_keys.append(value)


class FakeWindow(FakeControl):
    def __init__(self, *, logged_out: bool = False, search_box=None, chat_item=None, editor=None) -> None:
        super().__init__(exists=True)
        self.logged_out = logged_out
        self.search_box = search_box
        self.chat_item = chat_item
        self.editor = editor
        self.active = False

    def SetActive(self):
        self.active = True

    def TextControl(self, Name=None):
        if self.logged_out and Name in {"登录", "扫码登录", "手机确认登录"}:
            return FakeControl(exists=True)
        if self.chat_item is not None and Name == "测试联系人":
            return self.chat_item
        return FakeControl(exists=False)

    def EditControl(self, foundIndex=None, Name=None):
        if Name == "搜索":
            return self.search_box or FakeControl(exists=False)
        if foundIndex == 1:
            return self.search_box or FakeControl(exists=False)
        if foundIndex == 2:
            return self.editor or FakeControl(exists=False)
        return FakeControl(exists=False)

    def Control(self, searchDepth=None, ClassName=None):
        if ClassName in {"RichEdit50W", "EditWnd"} and self.editor is not None:
            return self.editor
        if ClassName == "EditWnd" and self.search_box is not None:
            return self.search_box
        return FakeControl(exists=False)

    def ListItemControl(self, Name=None):
        if self.chat_item is not None and Name == "测试联系人":
            return self.chat_item
        return FakeControl(exists=False)

    def ButtonControl(self, Name=None):
        if self.chat_item is not None and Name == "测试联系人":
            return self.chat_item
        return FakeControl(exists=False)


class FakeAuto:
    def __init__(self, window=None, *, fail_clipboard: bool = False) -> None:
        self.window = window
        self.fail_clipboard = fail_clipboard
        self.sent_keys: list[str] = []
        self.clipboard: list[str] = []

    def WindowControl(self, searchDepth=1, Name=None):
        if self.window is None:
            return FakeControl(exists=False)
        return self.window

    def SetClipboardText(self, text: str):
        if self.fail_clipboard:
            raise RuntimeError("clipboard failed")
        self.clipboard.append(text)

    def SendKeys(self, value: str):
        self.sent_keys.append(value)


def build_adapter(auto) -> WindowsUiaWechatAutomation:
    adapter = WindowsUiaWechatAutomation()
    adapter._auto = auto
    adapter._available = True
    adapter.send_delay_seconds = 0
    adapter.search_timeout_seconds = 1
    return adapter


def test_check_login_status_returns_unknown_when_uia_unavailable() -> None:
    adapter = WindowsUiaWechatAutomation()

    assert adapter.check_login_status() == "unknown"


def test_ensure_ready_raises_when_uia_missing() -> None:
    adapter = WindowsUiaWechatAutomation()

    with pytest.raises(WechatAutomationError, match="uiautomation dependency is not installed"):
        adapter.ensure_ready()


def test_check_login_status_detects_logged_out_window() -> None:
    adapter = build_adapter(FakeAuto(window=FakeWindow(logged_out=True)))

    assert adapter.check_login_status() == "logged_out"


def test_ensure_ready_raises_when_window_not_found() -> None:
    adapter = build_adapter(FakeAuto(window=None))

    with pytest.raises(WechatWindowNotFoundError):
        adapter.ensure_ready()


def test_ensure_ready_raises_when_logged_out() -> None:
    adapter = build_adapter(FakeAuto(window=FakeWindow(logged_out=True)))

    with pytest.raises(WechatLoggedOutError):
        adapter.ensure_ready()


def test_open_chat_searches_and_clicks_contact() -> None:
    search_box = FakeControl()
    chat_item = FakeControl()
    window = FakeWindow(search_box=search_box, chat_item=chat_item, editor=FakeControl())
    auto = FakeAuto(window=window)
    adapter = build_adapter(auto)

    adapter.open_chat("测试联系人")

    assert window.active is True
    assert chat_item.clicked is True
    assert auto.clipboard[0] == "测试联系人"


def test_send_text_pastes_message_and_hits_enter() -> None:
    editor = FakeControl()
    window = FakeWindow(search_box=FakeControl(), chat_item=FakeControl(), editor=editor)
    auto = FakeAuto(window=window)
    adapter = build_adapter(auto)

    adapter.send_text("日报正文")

    assert editor.clicked is True
    assert auto.clipboard[-1] == "日报正文"
    assert auto.sent_keys[-2:] == ["{Ctrl}v", "{Enter}"]


def test_send_text_raises_when_clipboard_paste_fails() -> None:
    editor = FakeControl()
    window = FakeWindow(search_box=FakeControl(), chat_item=FakeControl(), editor=editor)
    adapter = build_adapter(FakeAuto(window=window, fail_clipboard=True))

    with pytest.raises(WechatAutomationError, match="Failed to paste text into WeChat"):
        adapter.send_text("日报正文")
