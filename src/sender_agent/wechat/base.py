from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

WechatLoginStatus = Literal["logged_in", "logged_out", "unknown"]


class WechatAutomation(ABC):
    @abstractmethod
    def check_login_status(self) -> WechatLoginStatus:
        raise NotImplementedError

    @abstractmethod
    def ensure_ready(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def open_chat(self, target_user: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def send_text(self, text: str) -> None:
        raise NotImplementedError

    def send_chunks(self, target_user: str, chunks: list[str]) -> int:
        self.ensure_ready()
        self.open_chat(target_user)
        sent_count = 0
        for chunk in chunks:
            self.send_text(chunk)
            sent_count += 1
        return sent_count
