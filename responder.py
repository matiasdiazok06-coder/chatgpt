# responder.py
# -*- coding: utf-8 -*-
import os, time, random, json, logging
from pathlib import Path
from utils import banner, ask, ask_int, press_enter, warn, em
from accounts import list_all
from storage import get_auto_state, save_auto_state
from config import SETTINGS
from runtime import STOP_EVENT, ensure_logging, request_stop, reset_stop_event, start_q_listener


def _client_for(username: str):
    from instagrapi import Client

    cl = Client()
    ses = Path(__file__).resolve().parent / ".sessions" / f"{username}.json"
    if not ses.exists():
        raise RuntimeError(f"No hay sesión para {username}.")
    cl.load_settings(str(ses))
    try:
        cl.get_timeline_feed()
    except Exception:
        pass
    return cl


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
    ensure_logging()
    reset_stop_event()
    banner()
    alias = ask("Alias/usuario con sesión guardada (o 'ALL' para todas activas): ").strip() or "ALL"
    default_api_key = os.environ.get("OPENAI_API_KEY", "")
    api_input = ask("Pegá tu OPENAI_API_KEY (Enter para usar la de entorno): ").strip()
    api_key = api_input or default_api_key
    if not api_key:
        warn("Necesitás definir OPENAI_API_KEY para enviar respuestas automáticas.")
        press_enter()
        return
    if not api_input and default_api_key:
        logger.info("Usando OPENAI_API_KEY obtenida desde el entorno.")
    system_prompt = ask("Instrucciones del bot (system prompt): ").strip() or "Respondé cordial, breve y como humano."
    delay_default = max(1, SETTINGS.autoresponder_delay)
    delay = ask_int("Delay entre chequeos (seg, ej 10): ", 1, delay_default)

    state = get_auto_state()  # {account: {thread_id: last_msg_id}}

    targets = []
    if alias.upper() == "ALL":
        targets = [a["username"] for a in list_all() if a.get("active")]
    else:
        targets = [alias]

    if not targets:
        warn("No se encontraron cuentas activas para iniciar el auto-responder.")
        press_enter()
        return

    active_targets = []
    for user in targets:
        try:
            _client_for(user)
            active_targets.append(user)
        except Exception as e:
            warn(str(e))

    if not active_targets:
        warn("Ninguna cuenta tiene sesión válida.")
        press_enter()
        return

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

