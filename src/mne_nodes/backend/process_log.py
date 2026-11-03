"""ANSI-formatted progress output for generated pipeline scripts.

While a pipeline runs, ``sys.stdout`` and ``sys.stderr`` are wrapped so that
all output, including prints from node functions, is indented inside frames
for the current recording and function.

Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from __future__ import annotations

import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
GRAY = "\x1b[90m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[94m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"

RULE_WIDTH = 70
_UNICODE = {
    "start": "▶",
    "done": "✔",
    "fail": "✘",
    "cached": "↺",
    "load": "⇣",
    "save": "⇡",
    "from": "←",
    "to": "→",
    "v": "│",
    "h": "─",
    "top": "╭",
    "bottom": "╰",
    "ftop": "┌",
    "fbottom": "└",
}
_ASCII = dict(
    _UNICODE,
    start=">",
    done="+",
    fail="x",
    cached="~",
    load="<",
    save=">",
    **{"from": "<-", "to": "->"},
    v="|",
    h="-",
    top="+",
    bottom="+",
    ftop="+",
    fbottom="+",
)
_LINE_BREAK = re.compile(r"(\r\n|\n|\r)")


class _State:
    frames: ClassVar[list[str]] = []
    item: tuple[str, float] | None = None
    last: str | None = None


def use_color() -> bool:
    """Return whether ANSI styling should be written to stdout.

    Follows the ``NO_COLOR``/``FORCE_COLOR`` conventions and otherwise only
    styles interactive terminals.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def style(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes if styling is enabled."""
    if not codes or not use_color():
        return text
    return f"{''.join(codes)}{text}{RESET}"


def _glyphs() -> dict[str, str]:
    """Return box/symbol characters supported by the stdout encoding."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "".join(_UNICODE.values()).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return _ASCII
    return _UNICODE


class FramedStream:
    """Text stream proxy prefixing each output line with the active frames."""

    def __init__(self, stream):
        self._stream = stream
        self.at_line_start = True

    def write(self, text: str) -> int:
        prefix = "".join(_State.frames)
        parts = []
        for part in _LINE_BREAK.split(text):
            if not part:
                continue
            if part in ("\n", "\r\n"):
                # Continue the frame bars through empty lines.
                if self.at_line_start and prefix:
                    parts.append(prefix.rstrip())
                self.at_line_start = True
            elif part == "\r":
                self.at_line_start = True
            else:
                if self.at_line_start:
                    parts.append(prefix)
                self.at_line_start = False
            parts.append(part)
        self._stream.write("".join(parts))
        return len(text)

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _install() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if not isinstance(stream, FramedStream):
            setattr(sys, name, FramedStream(stream))


def _uninstall() -> None:
    _State.frames.clear()
    _State.item = None
    _State.last = None
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if isinstance(stream, FramedStream):
            setattr(sys, name, stream._stream)


def _emit(text: str = "") -> None:
    if getattr(sys.stdout, "at_line_start", True) is False:
        text = "\n" + text
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding), flush=True)


def _separate() -> None:
    """Insert an empty (framed) line between consecutive blocks."""
    if _State.last not in (None, "item", "load"):
        _emit()


def _describe(path) -> str:
    """Return a short display name for a path, BIDSPath, or list of them."""
    if isinstance(path, (list, tuple)):
        return f"{len(path)} files"
    basename = getattr(path, "basename", None)
    return basename or Path(str(path)).name


def _duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes} min {seconds} s"


def _since(start: float) -> str:
    return _duration(time.monotonic() - start)


def pipeline_start(name: str | None = None) -> float:
    """Start framing the output and return the pipeline start time."""
    _install()
    title = f"Starting pipeline {name}" if name else "Starting pipeline"
    _emit(style(f"{_glyphs()['start']} {title}", BOLD, CYAN))
    return time.monotonic()


def pipeline_finished(start: float) -> None:
    """Close open frames, announce the finished pipeline and stop framing."""
    _close_item()
    _emit()
    finished = f"{_glyphs()['done']} Pipeline finished in {_since(start)}"
    _emit(style(finished, BOLD, GREEN))
    _uninstall()


def _close_item() -> None:
    if _State.item is None:
        return
    name, start = _State.item
    g = _glyphs()
    _emit()
    _State.frames.pop()
    _State.item = None
    _emit(
        style(f"{g['bottom']}{g['h']} {g['done']} {name} ", MAGENTA)
        + style(f"({_since(start)})", GRAY)
    )


def item_start(selection_type: str, item, index: int, total: int) -> None:
    """Close the previous recording/group frame and open a new one."""
    _close_item()
    g = _glyphs()
    name = _describe(item)
    counter = f"[{index}/{total}] {selection_type}"
    rule = g["h"] * max(3, RULE_WIDTH - len(name) - len(counter) - 6)
    _emit()
    _emit(
        style(f"{g['top']}{g['h']} ", MAGENTA)
        + style(name, BOLD, MAGENTA)
        + " "
        + style(counter, GRAY)
        + style(f" {rule}", MAGENTA)
    )
    _State.frames.append(style(g["v"], MAGENTA) + " ")
    _State.item = (name, time.monotonic())
    _State.last = "item"


@contextmanager
def loading(name: str, source=None):
    """Announce loading of input data and indent the loader's output."""
    g = _glyphs()
    _separate()
    text = style(f"{g['load']} Loading ", CYAN) + style(name, BOLD, CYAN)
    if source is not None:
        text += style(f" {g['from']} {_describe(source)}", GRAY)
    _emit(text)
    _State.frames.append("  ")
    try:
        yield
    except BaseException:
        _uninstall()
        raise
    _State.frames.pop()
    _State.last = "load"


@contextmanager
def function(name: str):
    """Frame the execution of a node function, including all its output."""
    g = _glyphs()
    _separate()
    _emit(
        style(f"{g['ftop']}{g['h']} {g['start']} ", YELLOW) + style(name, BOLD, YELLOW)
    )
    _State.frames.append(style(g["v"], YELLOW) + " ")
    start = time.monotonic()
    try:
        yield
    except BaseException:
        _State.frames.pop()
        _emit(
            style(f"{g['fbottom']}{g['h']} ", YELLOW)
            + style(f"{g['fail']} {name} failed ", BOLD, RED)
            + style(f"({_since(start)})", GRAY)
        )
        _uninstall()
        raise
    _State.frames.pop()
    _emit(
        style(f"{g['fbottom']}{g['h']} ", YELLOW)
        + style(f"{g['done']} {name} ", GREEN)
        + style(f"({_since(start)})", GRAY)
    )
    _State.last = "function"


def function_cached(name: str) -> None:
    """Announce reuse of a cached subject-level function result."""
    _separate()
    g = _glyphs()
    _emit(style(f"{g['cached']} {name} (reused for the same subject)", GRAY))
    _State.last = "function"


def save(name: str, target) -> None:
    """Announce saving of output data to a derivative file."""
    g = _glyphs()
    text = style(f"{g['save']} Saving ", BLUE) + style(name, BOLD, BLUE)
    _emit(text + style(f" {g['to']} {_describe(target)}", GRAY))
    _State.last = "save"
