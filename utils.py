# utils.py
# -*- coding: utf-8 -*-
"""General helpers for prompts and console feedback."""

from __future__ import annotations

import os
from typing import Optional

from typing import Optional

from ui import (
    EMOJI_ON,
    Fore,
    Style,
    banner as ui_banner,
    clear_console as ui_clear_console,
    em,
    full_line,
    style_text,
)


SEP = full_line()


def banner() -> None:
    ui_banner()


def clear_console() -> None:
    ui_clear_console()


def supports_emojis_default() -> bool:
    return EMOJI_ON


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def press_enter(msg: str = "Presioná Enter para continuar...") -> None:
    try:
        input(msg)
    except EOFError:
        pass


def ask_int(prompt: str, min_value: int = 0, default: Optional[int] = None) -> int:
    while True:
        s = ask(prompt).strip()
        if not s and default is not None:
            return default
        try:
            v = int(s)
            if v < min_value:
                print(f"Ingresá un número >= {min_value}")
                continue
            return v
        except Exception:
            print("Número inválido.")


def ok(msg: str) -> None:
    print(f"{Fore.GREEN}✔ {msg}{Style.RESET_ALL}")


def warn(msg: str) -> None:
    print(f"{Fore.YELLOW}⚠ {msg}{Style.RESET_ALL}")


def err(msg: str) -> None:
    print(f"{Fore.RED}✖ {msg}{Style.RESET_ALL}")


def title(msg: str) -> None:
    print(style_text(msg, color=Fore.CYAN, bold=True))


def bullet(msg: str) -> None:
    print(f" • {msg}")


def env_hint(key: str, value: str | None) -> str:
    shown = value if value else "(sin definir)"
    return f"{key} = {shown}"
