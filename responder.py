# responder.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os
import time
from utils import banner, ask, ask_int, press_enter, warn, em
from accounts import list_all, mark_connected, prompt_login
from storage import get_auto_state, save_auto_state
from config import SETTINGS
from runtime import STOP_EVENT, ensure_logging, request_stop, reset_stop_event, start_q_listener
from session_store import has_session, load_into


def _client_for(username: str):
    from instagrapi import Client

    cl = Client()
    try:
        load_into(cl, username)
    except FileNotFoundError as exc:
        mark_connected(username, False)
        raise RuntimeError(f"No hay sesión para {username}.") from exc
    try:
        cl.get_timeline_feed()
        mark_connected(username, True)
    except Exception as exc:
        mark_connected(username, False)
        raise RuntimeError(
            f"La sesión guardada para {username} no es válida. Iniciá sesión nuevamente."
        ) from exc
    return cl


def _ensure_session(username: str) -> bool:
    try:
        _client_for(username)
        return True
    except Exception:
        return False


logger = logging.getLogger(__name__)


def _gen_response(api_key: str, system_prompt: str, convo_text: str) -> str:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        msg = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": convo_text[:6000]},
            ],
            temperature=0.6,
            max_output_tokens=180,
        )
        return (msg.output_text or "").strip() or "Gracias por tu mensaje 🙌 ¿Cómo te puedo ayudar?"
    except Exception as e:
        logger.debug("Fallo al generar respuesta con OpenAI: %s", e, exc_info=False)
        return "Gracias por tu mensaje 🙌 ¿Cómo te puedo ayudar?"


def menu_autoresponder():
    ensure_logging(
        quiet=SETTINGS.quiet,
        log_dir=SETTINGS.log_dir,
        log_file=SETTINGS.log_file,
    )
    reset_stop_event()
    banner()
    alias = ask("Alias/usuario con sesión guardada (o 'ALL' para todas activas): ").strip() or "ALL"
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        logger.info("Usando OPENAI_API_KEY desde la configuración cargada.")
    else:
        api_key = ask("Pegá tu OPENAI_API_KEY: ").strip()
        if not api_key:
            warn("Necesitás definir OPENAI_API_KEY para enviar respuestas automáticas.")
            press_enter()
            return
    system_prompt = ask("Instrucciones del bot (system prompt): ").strip() or "Respondé cordial, breve y como humano."
    delay_default = max(1, SETTINGS.autoresponder_delay)
    delay = ask_int("Delay entre chequeos (seg, ej 10): ", 1, delay_default)

    state = get_auto_state()  # {account: {thread_id: last_msg_id}}

    accounts_data = list_all()
    alias_key = alias.lstrip("@")
    alias_lower = alias_key.lower()

    targets: list[str]
    if alias.upper() == "ALL":
        targets = [a["username"] for a in accounts_data if a.get("active")]
    else:
        alias_matches = [
            a for a in accounts_data if a.get("alias", "").lower() == alias_lower and a.get("active")
        ]
        if alias_matches:
            targets = [a["username"] for a in alias_matches]
        else:
            username_matches = [
                a for a in accounts_data if a.get("username", "").lower() == alias_lower and a.get("active")
            ]
            if username_matches:
                targets = [username_matches[0]["username"]]
            else:
                targets = [alias_key]

    deduped: list[str] = []
    seen = set()
    for user in targets:
        norm = user.lstrip("@")
        if norm not in seen:
            seen.add(norm)
            deduped.append(norm)
    targets = deduped

    if not targets:
        warn("No se encontraron cuentas activas para iniciar el auto-responder.")
        press_enter()
        return

    verified: list[str] = []
    needing_login: list[tuple[str, str]] = []
    for user in targets:
        if not has_session(user):
            needing_login.append((user, "sin sesión guardada"))
            continue
        if not _ensure_session(user):
            needing_login.append((user, "sesión expirada"))
            continue
        verified.append(user)

    if needing_login:
        print("\nLas siguientes cuentas necesitan volver a iniciar sesión:")
        for user, reason in needing_login:
            print(f" - @{user}: {reason}")
        if ask("¿Iniciar sesión ahora? (s/N): ").strip().lower() == "s":
            for user, _ in needing_login:
                if prompt_login(user) and _ensure_session(user):
                    if user not in verified:
                        verified.append(user)
        else:
            warn("Se omitieron las cuentas sin sesión válida.")

    if not verified:
        warn("Ninguna cuenta tiene sesión válida.")
        press_enter()
        return

    active_targets = verified

    listener = start_q_listener("Presioná Q para detener el auto-responder.", logger)
    logger.info("Auto-responder activo para %d cuentas. Delay: %ss", len(active_targets), delay)
    print(em("🟢") + " Auto-responder activo. CTRL+C o Q para detener.")
    try:
        while not STOP_EVENT.is_set():
            for user in active_targets:
                if STOP_EVENT.is_set():
                    break
                try:
                    cl = _client_for(user)
                    inbox = cl.direct_threads(selected_filter="unread", amount=10)
                    if not inbox:
                        continue
                    state.setdefault(user, {})
                    for th in inbox:
                        tid = th.id
                        # Recopilar últimos mensajes
                        messages = cl.direct_messages(th.id, amount=10)
                        if not messages:
                            continue
                        last = messages[0]
                        if last.user_id == cl.user_id:  # último es mío, no responder
                            continue
                        # evitar duplicados
                        last_seen = state[user].get(tid)
                        if last_seen == last.id:
                            continue
                        # Armar contexto
                        convo = "\n".join([
                            f"{'YO' if m.user_id == cl.user_id else 'EL'}: {m.text or ''}"
                            for m in reversed(messages)
                        ])
                        reply = _gen_response(api_key, system_prompt, convo)
                        cl.direct_send(reply, [last.user_id])
                        state[user][tid] = last.id
                        save_auto_state(state)
                        logger.info("Respuesta enviada por @%s en hilo %s", user, tid)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.debug("Error en auto-responder para @%s: %s", user, e, exc_info=False)
            slept = 0
            while slept < delay and not STOP_EVENT.is_set():
                time.sleep(1)
                slept += 1
    except KeyboardInterrupt:
        request_stop("interrupción con Ctrl+C")
    finally:
        request_stop("auto-responder detenido")
        if listener:
            listener.join(timeout=0.1)
        print("\nDetenido por usuario.")
        press_enter()

