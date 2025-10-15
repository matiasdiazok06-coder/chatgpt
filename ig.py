# ig.py
# -*- coding: utf-8 -*-
import logging
import random
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict

from accounts import list_all
from config import SETTINGS
from leads import load_list
from runtime import STOP_EVENT, ensure_logging, request_stop, reset_stop_event, start_q_listener
from storage import already_contacted, log_sent
from utils import ask, ask_int, banner, em, press_enter, warn


def _client_for(username: str):
    from instagrapi import Client

    cl = Client()
    ses = Path(__file__).resolve().parent / ".sessions" / f"{username}.json"
    if ses.exists():
        cl.load_settings(str(ses))
        try:
            cl.get_timeline_feed()  # ping
        except Exception:
            pass
    else:
        raise RuntimeError(f"No hay sesión guardada para {username}. Usá opción 1.")
    return cl


logger = logging.getLogger(__name__)


def _send_dm(cl, to_username: str, message: str) -> bool:
    try:
        # Minimizar ruido: envolvemos en try sin mostrar trazas del lib
        uid = cl.user_id_from_username(to_username)
        cl.direct_send(message, [uid])
        return True
    except Exception as e:
        # Algunos entornos tienen warning 'update_headers', igual suele enviar.
        logger.debug("Error enviando DM: %s", e, exc_info=False)
        return False


def _send_job(
    account: Dict,
    lead: str,
    message: str,
    delay_min: int,
    delay_max: int,
    semaphore: threading.Semaphore,
    success: Dict[str, int],
    failed: Dict[str, int],
    lock: threading.Lock,
) -> None:
    username = account["username"]
    try:
        if STOP_EVENT.is_set():
            return
        try:
            cl = _client_for(username)
            okflag = _send_dm(cl, lead, message)
        except Exception as exc:
            logger.debug("Fallo inesperado con @%s → @%s: %s", username, lead, exc, exc_info=False)
            okflag = False

        with lock:
            if okflag:
                log_sent(username, lead, True, "")
                success[username] += 1
                logger.info("%s ENVIADO: [@%s] → @%s", em("✅"), username, lead)
            else:
                log_sent(username, lead, False, "envío falló")
                failed[username] += 1
                logger.warning("%s ERROR: [@%s] → @%s", em("⛔"), username, lead)

        wait_time = delay_min if delay_max <= delay_min else random.randint(delay_min, delay_max)
        logger.debug("Esperando %ss antes del próximo envío de @%s", wait_time, username)
        slept = 0
        while slept < wait_time and not STOP_EVENT.is_set():
            time.sleep(1)
            slept += 1
    finally:
        semaphore.release()


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _any_capacity(remaining: Dict[str, int]) -> bool:
    return any(v > 0 for v in remaining.values())


def menu_send_rotating() -> None:
    ensure_logging()
    reset_stop_event()
    banner()

    settings = SETTINGS

    alias = ask("Alias/grupo: ").strip() or "default"
    listname = ask("Nombre de la lista (text/leads/<nombre>.txt): ").strip()

    per_acc_input = ask_int("¿Cuántos mensajes por cuenta? ", 1, settings.max_per_account)
    per_acc = _clamp(per_acc_input, 1, settings.max_per_account)
    if per_acc < per_acc_input:
        warn(f"Límite por cuenta ajustado a {per_acc} (MAX_PER_ACCOUNT)")

    concurr_input = ask_int("Cuentas en simultáneo: ", 1, settings.max_concurrent)
    concurr = _clamp(concurr_input, 1, settings.max_concurrent)
    if concurr < concurr_input:
        warn(f"Concurrencia limitada a {concurr} (MAX_CONCURRENT)")

    dmin_input = ask_int("Delay mínimo (seg): ", 0, settings.delay_min)
    dmax_default = max(settings.delay_max, dmin_input)
    dmax_input = ask_int("Delay máximo (seg): ", dmin_input, dmax_default)
    delay_min = max(settings.delay_min, dmin_input)
    delay_max = _clamp(dmax_input, delay_min, settings.delay_max)
    if delay_min != dmin_input:
        warn(f"Delay mínimo ajustado a {delay_min}s")
    if delay_max != dmax_input:
        warn(f"Delay máximo ajustado a {delay_max}s")

    print("Escribí plantillas (una por línea). Línea vacía para terminar:")
    templates: list[str] = []
    while True:
        s = ask("")
        if not s:
            break
        templates.append(s)
    if not templates:
        templates = ["hola!"]

    all_acc = [a for a in list_all() if a.get("alias") == alias and a.get("active")]
    if not all_acc:
        warn("No hay cuentas activas en ese alias.")
        press_enter()
        return

    users = deque([u for u in load_list(listname) if not already_contacted(u)])
    if not users:
        warn("No hay leads (o todos ya fueron contactados).")
        press_enter()
        return

    remaining = {a["username"]: per_acc for a in all_acc}
    success = defaultdict(int)
    failed = defaultdict(int)
    lock = threading.Lock()
    semaphore = threading.Semaphore(concurr)
    listener = start_q_listener("Presioná Q para detener la campaña.", logger)
    threads: list[threading.Thread] = []

    logger.info(
        "Iniciando campaña con %d cuentas activas y %d leads pendientes. Límite/cuenta: %d, concurrencia: %d, delay: %s-%ss",
        len(all_acc), len(users), per_acc, concurr, delay_min, delay_max,
    )

    try:
        while users and _any_capacity(remaining) and not STOP_EVENT.is_set():
            for account in all_acc:
                if STOP_EVENT.is_set():
                    break
                username = account["username"]
                if remaining[username] <= 0:
                    continue
                if not users:
                    break
                lead = users.popleft()
                message = random.choice(templates)

                acquired = semaphore.acquire(timeout=0.5)
                if not acquired:
                    users.appendleft(lead)
                    continue

                remaining[username] -= 1
                logger.info(
                    "Programado: [@%s] → @%s (quedan %d envíos para la cuenta)",
                    username,
                    lead,
                    remaining[username],
                )
                thread = threading.Thread(
                    target=_send_job,
                    args=(account, lead, message, delay_min, delay_max, semaphore, success, failed, lock),
                    daemon=True,
                )
                thread.start()
                threads.append(thread)

                if not users or STOP_EVENT.is_set():
                    break
            time.sleep(0.1)
    except KeyboardInterrupt:
        request_stop("interrupción con Ctrl+C")
    finally:
        if not users:
            request_stop("no quedan leads por procesar")
        elif not _any_capacity(remaining):
            request_stop("se alcanzó el límite de envíos por cuenta")

        for t in threads:
            t.join()
        if listener:
            listener.join(timeout=0.1)

    print("\n== Resumen ==")
    total_ok = sum(success.values())
    print(f"OK: {total_ok}")
    for account in all_acc:
        user = account["username"]
        print(f" - {user}: {success[user]} enviados, {failed[user]} errores")
    if STOP_EVENT.is_set():
        logger.info("Proceso detenido (%s).", "stop_event activo")
    press_enter()

