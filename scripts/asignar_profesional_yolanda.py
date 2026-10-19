"""
Asigna a YOLANDA MOYA los proyectos que le corresponden según las reglas de reglas_profesionales.py
(comunas Los Vilos, Andacollo, La Higuera, Punitaqui, Monte Patria y Río Hurtado, en los programas
Emergencia, Tradicional, Emergencia Fondo Infraestructura Educacional, Subsecretaría Prevención del Delito
y Ministerio de Transporte y Telecomunicación).

- Solo toca esos proyectos (los de otros profesionales no se tocan).
- REEMPLAZA al profesional que tenían (Tamara, Romina o una asignación manual): es lo que se pidió.
  El resumen muestra cuántos venían de cada uno antes de que confirmes.
- Antes de escribir guarda un respaldo de "Datos adicionales" en data_raw/.
- Se puede repetir: lo que ya es de Yolanda no se vuelve a cambiar.

Uso:
    python3 scripts/asignar_profesional_yolanda.py --simular
    python3 scripts/asignar_profesional_yolanda.py          # pregunta antes de escribir
"""
import sys
import json
import argparse
import collections
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asignar_evento_listado as lst            # Drive y proyectos publicados
from reglas_profesionales import calcular_profesional

PROFESIONAL = "Yolanda Moya"
BASE_DIR = lst.BASE_DIR
DATOS_EXTRA_FILE_ID = lst.DATOS_EXTRA_FILE_ID


def planificar(proyectos: list, datos_extra: dict) -> dict:
    """Calcula (sin escribir) qué proyectos pasan a Yolanda. Pura: se prueba sin Drive."""
    cambios, ya = {}, 0
    previos = collections.Counter()
    for p in proyectos:
        idp = p.get("id_proyecto")
        if not idp or calcular_profesional(p.get("programa"), p.get("comuna")) != PROFESIONAL:
            continue
        actual = ((datos_extra.get(idp) or {}).get("profesional") or "").strip()
        if actual == PROFESIONAL:
            ya += 1
            continue
        cambios[idp] = p
        previos[actual or "(sin profesional)"] += 1
    return {"cambios": cambios, "ya": ya, "previos": previos}


def aplicar(datos_extra: dict, cambios: dict) -> dict:
    nuevos = json.loads(json.dumps(datos_extra))
    for idp in cambios:
        entrada = nuevos.get(idp) or {}
        entrada["profesional"] = PROFESIONAL
        nuevos[idp] = entrada
    return nuevos


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--si", action="store_true", help="no preguntar confirmación")
    a = ap.parse_args(argv)
    servicio = lst.obtener_servicio_drive()
    proyectos = lst.cargar_proyectos(servicio)
    datos_extra = lst.leer_json_drive(servicio, DATOS_EXTRA_FILE_ID)
    plan = planificar(proyectos, datos_extra)
    cambios = plan["cambios"]
    print(f"Proyectos que corresponden a {PROFESIONAL}: {len(cambios) + plan['ya']} (ya eran suyos: {plan['ya']} · pasan a ella: {len(cambios)})\n")
    print("Venían de:")
    for quien, n in plan["previos"].most_common():
        print(f"   {n:>4}  {quien}")
    por = collections.Counter((p["programa"], p["comuna"]) for p in cambios.values())
    print("\nPor programa y comuna:")
    for (prog, com), n in sorted(por.items(), key=lambda x: (x[0][0], -x[1])):
        print(f"   {n:>4}  {prog}  ·  {com}")
    if a.simular:
        print("\n(Simulación: no se escribió nada.)")
        return
    if not cambios:
        print("\nNada que hacer.")
        return
    if not a.si and input(f"\n¿Asignar {len(cambios)} proyectos a {PROFESIONAL} en 'Datos adicionales' (Drive)? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se aplicó nada.")
        return
    lst.RESPALDOS_DIR.mkdir(exist_ok=True)
    resp = lst.RESPALDOS_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    resp.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo: {resp.name}")
    lst.escribir_json_drive(servicio, DATOS_EXTRA_FILE_ID, aplicar(datos_extra, cambios))
    print(f"Listo: {len(cambios)} proyectos asignados a {PROFESIONAL}.")


if __name__ == "__main__":
    main()
