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


def decode_csi(params: str, final: str) -> KeyAction | None:
    """Shared CSI: mouse wheel, F1–F2 tabs."""
    if final in "Mm" and params.startswith("<"):
        parts = params[1:].split(";")
        try:
            btn = int(parts[0])
        except ValueError:
            return None
        if btn == 64:
            return KeyAction("wheel", "-3")
        if btn == 65:
            return KeyAction("wheel", "3")
        return None
    if final == "~":
        if params == "11":
            return KeyAction("main_tab", "chat")
        if params == "12":
            return KeyAction("main_tab", "text")
    return None


def decode_ss3(code: str) -> KeyAction | None:
    if code == "P":
        return KeyAction("main_tab", "chat")
    if code == "Q":
        return KeyAction("main_tab", "text")
    return None


class LineEditor:
    def __init__(self) -> None:
        self.buffer = ""
        self.cursor = 0
        self.history: list[str] = []
        self._hist_i: int | None = None
        self._stash = ""
        self._pending = b""
        self._pasting = False

    def display(self, *, active: bool = True) -> str:
        if not active:
            return self.buffer
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
        if lead == 0x09:
            return 1, KeyAction("cycle_focus")
        if lead == 0x14:
            return 1, KeyAction("cycle_tab")
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
        special = decode_csi(params, final)
        if special is not None:
            return special
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
        mapped = decode_ss3(code)
        if mapped is not None:
            return mapped
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


class NavKeys:
    """Key parser for the files / Changes pane (vim-ish)."""

    def __init__(self) -> None:
        self._pending = b""

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
            return 1, KeyAction("open")
        if lead == 0x09:
            return 1, KeyAction("cycle_focus")
        if lead == 0x14:
            return 1, KeyAction("cycle_tab")
        if lead < 0x20:
            return 1, None
        n = _utf8_len(lead)
        if len(buf) < n:
            return 0, None
        try:
            ch = buf[:n].decode("utf-8")
        except UnicodeDecodeError:
            return 1, None
        return n, self._letter(ch)

    def _escape(self) -> tuple[int, KeyAction | None]:
        buf = self._pending
        if len(buf) == 1:
            return 1, KeyAction("focus_input")
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
        return 1, KeyAction("focus_input")

    def _csi(self, params: str, final: str) -> KeyAction | None:
        special = decode_csi(params, final)
        if special is not None:
            return special
        if final == "~":
            if params == "5":
                return KeyAction("move", "-10")
            if params == "6":
                return KeyAction("move", "10")
            return None
        if final in "ABCD":
            return self._arrow(final)
        return None

    def _arrow(self, code: str) -> KeyAction | None:
        mapped = decode_ss3(code)
        if mapped is not None:
            return mapped
        if code == "A":
            return KeyAction("move", "-1")
        if code == "B":
            return KeyAction("move", "1")
        return None

    def _letter(self, ch: str) -> KeyAction | None:
        if ch in "kK":
            return KeyAction("move", "-1")
        if ch in "jJ":
            return KeyAction("move", "1")
        if ch == "c":
            return KeyAction("jump_changes")
        if ch in "dD":
            return KeyAction("diff")
        if ch in "eE":
            return KeyAction("open")
        if ch in "qQ":
            return KeyAction("focus_input")
        return None


class PickerKeys:
    """Key parser for the /skill, /mascot, and /model checkbox overlay."""

    def __init__(self) -> None:
        self._pending = b""

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
            return 1, KeyAction("cancel")
        if lead in (0x0D, 0x0A):
            return 1, KeyAction("confirm")
        if lead == 0x09:
            return 1, None
        if lead == 0x14:
            return 1, None
        if lead < 0x20:
            return 1, None
        n = _utf8_len(lead)
        if len(buf) < n:
            return 0, None
        try:
            ch = buf[:n].decode("utf-8")
        except UnicodeDecodeError:
            return 1, None
        return n, self._letter(ch)

    def _escape(self) -> tuple[int, KeyAction | None]:
        buf = self._pending
        if len(buf) == 1:
            return 1, KeyAction("cancel")
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
        return 1, KeyAction("cancel")

    def _csi(self, params: str, final: str) -> KeyAction | None:
        special = decode_csi(params, final)
        if special is not None:
            return special
        if final == "~":
            if params == "5":
                return KeyAction("move", "-10")
            if params == "6":
                return KeyAction("move", "10")
            return None
        if final in "ABCD":
            return self._arrow(final)
        return None

    def _arrow(self, code: str) -> KeyAction | None:
        mapped = decode_ss3(code)
        if mapped is not None:
            return mapped
        if code == "A":
            return KeyAction("move", "-1")
        if code == "B":
            return KeyAction("move", "1")
        return None

    def _letter(self, ch: str) -> KeyAction | None:
        if ch in "kK":
            return KeyAction("move", "-1")
        if ch in "jJ":
            return KeyAction("move", "1")
        if ch == " ":
            return KeyAction("toggle")
        if ch in "qQ":
            return KeyAction("cancel")
        return None
