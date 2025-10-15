# accounts.py
# -*- coding: utf-8 -*-
import json, os, getpass, time
from pathlib import Path
from typing import List, Dict
from utils import banner, em, ask, press_enter, ok, warn, title
from session_store import has_session, remove as remove_session, save_from

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
FILE = DATA / "accounts.json"

def _load() -> List[Dict]:
    if not FILE.exists():
        return []
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save(items: List[Dict]):
    FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

def list_all() -> List[Dict]:
    return _load()

def _find(items, username):
    for it in items:
        if it.get("username","").lower()==username.lower():
            return it
    return None

def add_account(username:str, alias:str):
    items=_load()
    if _find(items, username):
        warn("Ya existe.")
        return
    rec={"username":username.strip().lstrip("@"), "alias":alias, "active":True, "connected":False}
    items.append(rec); _save(items); ok("Agregada.")

def remove_account(username:str):
    items=_load()
    new=[it for it in items if it.get("username","").lower()!=username.lower()]
    _save(new)
    remove_session(username)
    ok("Eliminada (si existía).")

def set_active(username:str, is_active:bool=True):
    items=_load()
    it=_find(items, username)
    if it: it["active"]=is_active; _save(items); ok("Actualizada.")
    else: warn("No existe.")

def mark_connected(username:str, connected:bool):
    items=_load(); it=_find(items, username)
    if it: it["connected"]=connected; _save(items)

def _login_and_save_session(username:str, password:str)->bool:
    """
    Login con instagrapi y guarda sesión en .sessions/<username>.json
    """
    try:
        from instagrapi import Client
        cl=Client()
        cl.login(username, password)
        save_from(cl, username)
        mark_connected(username, True)
        ok(f"Sesión guardada para {username}.")
        return True
    except Exception as e:
        warn(f"No se pudo iniciar sesión para {username}: {e}")
        mark_connected(username, False)
        return False


def prompt_login(username: str) -> bool:
    pwd = getpass.getpass(f"Password @{username}: ")
    if not pwd:
        warn("Se canceló el inicio de sesión.")
        return False
    return _login_and_save_session(username, pwd)

def menu_accounts():
    while True:
        banner()
        items=_load()
        aliases = sorted(set([it.get("alias","default") for it in items]) | {"default"})
        title("Alias disponibles: " + ", ".join(aliases))
        alias = ask("Alias / grupo (ej default, ventas, matias): ").strip() or "default"

        print("\nCuentas del alias:", alias)
        group=[it for it in items if it.get("alias")==alias]
        if not group:
            print("(no hay cuentas aún)")
        else:
            for it in group:
                flag = em("🟢") if it.get("active") else em("⚪")
                conn = "[conectada]" if it.get("connected") else "[no conectada]"
                sess = "[sesión]" if has_session(it["username"]) else "[sin sesión]"
                print(f" - @{it['username']} {conn} {sess} {flag}")

        print("\n1) Agregar cuenta")
        print("2) Eliminar cuenta")
        print("3) Activar/Desactivar cuenta")
        print("4) Iniciar sesión y guardar sesiónid (auto en TODAS del alias)")
        print("5) Iniciar sesión y guardar sesión ID (seleccionar cuenta)")
        print("6) Volver\n")

        op=ask("Opción: ").strip()
        if op=="1":
            u=ask("Username (sin @): ").strip().lstrip("@")
            if not u: continue
            add_account(u, alias)
            prompt_login(u)
            press_enter()
        elif op=="2":
            u=ask("Username a eliminar: ").strip().lstrip("@")
            remove_account(u); press_enter()
        elif op=="3":
            u=ask("Username: ").strip().lstrip("@")
            val=ask("1=activar, 0=desactivar: ").strip()
            set_active(u, val=="1"); press_enter()
        elif op=="4":
            print("Se pedirá contraseña por cada cuenta...")
            for it in [x for x in _load() if x.get("alias")==alias]:
                prompt_login(it["username"])
            press_enter()
        elif op=="5":
            group = [x for x in _load() if x.get("alias") == alias]
            if not group:
                warn("No hay cuentas para iniciar sesión.")
                press_enter()
                continue
            print("Seleccioná cuentas por número o username (coma separada, * para todas):")
            for idx, acct in enumerate(group, start=1):
                sess = "[sesión]" if has_session(acct["username"]) else "[sin sesión]"
                print(f" {idx}) @{acct['username']} {sess}")
            raw = ask("Selección: ").strip()
            if not raw:
                warn("Sin selección.")
                press_enter()
                continue
            targets: List[Dict] = []
            if raw == "*":
                targets = group
            else:
                chosen = set()
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    if part.isdigit():
                        idx = int(part)
                        if 1 <= idx <= len(group):
                            chosen.add(group[idx - 1]["username"])
                    else:
                        chosen.add(part.lstrip("@"))
                targets = [acct for acct in group if acct["username"] in chosen]
            if not targets:
                warn("No se encontraron cuentas con esos datos.")
                press_enter()
                continue
            for acct in targets:
                prompt_login(acct["username"])
            press_enter()
        elif op=="6":
            break
        else:
            warn("Opción inválida."); press_enter()
