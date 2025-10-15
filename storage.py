# storage.py
# -*- coding: utf-8 -*-
import json, time
from pathlib import Path
from typing import Dict, List
from utils import banner, title, ask, press_enter, ok, warn

BASE = Path(__file__).resolve().parent
STO = BASE / "storage"
STO.mkdir(exist_ok=True)
SENT = STO / "sent_log.jsonl"
AUTO = STO / "autoresponder_state.json"

def log_sent(account:str, username:str, okflag:bool, detail:str=""):
    rec={"ts":int(time.time()), "account":account, "to":username, "ok":bool(okflag), "detail":detail}
    with SENT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False)+"\n")

def already_contacted(username:str)->bool:
    if not SENT.exists(): return False
    for line in SENT.read_text(encoding="utf-8").splitlines():
        try:
            obj=json.loads(line)
            if obj.get("to","").lower()==username.lower():
                return True
        except Exception: pass
    return False

def menu_logs():
    banner()
    title("Últimos envíos:")
    if not SENT.exists():
        print("(sin registros)"); press_enter(); return
    lines=SENT.read_text(encoding="utf-8").splitlines()[-50:]
    for ln in lines:
        try:
            obj=json.loads(ln)
            ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(obj["ts"]))
            status="OK" if obj.get("ok") else "ERROR"
            print(f"{ts}  @{obj.get('account')} → @{obj.get('to')}  [{status}] {obj.get('detail','')}")
        except Exception: pass
    press_enter()

def get_auto_state()->Dict:
    if not AUTO.exists(): return {}
    try: return json.loads(AUTO.read_text(encoding="utf-8"))
    except Exception: return {}

def save_auto_state(state:Dict):
    AUTO.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# Opcional: supabase
def menu_supabase():
    banner()
    print("Supabase opcional. Configurá SUPABASE_URL y SUPABASE_KEY en variables de entorno.")
    press_enter()
