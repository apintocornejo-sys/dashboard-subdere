"""Sube para_subir_a_drive/visitas.json al archivo "Visitas (calendario)" de Drive (con respaldo previo).
Uso:  python3 scripts/subir_visitas.py
"""
import json, sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from asignar_evento_listado import obtener_servicio_drive, leer_json_drive, escribir_json_drive

VISITAS_FILE_ID = "1BdiweDix_xw7ZmRSzFAaQj8P7UgyQaYn"
BASE = Path(__file__).resolve().parent.parent
nuevo = json.loads((BASE / "para_subir_a_drive" / "visitas.json").read_text(encoding="utf-8"))
assert nuevo.get("visitas"), "visitas.json vacío"
s = obtener_servicio_drive()
actual = leer_json_drive(s, VISITAS_FILE_ID)
resp = BASE / "data_raw" / f"visitas_respaldo_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
resp.write_text(json.dumps(actual, ensure_ascii=False), encoding="utf-8")
print(f"Respaldo: {resp.name} ({len(actual.get('visitas', []))} visitas)")
escribir_json_drive(s, VISITAS_FILE_ID, nuevo)
print(f"Subido: {len(nuevo['visitas'])} visitas (generado {nuevo['generado']}).")
