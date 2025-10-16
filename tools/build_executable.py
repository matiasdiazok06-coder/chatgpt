# tools/build_executable.py
# -*- coding: utf-8 -*-
"""Utilidad para generar ejecutables por licencia."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple


def _slugify(value: str) -> str:
    cleaned = [c if c.isalnum() or c in {"_", "-"} else "_" for c in value.lower()]
    slug = "".join(cleaned).strip("_")
    return slug or "cliente"


def _guess_output(dist_dir: Path, name: str) -> Path:
    if sys.platform.startswith("win"):
        candidate = dist_dir / f"{name}.exe"
        if candidate.exists():
            return candidate
    elif sys.platform == "darwin":
        candidate = dist_dir / f"{name}.app"
        if candidate.exists():
            return candidate
    candidate = dist_dir / name
    if candidate.exists():
        return candidate
    # fallback al .exe por si PyInstaller usa sufijo aun en otros SO
    candidate_exe = dist_dir / f"{name}.exe"
    if candidate_exe.exists():
        return candidate_exe
    return candidate


def build_for_license(
    record: Dict[str, str],
    supabase_url: str,
    supabase_key: str,
    *,
    name: str | None = None,
) -> Tuple[bool, Path | None, str]:
    """Genera un ejecutable para la licencia suministrada."""

    root = Path(__file__).resolve().parents[1]
    launcher = root / "client_launcher.py"
    if not launcher.exists():
        return False, None, "No se encontró client_launcher.py"

    dist_dir = root / "dist"
    dist_dir.mkdir(exist_ok=True)

    payload_path = root / "storage" / "license_payload.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "license_key": record.get("license_key"),
        "client_name": record.get("client_name"),
        "supabase_url": supabase_url,
        "supabase_key": supabase_key,
        "issued_at": record.get("issued_at"),
        "expires_at": record.get("expires_at"),
    }
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    exe_name = name or f"insta_cli_{_slugify(record.get('client_name') or 'cliente')}"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        exe_name,
        "--add-data",
        f"{payload_path}{os.pathsep}storage",
        "client_launcher.py",
    ]

    try:
        subprocess.run(command, check=True, cwd=root)
    except subprocess.CalledProcessError as exc:
        return False, None, f"Error al ejecutar PyInstaller: {exc}"
    finally:
        try:
            payload_path.unlink()
        except FileNotFoundError:
            pass

    output = _guess_output(dist_dir, exe_name)
    if not output.exists():
        return False, None, "PyInstaller no generó el archivo esperado."
    return True, output, f"Ejecutable generado en {output}"

