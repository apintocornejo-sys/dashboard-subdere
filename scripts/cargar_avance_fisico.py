"""
Carga el "% Avance Físico" de la planilla de seguimiento (hoja ProyectosVigentes) en "Datos adicionales",
campo avance_fisico (el "% de avance físico" de la ficha del proyecto en el dashboard).

  - Solo toca el campo avance_fisico; no modifica ningún otro dato.
  - Por defecto NO pisa un % ya cargado a mano (usa --sobrescribir para reemplazarlo con el de la planilla).
  - Solo carga proyectos que existen en el dashboard (proyectos.json). Los ID de la planilla con sufijo
    "[FET]" / "[CHA]" o leídos como número ("41030209.0") se normalizan antes de buscarlos.
  - Muestra el resumen y pregunta antes de escribir; guarda un respaldo local en data_raw/.

Uso:
    python3 scripts/cargar_avance_fisico.py --simular        # solo muestra qué haría
    python3 scripts/cargar_avance_fisico.py                  # pregunta antes de aplicar
    python3 scripts/cargar_avance_fisico.py --sobrescribir   # reemplaza también los % ya cargados
"""
import io
import re
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importar_planilla_seguimiento as imp  # noqa: E402  (reutiliza lectura de planilla y Drive)

DRIVE_FILE_ID = "1ZRi0TAbjIozOnZ00cbH9O68sX4Ejlds8"            # proyectos.json
DATOS_EXTRA_FILE_ID = imp.DATOS_EXTRA_FILE_ID                  # "Datos adicionales"


def normalizar_id(idp: str) -> str:
    idp = re.sub(r"\s*\[.*?\]\s*", "", str(idp)).strip()
    return re.sub(r"\.0$", "", idp)


def aplicar_avance(datos_extra: dict, filas: dict, ids_dashboard: set, hoy: str, sobrescribir=False):
    """Devuelve (nuevos_datos, cambios[(id, antes, después)], omitidos_ya_cargados, no_encontrados[id_planilla])."""
    nuevos = json.loads(json.dumps(datos_extra))
    cambios, ya, faltan = [], 0, []
    for id_planilla, f in filas.items():
        av = f.get("avance_fisico")
        if av is None:
            continue
        idp = normalizar_id(id_planilla)
        if idp not in ids_dashboard:
            faltan.append(id_planilla)
            continue
        ex = nuevos.get(idp) or {}
        antes = ex.get("avance_fisico")
        if antes not in (None, "") and not sobrescribir:
            ya += 1
            continue
        if antes not in (None, "") and float(antes) == float(av):
            continue
        ex["avance_fisico"] = av
        ex["actualizado"] = hoy
        ex["ultima_edicion_por"] = "carga de % avance físico desde planilla de seguimiento"
        nuevos[idp] = ex
        cambios.append((idp, antes, av))
    return nuevos, cambios, ya, faltan


def _bajar_json(servicio, file_id):
    return json.loads(servicio.files().get_media(fileId=file_id).execute().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="no escribe nada en Drive")
    ap.add_argument("--sobrescribir", action="store_true", help="reemplaza también los %% ya cargados")
    ap.add_argument("--archivo", help="usar un Excel de la planilla descargado a mano")
    ap.add_argument("--id", default=imp.PLANILLA_ID, help="ID de la planilla en Drive")
    a = ap.parse_args()

    from datetime import datetime
    from googleapiclient.http import MediaIoBaseUpload
    hoy = datetime.now().strftime("%Y-%m-%d")
    servicio = imp.obtener_servicio_drive()

    ruta = Path(a.archivo) if a.archivo else imp.descargar_planilla(servicio, a.id, imp.RAW_DIR / "planilla_seguimiento.xlsx")
    planilla = imp.leer_planilla(ruta)
    print(f"Hoja leída: {planilla['hoja']}  ·  columna: '{planilla['columnas'].get('avance_fisico')}'")
    if "avance_fisico" not in planilla["columnas"]:
        sys.exit("La planilla no tiene la columna '% Avance Físico'.")

    ids_dashboard = {p["id_proyecto"] for p in _bajar_json(servicio, DRIVE_FILE_ID)["proyectos"]}
    datos_extra = _bajar_json(servicio, DATOS_EXTRA_FILE_ID)
    nuevos, cambios, ya, faltan = aplicar_avance(datos_extra, planilla["filas"], ids_dashboard, hoy, a.sobrescribir)

    print(f"\nProyectos a actualizar: {len(cambios)}")
    for idp, antes, despues in cambios[:15]:
        print(f"   {idp}: {'' if antes in (None, '') else str(antes) + '% -> '}{despues}%")
    if len(cambios) > 15:
        print(f"   ... y {len(cambios) - 15} más")
    if ya:
        print(f"Con % ya cargado (no se tocan; usa --sobrescribir para reemplazarlos): {ya}")
    if faltan:
        print(f"En la planilla pero no en el dashboard ({len(faltan)}): {', '.join(faltan)}")

    if not cambios:
        print("\nNada que actualizar.")
        return
    if a.simular:
        print("\n--simular: no se escribió nada.")
        return
    if input("\n¿Aplicar en 'Datos adicionales'? (s/n): ").strip().lower() not in ("s", "si", "sí"):
        print("Cancelado.")
        return

    imp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    respaldo = imp.RAW_DIR / f"datos_adicionales_respaldo_{datetime.now():%Y%m%d_%H%M%S}.json"
    respaldo.write_text(json.dumps(datos_extra, ensure_ascii=False), encoding="utf-8")
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(nuevos, ensure_ascii=False).encode("utf-8")), mimetype="application/json")
    servicio.files().update(fileId=DATOS_EXTRA_FILE_ID, media_body=media).execute()
    print(f"Listo: {len(cambios)} proyecto(s) con % de avance físico cargado. Respaldo: data_raw/{respaldo.name}")


if __name__ == "__main__":
    main()
