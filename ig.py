# ig.py
# -*- coding: utf-8 -*-
import json, time, random, os, sys
from pathlib import Path
from typing import List
from utils import banner, em, title, ask, ask_int, press_enter, ok, warn, err
from accounts import list_all
from leads import load_list
from storage import log_sent, already_contacted

# Q to stop (Windows/non-blocking)
def _q_pressed():
    try:
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return ch.lower()=='q'
    except Exception:
        return False
    return False

def _client_for(username:str):
    from instagrapi import Client
    cl=Client()
    ses=Path(__file__).resolve().parent/".sessions"/f"{username}.json"
    if ses.exists():
        cl.load_settings(str(ses))
        try:
            cl.get_timeline_feed()  # ping
        except Exception:
            pass
    else:
        raise RuntimeError(f"No hay sesión guardada para {username}. Usá opción 1.")
    return cl

def _send_dm(cl, to_username:str, message:str)->bool:
    try:
        # Minimizar ruido: envolvemos en try sin mostrar trazas del lib
        uid = cl.user_id_from_username(to_username)
        cl.direct_send(message, [uid])
        return True
    except Exception as e:
        # Algunos entornos tienen warning 'update_headers', igual suele enviar.
        return False

def menu_send_rotating():
    banner()
    alias = ask("Alias/grupo: ").strip() or "default"
    listname = ask("Nombre de la lista (text/leads/<nombre>.txt): ").strip()
    per_acc = ask_int("¿Cuántos mensajes por cuenta? ", 1, 1)
    concurr = int((input("Cuentas en simultáneo (default=1): ").strip() or "1"))
    dmin = ask_int("Delay mínimo (seg): ", 0, 45)
    dmax = ask_int("Delay máximo (seg): ", dmin, 55)
    print("Escribí plantillas (una por línea). Línea vacía para terminar:")
    templates=[]
    while True:
        s=ask("")
        if not s: break
        templates.append(s)
    if not templates: templates=["hola!"]

    all_acc=[a for a in list_all() if a.get("alias")==alias and a.get("active")]
    if not all_acc:
        warn("No hay cuentas activas en ese alias."); press_enter(); return

    users=[u for u in load_list(listname) if not already_contacted(u)]
    if not users:
        warn("No hay leads (o todos ya fueron contactados)."); press_enter(); return

    # Round-robin: por cuenta, hasta per_acc cada una
    sent_count={a["username"]:0 for a in all_acc}
    stop=False
    ui_idx=0
    while True:
        idle=True
        for a in all_acc:
            if sent_count[a["username"]]>=per_acc: continue
            if not users: stop=True; break
            u=users.pop(0)
            msg=random.choice(templates)
            idle=False
            banner()
            print("== Actividad ==")
            print(f"Cuenta: {a['username']}  {em('🟢 conectada')}")
            print(f"Lead: @{u}")
            print(f"Plantilla: {msg}")
            print(f"Delay próximo: {dmin}-{dmax}s")
            print("\n(Precione Q para cancelar el proceso)\n")
            try:
                cl=_client_for(a["username"])
                okflag=_send_dm(cl, u, msg)
            except Exception as e:
                okflag=False
            if okflag:
                print(f"{em('✅')} ENVIADO: [@{a['username']}] → @{u}")
                log_sent(a["username"], u, True, "")
                sent_count[a["username"]]+=1
            else:
                print(f"{em('⛔')} ERROR: [@{a['username']}] → @{u}")
                log_sent(a["username"], u, False, "envío falló")

            # allow cancel
            t=random.randint(dmin, dmax)
            for i in range(t):
                if _q_pressed():
                    stop=True; break
                time.sleep(1)
            if stop: break
        if stop: break
        if idle: break

    print("\n== Resumen ==")
    total_ok=sum(sent_count.values())
    print(f"OK: {total_ok}")
    for k,v in sent_count.items():
        print(f" - {k}: {v} enviados")
    press_enter()