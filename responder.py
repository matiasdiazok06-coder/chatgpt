# responder.py
# -*- coding: utf-8 -*-
import os, time, random, json
from pathlib import Path
from utils import banner, ask, ask_int, press_enter, title, ok, warn, err, em
from accounts import list_all
from storage import get_auto_state, save_auto_state

def _client_for(username:str):
    from instagrapi import Client
    cl=Client()
    ses=Path(__file__).resolve().parent/".sessions"/f"{username}.json"
    if not ses.exists():
        raise RuntimeError(f"No hay sesión para {username}.")
    cl.load_settings(str(ses))
    try: cl.get_timeline_feed()
    except Exception: pass
    return cl

def _gen_response(api_key:str, system_prompt:str, convo_text:str)->str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        msg = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"user","content":convo_text[:6000]}
            ],
            temperature=0.6,
            max_tokens=180
        )
        return msg.choices[0].message.content.strip()
    except Exception as e:
        return "Gracias por tu mensaje 🙌 ¿Cómo te puedo ayudar?"

def menu_autoresponder():
    banner()
    alias = ask("Alias/usuario con sesión guardada (o 'ALL' para todas activas): ").strip() or "ALL"
    api_key = ask("Pegá tu OPENAI_API_KEY: ").strip()
    system_prompt = ask("Instrucciones del bot (system prompt): ").strip() or "Respondé cordial, breve y como humano."
    delay = ask_int("Delay entre chequeos (seg, ej 10): ", 1, 10)

    state=get_auto_state()  # {account: {thread_id: last_msg_id}}

    targets = []
    if alias.upper()=="ALL":
        targets=[a["username"] for a in list_all() if a.get("active")]
    else:
        targets=[alias]

    for user in targets:
        try:
            cl=_client_for(user)
        except Exception as e:
            warn(str(e)); continue

    print(em("🟢")+" Auto-responder activo. CTRL+C para detener.")
    try:
        while True:
            for user in targets:
                try:
                    cl=_client_for(user)
                    inbox = cl.direct_threads(selected_filter="unread", amount=10)
                    if not inbox:
                        continue
                    state.setdefault(user, {})
                    for th in inbox:
                        tid=th.id
                        # Recopilar últimos mensajes
                        messages=cl.direct_messages(th.id, amount=10)
                        if not messages: continue
                        last = messages[0]
                        if last.user_id == cl.user_id:  # último es mío, no responder
                            continue
                        # evitar duplicados
                        last_seen = state[user].get(tid)
                        if last_seen == last.id:
                            continue
                        # Armar contexto
                        convo = "\n".join([
                            f"{'YO' if m.user_id==cl.user_id else 'EL'}: {m.text or ''}"
                            for m in reversed(messages)
                        ])
                        reply=_gen_response(api_key, system_prompt, convo)
                        cl.direct_send(reply, [last.user_id])
                        state[user][tid]=last.id
                        save_auto_state(state)
                        print(f"[@{user}] respondió en hilo {tid}")
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    pass
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\nDetenido por usuario.")
        press_enter()
