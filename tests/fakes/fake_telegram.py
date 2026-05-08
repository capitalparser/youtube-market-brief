from __future__ import annotations


class FakeTelegramClient:
    def __init__(self, *, fail_at: int | None = None):
        self.sent: list[tuple[str, int | None]] = []
        self._fail_at = fail_at
        self._next_id = 1

    def send_message(self, text: str, *, reply_to_message_id: int | None = None) -> int:
        if self._fail_at is not None and len(self.sent) + 1 == self._fail_at:
            raise RuntimeError(f"fake telegram: forced failure at message {self._fail_at}")
        self.sent.append((text, reply_to_message_id))
        mid = self._next_id
        self._next_id += 1
        return mid
