# utils.py
# -*- coding: utf-8 -*-
import os, sys, time
from typing import Optional

# Forzar UTF-8 (emojis) en Windows
try:
    if os.name == "nt":
        os.system("chcp 65001 >nul")
except Exception:
    pass

# Colores
try:
    from colorama import init as _colorama_init, Fore, Style
    _colorama_init(convert=True, autoreset=True)
except Exception:
    class _Dummy:
        RESET_ALL=''; BRIGHT=''; CYAN=''; GREEN=''; YELLOW=''; RED=''; MAGENTA=''; BLUE=''
    Fore=_Dummy(); Style=_Dummy()

def supports_emojis_default() -> bool:
    v = os.environ.get("INSTACLI_EMOJI")
    if v is not None:
        return v not in ("0","false","False")
    return True

EMOJI_ON = supports_emojis_default()

def em(s: str) -> str:
    if EMOJI_ON: return s
    return (s.replace("🏆","*").replace("🤖","(bot)").replace("🔐","[Cuentas]")
             .replace("🗂️","[Leads]").replace("📜","[Logs]").replace("📦","[Cliente]")
             .replace("💬","[Msg]").replace("📊","[Tablero]").replace("🚪","[Salir]")
             .replace("🟢","[ON]").replace("⚪","[OFF]").replace("✅","OK").replace("⛔","OFF"))

SEP = "————————————————————————"

def banner():
    clear_console()
    print(SEP); print(SEP); print()
    print(f"{em('🏆🏆')} HERRAMIENTA DE MENSAJERÍA DE IG {em('🏆🏆')}")
    print(); print(SEP); print(SEP); print()

def clear_console():
    try:
        os.system('cls' if os.name=='nt' else 'clear')
    except Exception:
        print('\n'*2)

def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""

def press_enter(msg: str = 'Presioná Enter para continuar...'):
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
                print(f'Ingresá un número >= {min_value}')
                continue
            return v
        except Exception:
            print('Número inválido.')

def ok(msg: str): print(f"{Fore.GREEN}✔ {msg}{Style.RESET_ALL}")
def warn(msg: str): print(f"{Fore.YELLOW}⚠ {msg}{Style.RESET_ALL}")
def err(msg: str): print(f"{Fore.RED}✖ {msg}{Style.RESET_ALL}")
def title(msg: str): print(f"{Style.BRIGHT}{Fore.CYAN}{msg}{Style.RESET_ALL}")
def bullet(msg: str): print(f" • {msg}")
