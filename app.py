# app.py
# -*- coding: utf-8 -*-
import importlib, time
from utils import banner, SEP, em, ask, press_enter, warn

def _safe_import(name):
    try:
        return importlib.import_module(name)
    except Exception as e:
        warn(f"Módulo no disponible o con error: {name} ({e})")
        return None

accounts = _safe_import("accounts")
leads     = _safe_import("leads")
ig        = _safe_import("ig")
storage   = _safe_import("storage")
responder = _safe_import("responder")
licensekit= _safe_import("licensekit")

def _counts():
    try:
        items=accounts.list_all()
        n=len(items); c=sum(1 for i in items if i.get("connected")); a=sum(1 for i in items if i.get("active"))
        return n,c,a
    except Exception:
        return 0,0,0

def _message_totals():
    if ig and hasattr(ig, "get_message_totals"):
        try:
            return ig.get_message_totals()
        except Exception:
            pass
    if storage and hasattr(storage, "sent_totals"):
        try:
            return storage.sent_totals()
        except Exception:
            pass
    return 0,0

def menu():
    while True:
        banner()
        n,c,a=_counts()
        ok_total, err_total = _message_totals()
        print(f"Cuentas: {n}\nConectadas: {c}\nActivas: {a}\n")
        print(f"Mensajes enviados: {ok_total}")
        print(f"Mensajes con error: {err_total}\n")
        print(SEP); print(SEP); print()
        print("1) "+em("🔐")+" Gestionar cuentas")
        print("2) "+em("🗂️")+" Gestionar leads (crear / importar CSV)")
        print("3) "+em("💬")+" Enviar mensajes (rotando cuentas activas)")
        print("4) "+em("📜")+" Ver registros de envíos")
        print("5) "+em("🤖")+" Auto-responder con OpenAI")
        print("6) "+em("📊")+" Ver tablero Supabase (mensajes y estados)")
        print("7) "+em("📦")+" Entregar a cliente (licencia / EXE)")
        print("8) "+em("🚪")+" Salir\n")
        print(SEP); print(SEP); print()
        op=ask("Opción: ").strip()
        if op=="1" and accounts: accounts.menu_accounts()
        elif op=="2" and leads: leads.menu_leads()
        elif op=="3" and ig: ig.menu_send_rotating()
        elif op=="4" and storage: storage.menu_logs()
        elif op=="5" and responder: responder.menu_autoresponder()
        elif op=="6" and storage: storage.menu_supabase()
        elif op=="7" and licensekit: licensekit.menu_deliver()
        elif op=="8":
            print("Saliendo..."); time.sleep(0.3); break
        else:
            warn("Opción inválida o módulo faltante."); press_enter()

if __name__=="__main__":
    menu()
