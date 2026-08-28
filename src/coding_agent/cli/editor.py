"""Byte-oriented line editor for the alternate-screen TUI.

Rich Live owns the screen, so we cannot use ``console.input()`` (it would
echo under the frame). Bytes come from raw/cbreak stdin; we emit actions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyAction:
    kind: str
    text: str = ""


def _utf8_len(lead: int) -> int:
    if lead < 0x80:
        return 1
    if lead < 0xE0:
        return 2
    if lead < 0xF0:
        return 3
    return 4


class LineEditor:
    def __init__(self) -> None:
        self.buffer = ""
        self.cursor = 0
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._stash = ""
        self._pending = b""
        self._pasting = False

    def display(self) -> str:
        return self.buffer[: self.cursor] + "█" + self.buffer[self.cursor :]

    def clear(self) -> None:
        self.buffer = ""
        self.cursor = 0
        self._hist_i = None

    def feed(self, data: bytes) -> list[KeyAction]:
        if not data:
            return []
        self._pending += data
        actions: list[KeyAction] = []
        while self._pending:
            consumed, action = self._take()
            if consumed == 0:
                break
            self._pending = self._pending[consumed:]
            if action is not None:
                actions.append(action)
        return actions

    def _take(self) -> tuple[int, KeyAction | None]:
        buf = self._pending
        lead = buf[0]
        if lead == 0x1B:
            return self._escape()
        if lead == 0x03:
            return 1, KeyAction("interrupt")
        if lead == 0x04:
            return 1, KeyAction("eof")
        if lead in (0x0D, 0x0A):
            if self._pasting:
                self._insert("\n")
                return 1, None
            return 1, self._submit()
        if lead in (0x7F, 0x08):
            self._backspace()
            return 1, None
        if lead == 0x15:
            self.buffer = self.buffer[self.cursor :]
            self.cursor = 0
            return 1, None
        if lead == 0x01:
            self.cursor = 0
            return 1, None
        if lead == 0x05:
            self.cursor = len(self.buffer)
            return 1, None
        if lead == 0x0B:
            self.buffer = self.buffer[: self.cursor]
            return 1, None
        if lead == 0x17:
            self._delete_word()
            return 1, None
        if lead == 0x0C:
            return 1, KeyAction("scroll_bottom")
        if lead < 0x20:
            return 1, None
        n = _utf8_len(lead)
        if len(buf) < n:
            return 0, None
        try:
            ch = buf[:n].decode("utf-8")
        except UnicodeDecodeError:
            return 1, None
        self._insert(ch)
        return n, None

    def _escape(self) -> tuple[int, KeyAction | None]:
        buf = self._pending
        if len(buf) == 1:
            return 0, None
        if buf[1:2] == b"[":
            i = 2
            while i < len(buf) and not (0x40 <= buf[i] <= 0x7E):
                i += 1
            if i >= len(buf):
                return 0, None
            params = buf[2:i].decode("ascii", "replace")
            final = chr(buf[i])
            return i + 1, self._csi(params, final)
        if buf[1:2] == b"O":
            if len(buf) < 3:
                return 0, None
            return 3, self._arrow(chr(buf[2]))
        return 1, None

    def _csi(self, params: str, final: str) -> KeyAction | None:
        if final == "~":
            if params == "200":
                self._pasting = True
                return None
            if params == "201":
                self._pasting = False
                return None
            if params == "3":
                self._delete()
                return None
            if params == "5":
                return KeyAction("page_up")
            if params == "6":
                return KeyAction("page_down")
            if params in ("1", "7"):
                self.cursor = 0
            elif params in ("4", "8"):
                self.cursor = len(self.buffer)
            return None
        if final in "ABCD":
            return self._arrow(final)
        if final == "H":
            self.cursor = 0
        elif final == "F":
            self.cursor = len(self.buffer)
        return None

    def _arrow(self, code: str) -> KeyAction | None:
        if code == "A":
            self._history(-1)
        elif code == "B":
            self._history(1)
        elif code == "C":
            self.cursor = min(len(self.buffer), self.cursor + 1)
        elif code == "D":
            self.cursor = max(0, self.cursor - 1)
        return None

    def _insert(self, ch: str) -> None:
        self.buffer = self.buffer[: self.cursor] + ch + self.buffer[self.cursor :]
        self.cursor += len(ch)
        self._hist_i = None

    def _backspace(self) -> None:
        if self.cursor <= 0:
            return
        self.buffer = self.buffer[: self.cursor - 1] + self.buffer[self.cursor :]
        self.cursor -= 1

    def _delete(self) -> None:
        if self.cursor >= len(self.buffer):
            return
        self.buffer = self.buffer[: self.cursor] + self.buffer[self.cursor + 1 :]

    def _delete_word(self) -> None:
        i = self.cursor
        while i > 0 and self.buffer[i - 1].isspace():
            i -= 1
        while i > 0 and not self.buffer[i - 1].isspace():
            i -= 1
        self.buffer = self.buffer[:i] + self.buffer[self.cursor :]
        self.cursor = i

    def _history(self, delta: int) -> None:
        if not self.history:
            return
        if self._hist_i is None:
            self._stash = self.buffer
            self._hist_i = len(self.history)
        nxt = self._hist_i + delta
        if nxt >= len(self.history):
            self._hist_i = None
            self.buffer = self._stash
            self.cursor = len(self.buffer)
            return
        self._hist_i = max(0, nxt)
        self.buffer = self.history[self._hist_i]
        self.cursor = len(self.buffer)

    def _submit(self) -> KeyAction:
        text = self.buffer
        if text.endswith("\\") and not text.endswith("\\\\"):
            self.buffer = text[:-1] + "\n"
            self.cursor = len(self.buffer)
            return KeyAction("redraw")
        self.clear()
        if text.strip():
            self.history.append(text)
        return KeyAction("submit", text)
