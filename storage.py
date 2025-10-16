# storage.py
# -*- coding: utf-8 -*-
import json
import re
import time
from pathlib import Path

from config import SETTINGS, read_env_local, update_env_local
from ui import Fore, banner, full_line, style_text
from utils import ask, ok, press_enter, warn

BASE = Path(__file__).resolve().parent
STO = BASE / "storage"
STO.mkdir(exist_ok=True)
SENT = STO / "sent_log.jsonl"
AUTO = STO / "autoresponder_state.json"


def log_sent(account: str, username: str, okflag: bool, detail: str = ""):
    rec = {
        "ts": int(time.time()),
        "account": account,
        "to": username,
        "ok": bool(okflag),
        "detail": detail,
    }
    with SENT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def already_contacted(username: str) -> bool:
    if not SENT.exists():
        return False
    for line in SENT.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("to", "").lower() == username.lower():
            return True
    return False


def sent_totals() -> tuple[int, int]:
    """Devuelve totales acumulados de envíos OK y con error."""
    if not SENT.exists():
        return 0, 0
    ok_count = 0
    error_count = 0
    for line in SENT.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("ok"):
            ok_count += 1
        else:
            error_count += 1
    return ok_count, error_count


def menu_logs():
    banner()
    print(style_text("Últimos envíos:", bold=True, color=Fore.CYAN))
    if not SENT.exists():
        print("(sin registros)")
        press_enter()
        return
    lines = SENT.read_text(encoding="utf-8").splitlines()[-50:]
    for ln in lines:
        try:
            obj = json.loads(ln)
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(obj["ts"]))
            status = "OK" if obj.get("ok") else "ERROR"
            print(
                f"{ts}  @{obj.get('account')} → @{obj.get('to')}  [{status}] {obj.get('detail', '')}"
            )
        except Exception:
            pass
    press_enter()


def get_auto_state() -> dict:
    if not AUTO.exists():
        return {}
    try:
        return json.loads(AUTO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_auto_state(state: dict):
    AUTO.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _current_supabase() -> tuple[str, str]:
    env_local = read_env_local()
    url = env_local.get("SUPABASE_URL") or SETTINGS.supabase_url or ""
    key = env_local.get("SUPABASE_KEY") or SETTINGS.supabase_key or ""
    return url, key


def _is_valid_url(url: str) -> bool:
    return bool(re.match(r"^https?://", url))


def menu_supabase() -> None:
    while True:
        banner()
        url, key = _current_supabase()
        print(full_line())
        print(style_text("Configuración de Supabase", color=Fore.CYAN, bold=True))
        print(full_line())
        print(f"URL actual: {url or '(sin definir)'}")
        masked = key[:4] + "…" if key else "(sin definir)"
        print(f"API Key: {masked}")
        print()
        print("1) Configurar SUPABASE_URL")
        print("2) Configurar SUPABASE_KEY")
        print("3) Probar conexión")
        print("4) Volver")
        print()
        choice = ask("Opción: ").strip()
        if choice == "1":
            new_url = ask("Nueva URL (dejar vacío para cancelar): ").strip()
            if not new_url:
                warn("Sin cambios.")
                press_enter()
                continue
            if not _is_valid_url(new_url):
                warn("La URL debe comenzar con http:// o https://")
                press_enter()
                continue
            update_env_local({"SUPABASE_URL": new_url})
            ok("SUPABASE_URL guardada en .env.local")
            press_enter()
        elif choice == "2":
            new_key = ask("Nueva SUPABASE_KEY (dejar vacío para cancelar): ").strip()
            if not new_key:
                warn("Sin cambios.")
                press_enter()
                continue
            update_env_local({"SUPABASE_KEY": new_key})
            ok("SUPABASE_KEY guardada en .env.local")
            press_enter()
        elif choice == "3":
            url, key = _current_supabase()
            if url and key:
                print(style_text("OK: valores configurados.", color=Fore.GREEN, bold=True))
            else:
                warn("Falta URL o KEY para probar conexión.")
            press_enter()
        elif choice == "4":
            break
        else:
            warn("Opción inválida.")
            press_enter()
