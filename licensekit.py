# licensekit.py
# -*- coding: utf-8 -*-
"""Herramientas de gestión y entrega de licencias."""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from config import SETTINGS, read_env_local, refresh_settings, update_env_local
from supabase_migrations import ensure_licenses_table as run_ensure_licenses_table
from ui import Fore, banner, full_line, style_text
from utils import ask, ask_int, ok, press_enter, warn

_TABLE = "licenses"
_DATE_FMT = "%Y-%m-%d"
_STATUS_ACTIVE = "active"
_STATUS_EXPIRED = "expired"
_STATUS_PAUSED = "paused"
_STATUS_REVOKED = "revoked"
_TABLE_SQL = textwrap.dedent(
    """
    create table if not exists public.licenses (
        id uuid primary key default gen_random_uuid(),
        client_name text not null,
        license_key text not null unique,
        expires_at timestamptz not null,
        status text not null default 'active',
        created_at timestamptz not null default now()
    );
    """
).strip()
_PAYLOAD_PATH = Path(__file__).resolve().parent / "storage" / "license_payload.json"


def _supabase_credentials() -> Tuple[str, str]:
    env_local = read_env_local()
    url = (env_local.get("SUPABASE_URL") or SETTINGS.supabase_url or "").strip()
    key = (env_local.get("SUPABASE_KEY") or SETTINGS.supabase_key or "").strip()
    return url, key


def _missing_table_text() -> str:
    return (
        "La tabla 'licenses' no existe en Supabase.\n"
        "Creala ejecutando en el editor SQL (schema public):\n"
        f"{_TABLE_SQL}"
    )


def _show_missing_table_help() -> None:
    message = _missing_table_text()
    warn(message.splitlines()[0])
    print(full_line(color=Fore.BLUE))
    for line in message.splitlines()[1:]:
        print(line)
    print(full_line(color=Fore.BLUE))
    press_enter()


def _load_local_payload() -> Dict[str, Any]:
    if not _PAYLOAD_PATH.exists():
        return {}
    try:
        return json.loads(_PAYLOAD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ensure_supabase(*, interactive: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    url, key = _supabase_credentials()
    if url and key:
        return True, url, key

    if not interactive:
        return False, url or None, key or None

    warn("Faltan SUPABASE_URL y/o SUPABASE_KEY.")
    confirm = ask("¿Querés configurarlos ahora? (s/N): ").strip().lower()
    if confirm != "s":
        warn("Operación cancelada.")
        press_enter()
        return False, None, None

    url = ask("SUPABASE_URL: ").strip()
    key = ask("SUPABASE_KEY: ").strip()
    if not url or not key:
        warn("Se requieren ambos valores.")
        press_enter()
        return False, None, None

    update_env_local({"SUPABASE_URL": url, "SUPABASE_KEY": key})
    refresh_settings()
    ok("Credenciales guardadas en .env.local.")
    press_enter()
    return True, url, key


def _is_missing_table(error: Optional[str], status: int) -> bool:
    if status == 404:
        return True
    if error and "PGRST208" in error:
        return True
    return False


def _request(
    method: str,
    endpoint: str,
    *,
    json_payload: Any | None = None,
    url_override: str | None = None,
    key_override: str | None = None,
) -> Tuple[Any | None, Optional[str], int]:
    url, key = _supabase_credentials()
    if url_override is not None:
        url = url_override
    if key_override is not None:
        key = key_override
    if not url or not key:
        return None, "Faltan credenciales de Supabase."

    base = url.rstrip("/") + "/rest/v1/"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if json_payload is not None:
        headers["Content-Type"] = "application/json"
        headers.setdefault("Prefer", "return=representation")

    try:
        response = requests.request(
            method.upper(),
            base + endpoint.lstrip("/"),
            headers=headers,
            json=json_payload,
            timeout=15,
        )
    except requests.RequestException as exc:  # pragma: no cover - red de Supabase
        return None, str(exc), 0

    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:  # pragma: no cover - fallback legible
            detail = response.text
        return None, f"{response.status_code}: {detail}", response.status_code

    if not response.text:
        return None, None, response.status_code

    try:
        return response.json(), None, response.status_code
    except ValueError:
        return response.text, None, response.status_code


def _ensure_table_ready(url: str, key: str, *, interactive: bool = True) -> bool:
    _, error, status = _request(
        "get",
        f"{_TABLE}?select=license_key&limit=1",
        url_override=url,
        key_override=key,
    )
    if _is_missing_table(error, status):
        if interactive:
            warn("La tabla de licencias no existe en Supabase.")
            choice = ask("¿Crear tabla automáticamente? (s/N): ").strip().lower()
            if choice == "s":
                created, message = run_ensure_licenses_table(url, key)
                if created:
                    ok("Tabla 'licenses' creada en Supabase.")
                    _, error, status = _request(
                        "get",
                        f"{_TABLE}?select=license_key&limit=1",
                        url_override=url,
                        key_override=key,
                    )
                    if not error:
                        return True
                else:
                    warn(message)
                    press_enter()
            else:
                _show_missing_table_help()
            return False
        _show_missing_table_help()
        return False
    if error:
        warn(f"No se pudo comprobar la tabla de licencias: {error}")
        press_enter()
        return False
    return True


def _parse_iso(value: str | None) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_expired(record: Dict[str, Any]) -> bool:
    expires = _parse_iso(record.get("expires_at"))
    if not expires:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    return expires < now


def _status_label(record: Dict[str, Any]) -> Tuple[str, str]:
    status = str(record.get("status", "")).lower()
    if status == _STATUS_REVOKED:
        return "Revocada", Fore.RED
    if status == _STATUS_PAUSED:
        return "Pausada", Fore.YELLOW
    if status == _STATUS_EXPIRED or _is_expired(record):
        return "Vencida", Fore.YELLOW
    return "Activa", Fore.GREEN


def _format_date(value: str | None) -> str:
    parsed = _parse_iso(value)
    if not parsed:
        return "-"
    return parsed.strftime(_DATE_FMT)


def _days_left(record: Dict[str, Any]) -> str:
    expires = _parse_iso(record.get("expires_at"))
    if not expires:
        return "-"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    delta = expires - now
    if delta.total_seconds() <= 0:
        return "0"
    return str(int(delta.total_seconds() // 86400))


def _render_table(records: Iterable[Dict[str, Any]]) -> None:
    rows: List[Tuple[str, str, str, str, str, str, str]] = []
    for idx, rec in enumerate(records, start=1):
        status, color = _status_label(rec)
        status_txt = style_text(status, color=color, bold=True)
        rows.append(
            (
                str(idx),
                rec.get("client_name", "-"),
                rec.get("license_key", "-"),
                _format_date(rec.get("created_at")),
                _format_date(rec.get("expires_at")),
                _days_left(rec),
                status_txt,
            )
        )

    if not rows:
        warn("No hay licencias registradas.")
        return

    headers = ("#", "Cliente", "Key", "Creada", "Vence", "Días", "Estado")
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    line = full_line(color=Fore.BLUE)
    print(line)
    header_row = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(style_text(header_row, color=Fore.CYAN, bold=True))
    print(line)
    for row in rows:
        body_row = "  ".join(row[i].ljust(widths[i]) for i in range(len(headers)))
        print(body_row)
    print(line)


def _fetch_licenses() -> List[Dict[str, Any]]:
    data, error, status = _request("get", f"{_TABLE}?select=*")
    if _is_missing_table(error, status):
        _show_missing_table_help()
        return []
    if error:
        warn(f"No se pudieron obtener licencias: {error}")
        return []
    if not isinstance(data, list):
        return []
    return data


def _select_license(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not records:
        warn("No hay licencias para seleccionar.")
        press_enter()
        return None
    _render_table(records)
    choice = ask("Seleccioná número de licencia (vacío para cancelar): ").strip()
    if not choice:
        warn("Operación cancelada.")
        press_enter()
        return None
    try:
        idx = int(choice)
    except ValueError:
        warn("Número inválido.")
        press_enter()
        return None
    if not 1 <= idx <= len(records):
        warn("Fuera de rango.")
        press_enter()
        return None
    return records[idx - 1]


def _update_license(license_key: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoint = f"{_TABLE}?license_key=eq.{license_key}"
    data, error, status = _request("patch", endpoint, json_payload=payload)
    if _is_missing_table(error, status):
        _show_missing_table_help()
        return None
    if error:
        warn(f"No se pudo actualizar la licencia: {error}")
        press_enter()
        return None
    if isinstance(data, list) and data:
        ok("Licencia actualizada.")
        press_enter()
        return data[0]
    ok("Licencia actualizada.")
    press_enter()
    return None


def _extend_license(record: Dict[str, Any]) -> None:
    extra_days = ask_int("Cantidad de días a extender (>=1): ", min_value=1, default=30)
    current_exp = _parse_iso(record.get("expires_at")) or dt.datetime.now(dt.timezone.utc)
    new_exp = current_exp + dt.timedelta(days=extra_days)
    payload = {
        "expires_at": new_exp.astimezone(dt.timezone.utc).isoformat(),
        "status": _STATUS_ACTIVE,
    }
    _update_license(record["license_key"], payload)


def _update_status(record: Dict[str, Any], status: str, verb: str) -> None:
    confirm = ask(f"Confirmás {verb} la licencia? (s/N): ").strip().lower()
    if confirm != "s":
        warn("Sin cambios.")
        press_enter()
        return
    payload = {"status": status}
    _update_license(record["license_key"], payload)


def _delete_license(record: Dict[str, Any]) -> None:
    confirm = ask("Confirmás eliminar la licencia? (s/N): ").strip().lower()
    if confirm != "s":
        warn("Sin cambios.")
        press_enter()
        return
    endpoint = f"{_TABLE}?license_key=eq.{record['license_key']}"
    _, error, status = _request("delete", endpoint)
    if _is_missing_table(error, status):
        _show_missing_table_help()
        return
    if error:
        warn(f"No se pudo eliminar la licencia: {error}")
    else:
        ok("Licencia eliminada.")
    press_enter()


def _license_actions_loop(license_key: str) -> None:
    while True:
        record = _fetch_single(license_key)
        if not record:
            warn("No se encontró la licencia seleccionada.")
            press_enter()
            return
        banner()
        print(full_line())
        print(style_text("Gestión de licencia", color=Fore.CYAN, bold=True))
        print(full_line())
        _render_table([record])
        print("1) Extender vigencia")
        print("2) Pausar licencia")
        print("3) Activar licencia")
        print("4) Revocar licencia")
        print("5) Eliminar licencia")
        print("6) Volver")
        choice = ask("Opción: ").strip()
        status = str(record.get("status", "")).lower()
        if choice == "1":
            _extend_license(record)
        elif choice == "2":
            if status == _STATUS_PAUSED:
                warn("La licencia ya está en pausa.")
                press_enter()
            else:
                _update_status(record, _STATUS_PAUSED, "pausar")
        elif choice == "3":
            if status == _STATUS_ACTIVE:
                warn("La licencia ya está activa.")
                press_enter()
            else:
                _update_status(record, _STATUS_ACTIVE, "activar")
        elif choice == "4":
            _update_status(record, _STATUS_REVOKED, "revocar")
        elif choice == "5":
            _delete_license(record)
            break
        elif choice == "6":
            break
        else:
            warn("Opción inválida.")
            press_enter()


def _fetch_single(license_key: str) -> Optional[Dict[str, Any]]:
    endpoint = f"{_TABLE}?license_key=eq.{license_key}&select=*"
    data, error, status = _request("get", endpoint)
    if _is_missing_table(error, status):
        _show_missing_table_help()
        return None
    if error or not isinstance(data, list):
        return None
    return data[0] if data else None


def _generate_key() -> str:
    return secrets.token_urlsafe(18)


def _package_license(record: Dict[str, Any], url: str, key: str) -> Tuple[bool, str]:
    try:
        from tools.build_executable import build_for_license
    except Exception as exc:  # pragma: no cover - entorno sin módulo
        return False, f"No se pudo importar el generador de ejecutables: {exc}"

    success, _output, message = build_for_license(record, url, key)
    if success:
        return True, message
    return False, message


def _build_executable(record: Dict[str, Any], url: str, key: str) -> None:
    choice = ask("¿Generar build para esta licencia? (s/N): ").strip().lower()
    if choice != "s":
        warn("Operación cancelada.")
        press_enter()
        return

    success, message = _package_license(record, url, key)
    if success:
        ok(message)
    else:
        warn(message)
    press_enter()


def _create_license(url: str, key: str) -> None:
    banner()
    print(full_line())
    print(style_text("Nueva licencia", color=Fore.CYAN, bold=True))
    print(full_line())
    client = ask("Nombre del cliente: ").strip()
    if not client:
        warn("Se requiere un nombre de cliente.")
        press_enter()
        return
    duration = ask_int("Duración en días (mínimo 30): ", min_value=30, default=30)
    issued = dt.datetime.now(dt.timezone.utc)
    expires = issued + dt.timedelta(days=duration)
    payload = {
        "license_key": _generate_key(),
        "client_name": client,
        "created_at": issued.astimezone(dt.timezone.utc).isoformat(),
        "expires_at": expires.astimezone(dt.timezone.utc).isoformat(),
        "status": _STATUS_ACTIVE,
    }
    data, error, status = _request("post", _TABLE, json_payload=[payload])
    if _is_missing_table(error, status):
        _show_missing_table_help()
        return
    if error:
        warn(f"No se pudo crear la licencia: {error}")
        press_enter()
        return
    if isinstance(data, list) and data:
        record = data[0]
        ok(f"Licencia creada para {client}.")
        _render_table([record])
        _build_executable(record, url, key)
    else:
        ok("Licencia creada.")
        press_enter()


def _select_and_manage() -> None:
    records = _fetch_licenses()
    if not records:
        press_enter()
        return
    record = _select_license(records)
    if not record:
        return
    _license_actions_loop(record["license_key"])


def _select_and_package(url: str, key: str) -> None:
    records = _fetch_licenses()
    if not records:
        press_enter()
        return
    record = _select_license(records)
    if not record:
        return
    success, message = _package_license(record, url, key)
    if success:
        ok(message)
    else:
        warn(message)
    press_enter()


def verify_license_remote(
    license_key: str,
    supabase_url: str,
    supabase_key: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Valida una licencia usando Supabase."""

    if not license_key:
        return False, "Falta la licencia.", {}
    if not supabase_url or not supabase_key:
        return False, "Faltan credenciales de Supabase.", {}
    endpoint = f"{_TABLE}?license_key=eq.{license_key}&select=*"
    data, error, status = _request(
        "get", endpoint, url_override=supabase_url, key_override=supabase_key
    )
    if _is_missing_table(error, status):
        return False, _missing_table_text(), {}
    if error:
        return False, error, {}
    if not isinstance(data, list) or not data:
        return False, "Licencia inexistente.", {}
    record = data[0]
    status_value = str(record.get("status", "")).lower()
    if status_value == _STATUS_REVOKED:
        return False, "Licencia revocada.", record
    if status_value == _STATUS_EXPIRED or _is_expired(record):
        return False, "Licencia vencida.", record
    if status_value and status_value != _STATUS_ACTIVE:
        return False, f"Licencia en estado {status_value}.", record
    return True, "", record


def enforce_startup_validation() -> None:
    if os.environ.get("LICENSE_ALREADY_VALIDATED") == "1":
        return
    payload = _load_local_payload()
    require = SETTINGS.client_distribution or bool(payload)
    if not require:
        return
    if not payload:
        print(full_line(color=Fore.RED))
        print(style_text("No se encontró licencia local", color=Fore.RED, bold=True))
        print(full_line(color=Fore.RED))
        sys.exit(2)

    license_key = payload.get("license_key", "")
    supabase_url = payload.get("supabase_url", "")
    supabase_key = payload.get("supabase_key", "")

    ok, message, _ = verify_license_remote(license_key, supabase_url, supabase_key)
    if not ok:
        print(full_line(color=Fore.RED))
        print(style_text("Licencia inválida", color=Fore.RED, bold=True))
        print(message or "No se pudo validar la licencia.")
        print(full_line(color=Fore.RED))
        sys.exit(2)


def menu_deliver() -> None:
    if SETTINGS.client_distribution:
        warn("Esta opción no está disponible en builds de cliente.")
        press_enter()
        return
    ready, url, key = _ensure_supabase()
    if not ready:
        return
    if not _ensure_table_ready(url or "", key or ""):
        return
    while True:
        banner()
        print(full_line())
        print(style_text("Entrega al cliente", color=Fore.CYAN, bold=True))
        print(full_line())
        print("1) Ver y gestionar licencias")
        print("2) Crear nueva licencia")
        print("3) Empaquetar build para cliente")
        print("4) Volver")
        print()
        choice = ask("Opción: ").strip()
        if choice == "1":
            _select_and_manage()
        elif choice == "2":
            _create_license(url or "", key or "")
        elif choice == "3":
            _select_and_package(url or "", key or "")
        elif choice == "4":
            break
        else:
            warn("Opción inválida.")
            press_enter()


def ensure_supabase_credentials(interactive: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    """Expone las credenciales de Supabase, solicitándolas si se requiere."""

    return _ensure_supabase(interactive=interactive)


def ensure_table_exists(url: str, key: str, *, interactive: bool = False) -> bool:
    """Comprueba que la tabla de licencias exista (sin interacción por defecto)."""

    return _ensure_table_ready(url, key, interactive=interactive)


def list_licenses() -> List[Dict[str, Any]]:
    """Devuelve todas las licencias disponibles en Supabase."""

    return _fetch_licenses()


def fetch_license(license_key: str) -> Optional[Dict[str, Any]]:
    """Obtiene una licencia puntual."""

    return _fetch_single(license_key)


def package_license(license_key: str, url: str, key: str) -> Tuple[bool, str]:
    """Genera artefactos limpios para la licencia indicada."""

    record = _fetch_single(license_key)
    if not record:
        return False, "Licencia no encontrada."
    return _package_license(record, url, key)

