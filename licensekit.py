# licensekit.py
# -*- coding: utf-8 -*-
from utils import banner, ok, warn, press_enter
import os

def menu_deliver():
    banner()
    print("Para entregar al cliente:")
    print("1) Ejecutá build_exe.bat para generar dist\\insta_cli.exe")
    print("2) Pasale el EXE junto con carpetas .sessions/, data/ y text/ si corresponden.")
    ok("Listo para exportar.")
    press_enter()
