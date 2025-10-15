# ig.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import random
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Optional

from accounts import list_all, mark_connected, prompt_login
from config import SETTINGS
from leads import load_list
from runtime import STOP_EVENT, ensure_logging, request_stop, reset_stop_event, start_q_listener
from storage import already_contacted, log_sent, sent_totals
from utils import ask, ask_int, banner, press_enter, warn
from session_store import has_session, load_into


def _client_for(username: str):
    from instagrapi import Client

    cl = Client()
    try:
        load_into(cl, username)
    except FileNotFoundError as exc:
        mark_connected(username, False)
        raise RuntimeError(f"No hay sesión guardada para {username}. Usá opción 1.") from exc
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

_LIVE_COUNTS = {"base_ok": 0, "base_fail": 0, "run_ok": 0, "run_fail": 0}
_LIVE_LOCK = threading.Lock()


def _reset_live_counters(reset_run: bool = True) -> None:
    base_ok, base_fail = sent_totals()
    with _LIVE_LOCK:
        _LIVE_COUNTS["base_ok"] = base_ok
        _LIVE_COUNTS["base_fail"] = base_fail
        if reset_run:
            _LIVE_COUNTS["run_ok"] = 0
            _LIVE_COUNTS["run_fail"] = 0


def get_message_totals() -> tuple[int, int]:
    with _LIVE_LOCK:
        ok_total = _LIVE_COUNTS["base_ok"] + _LIVE_COUNTS["run_ok"]
        error_total = _LIVE_COUNTS["base_fail"] + _LIVE_COUNTS["run_fail"]
    return ok_total, error_total


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
                with _LIVE_LOCK:
                    _LIVE_COUNTS["run_ok"] += 1
                    ok_total = _LIVE_COUNTS["base_ok"] + _LIVE_COUNTS["run_ok"]
                    err_total = _LIVE_COUNTS["base_fail"] + _LIVE_COUNTS["run_fail"]
                summary = (
                    f"Mensaje enviado a @{lead} (cuenta @{username}) | "
                    f"Totales OK: {ok_total}, errores: {err_total}"
                )
                logger.info(summary)
                if SETTINGS.quiet:
                    print(summary)
            else:
                log_sent(username, lead, False, "envío falló")
                failed[username] += 1
                with _LIVE_LOCK:
                    _LIVE_COUNTS["run_fail"] += 1
                    ok_total = _LIVE_COUNTS["base_ok"] + _LIVE_COUNTS["run_ok"]
                    err_total = _LIVE_COUNTS["base_fail"] + _LIVE_COUNTS["run_fail"]
                summary = (
                    f"Error al enviar a @{lead} (cuenta @{username}) | "
                    f"Totales OK: {ok_total}, errores: {err_total}"
                )
                logger.warning(summary)

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


def menu_send_rotating(concurrency_override: Optional[int] = None) -> None:
    ensure_logging(
        quiet=SETTINGS.quiet,
        log_dir=SETTINGS.log_dir,
        log_file=SETTINGS.log_file,
    )
    reset_stop_event()
    banner()
    _reset_live_counters()

    settings = SETTINGS

    alias = ask("Alias/grupo: ").strip() or "default"
    listname = ask("Nombre de la lista (text/leads/<nombre>.txt): ").strip()

    per_acc_input = ask_int("¿Cuántos mensajes por cuenta? ", 1, settings.max_per_account)
    per_acc = _clamp(per_acc_input, 1, settings.max_per_account)
    if per_acc < per_acc_input:
        warn(f"Límite por cuenta ajustado a {per_acc} (MAX_PER_ACCOUNT)")

    if concurrency_override is not None:
        concurr_input = max(1, concurrency_override)
        print(f"Concurrencia forzada: {concurr_input}")
    else:
        concurr_input = ask_int("Cuentas en simultáneo: ", 1, settings.max_concurrency)
    concurr = _clamp(concurr_input, 1, settings.max_concurrency)
    if concurr < concurr_input:
        warn(f"Concurrencia limitada a {concurr} (MAX_CONCURRENCY)")
    elif concurrency_override is not None:
        print(f"Concurrencia efectiva: {concurr}")

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

    verified: list[Dict] = []
    needing_login: list[tuple[Dict, str]] = []
    for account in all_acc:
        username = account["username"]
        if not has_session(username):
            needing_login.append((account, "sin sesión guardada"))
            continue
        if not _ensure_session(username):
            needing_login.append((account, "sesión expirada"))
            continue
        verified.append(account)

    if needing_login:
        print("\nLas siguientes cuentas necesitan volver a iniciar sesión:")
        for account, reason in needing_login:
            print(f" - @{account['username']}: {reason}")
        if ask("¿Iniciar sesión ahora? (s/N): ").strip().lower() == "s":
            for account, _ in needing_login:
                if prompt_login(account["username"]):
                    if _ensure_session(account["username"]):
                        verified.append(account)
        else:
            warn("Se omitieron las cuentas sin sesión válida.")

    all_acc = verified
    if not all_acc:
        warn("No hay cuentas con sesión válida para enviar mensajes.")
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
                logger.debug(
                    "Programado envío desde @%s hacia @%s (restan %d)",
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

        _reset_live_counters()

    print("\n== Resumen ==")
    total_ok = sum(success.values())
    print(f"OK: {total_ok}")
    for account in all_acc:
        user = account["username"]
        print(f" - {user}: {success[user]} enviados, {failed[user]} errores")
    if STOP_EVENT.is_set():
        logger.info("Proceso detenido (%s).", "stop_event activo")
    press_enter()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enviar mensajes rotando cuentas")
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Cantidad de cuentas enviando en simultáneo",
    )
    args = parser.parse_args()
    menu_send_rotating(concurrency_override=args.concurrency)
