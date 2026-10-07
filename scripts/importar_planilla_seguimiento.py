"""
IMPORTACIÓN ÚNICA desde la "Planilla Resumen y Control de Seguimiento URS Coquimbo" hacia "Datos adicionales".

Qué trae (solo estas 5 columnas; NO se copian contactos, correos, teléfonos ni datos de contratistas):
    Estado Real · % Avance Físico · Fecha Vencimiento Garantía · Contrato en Plataforma? · Evento

Reglas de seguridad:
  - Se usa UNA sola vez: al terminar deja una marca y se niega a repetirse (salvo --forzar).
  - NUNCA pisa lo que ya esté cargado o editado a mano en "Datos adicionales": solo completa campos vacíos.
  - Muestra primero un resumen y pregunta antes de escribir (o usa --simular para no escribir nada).
  - Guarda un respaldo local de "Datos adicionales" antes de modificar Drive.
  - La planilla descargada queda solo en tu computador (data_raw/, excluida de GitHub).

Uso:
    python3 scripts/importar_planilla_seguimiento.py --simular          # solo muestra qué haría
    python3 scripts/importar_planilla_seguimiento.py                    # lee la planilla de Drive y pregunta antes de aplicar
    python3 scripts/importar_planilla_seguimiento.py --archivo planilla.xlsx   # usa un Excel descargado a mano
    python3 scripts/importar_planilla_seguimiento.py --id OTRO_ID       # si la planilla original tiene otro ID
"""
import io
import re
import sys
import copy
import json
import argparse
import collections
import unicodedata
from pathlib import Path
from datetime import datetime, date, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
RAW_DIR = BASE_DIR / "data_raw"
MARCA = RAW_DIR / ".planilla_seguimiento_importada.json"
GITIGNORE = BASE_DIR / ".gitignore"

PLANILLA_ID = "1MZO9dqMiwyt1uK8JwwldhdHnyAfALEKNbWxfzWKS8Fk"      # "Copia de Planilla Resumen y Control de Seguimiento URS Coquimbo"
DATOS_EXTRA_FILE_ID = "1oThL9AfQ1_3i_h676ORmL6MSAi58VF7Z"          # "Datos adicionales" (ID fijo, nunca se busca por nombre)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Clasificación actual del "Estado Real" (la que usa el tablero). El importador avisa si la planilla trae otros valores.
ESTADOS_CONOCIDOS = [
    "01.- Aprobado", "02.- En Preparación de Bases", "03.- En Licitación", "04.- Con Licitación Cerrada", "05.- En Evaluación de Ofertas",
    "06.- Licitación Desierta", "07.- Adjudicado", "09.- En Proceso de Contrato", "10.- Contratado", "11.- En Rescilición de Contrato",
    "12.- En Ejecución", "13.- Terminado sin Recepción", "14.- Terminado", "Terminado con Modificaciones Pendientes", "Proyecto Paralizado",
]

# campo -> encabezados posibles (normalizados). Los 6 primeros se importan; el resto solo sirve para validar la fórmula.
ALIAS = {
    "id_proyecto": ["id proyecto"],
    "estado_real": ["estado real"],
    "avance_fisico": ["avance fisico"],
    "fecha_venc_garantia": ["fecha vencimiento garantia"],
    "contrato_plataforma": ["contrato en plataforma"],
    "evento": ["evento"],
    "contratado_subdere": ["contratado subdere"],
    "monto_total_contratado": ["monto total contratado"],
    "total_asignado": ["total asignado"],
    "total_rendido": ["total rendido a la fecha"],
    "rendicion_conf": ["rendicion conforme a de ejecucion"],
    "por_rendir_conf": ["por rendir conforme a de ejecucion"],
}
CAMPOS_IMPORTADOS = ["estado_real", "avance_fisico", "fecha_venc_garantia", "contrato_plataforma", "evento"]


def norm(t) -> str:
    n = unicodedata.normalize("NFKD", str(t if t is not None else ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in n if not unicodedata.combining(c)).lower()).strip()


# ----------------------------------------------------------------------
# Lectura de la planilla
# ----------------------------------------------------------------------
def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(" ", "")
    if not s or norm(s) in ("no aplica", "na", "n a"):
        return None
    pct = s.endswith("%")
    s = s.rstrip("%")
    if re.search(r",\d{1,2}$", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}(\.|$)", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _fecha(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < v < 80000:          # número de serie de Excel
        return (datetime(1899, 12, 30) + timedelta(days=float(v))).date().isoformat()
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return datetime(y, mo, d).date().isoformat()
    except ValueError:
        return None


def leer_planilla(ruta) -> dict:
    """Devuelve {'filas': {id: {campo: valor}}, 'crudo': [fila con montos para validar], 'hoja': nombre, 'columnas': {...}}."""
    import openpyxl
    libro = openpyxl.load_workbook(str(ruta), data_only=True, read_only=True)
    mejor = None
    for hoja in libro.worksheets:
        filas = list(hoja.iter_rows(values_only=True))
        for i, fila in enumerate(filas[:25]):
            normas = [norm(c) for c in fila]
            if "id proyecto" in normas and "estado real" in normas:
                n_datos = sum(1 for r in filas[i + 1:] if r and r[normas.index("id proyecto")] not in (None, ""))
                if mejor is None or n_datos > mejor[0]:
                    mejor = (n_datos, hoja.title, i, normas, filas)
                break
    if mejor is None:
        raise RuntimeError("No encontré en la planilla ninguna hoja con las columnas 'ID Proyecto' y 'Estado Real'.")
    _, titulo, ini, normas, filas = mejor
    col = {}
    for campo, alias in ALIAS.items():
        for a in alias:
            if a in normas:
                col[campo] = normas.index(a)
                break
    salida, crudo = {}, []
    for r in filas[ini + 1:]:
        if not r:
            continue
        g = lambda campo: r[col[campo]] if campo in col and col[campo] < len(r) else None
        idp = str(g("id_proyecto") or "").strip()
        if not idp or norm(idp) in ("id proyecto", "total", "totales"):
            continue
        estado = re.sub(r"\s+", " ", str(g("estado_real") or "")).strip()
        item = {
            "estado_real": estado or None,
            "avance_fisico": _num(g("avance_fisico")),
            "fecha_venc_garantia": _fecha(g("fecha_venc_garantia")),
            "evento": str(g("evento") or "").strip() or None,
        }
        cp = norm(g("contrato_plataforma"))
        item["contrato_plataforma"] = "SI" if cp in ("si", "s", "1", "true", "yes") else "NO" if cp in ("no", "n", "0", "false") else None
        salida[idp] = item
        crudo.append({k: _num(g(k)) for k in ("avance_fisico", "contratado_subdere", "monto_total_contratado", "total_asignado", "total_rendido", "rendicion_conf", "por_rendir_conf")})
    # El % de avance puede venir como fracción (0,35) o como porcentaje (35): se lleva todo a 0-100
    valores = [v["avance_fisico"] for v in salida.values() if v["avance_fisico"] is not None]
    escala = 100.0 if valores and max(valores) <= 1.0 else 1.0
    for v in salida.values():
        if v["avance_fisico"] is not None:
            v["avance_fisico"] = round(min(100.0, max(0.0, v["avance_fisico"] * escala)), 2)
    for c in crudo:
        if c["avance_fisico"] is not None:
            c["avance_fisico"] = c["avance_fisico"] * escala
    return {"filas": salida, "crudo": crudo, "hoja": titulo, "columnas": {k: normas[i] for k, i in col.items()}, "escala_avance": escala}


def validar_formula(crudo: list) -> list:
    """Averigua con TUS datos cómo calcula la planilla 'Por Rendir conforme a % de ejecución'."""
    lineas = []
    for base in ("contratado_subdere", "monto_total_contratado", "total_asignado"):
        ok = tot = 0
        for c in crudo:
            if c["avance_fisico"] is None or c["rendicion_conf"] is None or c[base] is None:
                continue
            tot += 1
            ok += abs(c[base] * c["avance_fisico"] / 100 - c["rendicion_conf"]) <= 1
        if tot:
            lineas.append((ok / tot, f"'Rendición conforme a % de ejecución' = {base.replace('_', ' ')} × % avance  → coincide en {ok} de {tot} proyectos"))
    ok = tot = 0
    for c in crudo:
        if c["rendicion_conf"] is None or c["por_rendir_conf"] is None or c["total_rendido"] is None:
            continue
        tot += 1
        ok += abs(max(0.0, c["rendicion_conf"] - c["total_rendido"]) - c["por_rendir_conf"]) <= 1
    out = [t for _, t in sorted(lineas, key=lambda x: -x[0])[:2]]
    if tot:
        out.append(f"'Por Rendir conforme a % de ejecución' = máx(0; Rendición conforme − Total Rendido)  → coincide en {ok} de {tot} proyectos")
    return out or ["(la planilla no trae las columnas necesarias para validar la fórmula)"]


# ----------------------------------------------------------------------
# Fusión con "Datos adicionales" (nunca pisa lo ya cargado)
# ----------------------------------------------------------------------
def fusionar(datos_extra: dict, filas: dict, hoy: str):
    nuevos = copy.deepcopy(datos_extra)
    stats = collections.Counter()
    for idp, f in filas.items():
        ex = nuevos.get(idp) or {}
        cambio = False
        for campo in CAMPOS_IMPORTADOS:
            v = f.get(campo)
            if v in (None, ""):
                continue
            if ex.get(campo) in (None, ""):
                ex[campo] = v
                stats[campo] += 1
                cambio = True
            else:
                stats[campo + "_ya_estaba"] += 1
        if cambio:
            ex["planilla_importada"] = hoy
            ex.setdefault("actualizado", hoy)
            ex.setdefault("ultima_edicion_por", "importación única de la planilla de seguimiento")
            nuevos[idp] = ex
            stats["proyectos_modificados"] += 1
    return nuevos, stats


# ----------------------------------------------------------------------
# Drive (aislado para poder probar el resto sin conexión)
# ----------------------------------------------------------------------
def obtener_servicio_drive():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES) if TOKEN_PATH.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES).run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def descargar_planilla(servicio, file_id: str, destino: Path) -> Path:
    from googleapiclient.http import MediaIoBaseDownload
    meta = servicio.files().get(fileId=file_id, fields="name,mimeType").execute()
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        peticion = servicio.files().export_media(fileId=file_id, mimeType=XLSX)
    else:
        peticion = servicio.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    descarga = MediaIoBaseDownload(buf, peticion)
    listo = False
    while not listo:
        _, listo = descarga.next_chunk()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(buf.getvalue())
    print(f"Planilla descargada: {meta['name']}  ->  {destino.name}")
    return destino


def leer_json_drive(servicio, file_id: str):
    contenido = servicio.files().get_media(fileId=file_id).execute()
    return json.loads(contenido.decode("utf-8")) if contenido else {}


def escribir_json_drive(servicio, file_id: str, datos: dict):
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(datos, ensure_ascii=False).encode("utf-8")), mimetype="application/json")
    servicio.files().update(fileId=file_id, media_body=media).execute()


def proteger_gitignore():
    linea = "data_raw/planilla_seguimiento_*"
    actual = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else ""
    if linea not in {l.strip() for l in actual.splitlines()}:
        GITIGNORE.write_text(actual.rstrip("\n") + ("\n" if actual else "") + "# Planilla de seguimiento (trae contactos): no subir a GitHub\n" + linea + "\n", encoding="utf-8")


def ids_del_informe_financiero():
    try:
        d = json.loads((BASE_DIR / "para_subir_a_drive" / "rendiciones.json").read_text(encoding="utf-8"))
        return {p["id_proyecto"] for p in d["proyectos"] if p.get("id_proyecto")}
    except Exception:
        return None


def resumen(planilla: dict, datos_extra: dict, hoy: str) -> str:
    filas = planilla["filas"]
    L = [f"Hoja usada: '{planilla['hoja']}' · {len(filas)} proyectos en la planilla"]
    est = collections.Counter(f["estado_real"] for f in filas.values() if f["estado_real"])
    L.append(f"\nEstado Real: {sum(est.values())} proyectos con estado, {len(est)} estados distintos")
    for e, n in sorted(est.items(), key=lambda x: x[0]):
        L.append(f"   {n:>4}  {e}" + ("" if e in ESTADOS_CONOCIDOS else "   <-- NO está en la lista del desplegable (se agregará automáticamente como opción)"))
    av = [f["avance_fisico"] for f in filas.values() if f["avance_fisico"] is not None]
    L.append(f"\n% Avance Físico: {len(av)} proyectos con dato" + (f" (mín {min(av)} · máx {max(av)} · escala detectada: {'fracción 0-1 → ×100' if planilla['escala_avance'] == 100 else 'ya en 0-100'})" if av else ""))
    fg = [f["fecha_venc_garantia"] for f in filas.values() if f["fecha_venc_garantia"]]
    L.append(f"Fecha vencimiento garantía: {len(fg)} proyectos con fecha · ya vencidas: {sum(1 for x in fg if x < hoy)}")
    cp = collections.Counter(f["contrato_plataforma"] for f in filas.values() if f["contrato_plataforma"])
    L.append(f"Contrato en plataforma: {dict(cp)}")
    L.append(f"Evento: {sum(1 for f in filas.values() if f['evento'])} proyectos con evento")
    ids = ids_del_informe_financiero()
    if ids is not None:
        faltan = [i for i in filas if i not in ids]
        L.append(f"\nCoincidencia con el informe financiero: {len(filas) - len(faltan)} de {len(filas)} proyectos" + (f" · {len(faltan)} NO están en el informe (ej.: {', '.join(faltan[:4])})" if faltan else ""))
    previos = sum(1 for i in filas if (datos_extra.get(i) or {}).get("estado_real") or (datos_extra.get(i) or {}).get("avance_fisico") not in (None, ""))
    L.append(f"Proyectos que YA tienen estado o avance en Datos adicionales (no se tocan): {previos}")
    L.append("\nCómo calcula la planilla el 'Por Rendir conforme a % de ejecución' (validado con tus datos):")
    L += ["   " + t for t in validar_formula(planilla["crudo"])]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", help="Excel de la planilla ya descargado (si no, se descarga de Drive)")
    ap.add_argument("--id", default=PLANILLA_ID, help="ID de la planilla en Drive")
    ap.add_argument("--simular", action="store_true", help="solo muestra el resumen; no escribe nada")
    ap.add_argument("--si", action="store_true", help="no preguntar confirmación")
    ap.add_argument("--forzar", action="store_true", help="permitir repetir la importación (igual no pisa datos existentes)")
    a = ap.parse_args(argv)
    hoy = date.today().isoformat()

    if MARCA.exists() and not a.forzar and not a.simular:
        previa = json.loads(MARCA.read_text(encoding="utf-8"))
        sys.exit(f"La planilla ya se importó el {previa.get('fecha')} ({previa.get('proyectos_modificados')} proyectos). Esta importación es de una sola vez. "
                 "Si de verdad necesitas repetirla: --forzar (no pisa lo ya cargado).")
    servicio = None
    if a.archivo:
        ruta = Path(a.archivo)
    else:
        servicio = obtener_servicio_drive()
        ruta = descargar_planilla(servicio, a.id, RAW_DIR / f"planilla_seguimiento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        proteger_gitignore()
    planilla = leer_planilla(ruta)
    servicio = servicio or (None if a.simular and not a.archivo else obtener_servicio_drive())
    datos_extra = leer_json_drive(servicio, DATOS_EXTRA_FILE_ID) if servicio else {}
    print(resumen(planilla, datos_extra, hoy))
    nuevos, stats = fusionar(datos_extra, planilla["filas"], hoy)
    print("\nSe completarían: " + ", ".join(f"{k.replace('_', ' ')}: {stats[k]}" for k in CAMPOS_IMPORTADOS) + f"  ·  proyectos modificados: {stats['proyectos_modificados']}")
    if a.simular:
        print("\n(Simulación: no se escribió nada.)")
        return
    if not a.si and input("\n¿Aplicar en 'Datos adicionales' (Drive)? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se aplicó nada.")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    respaldo = RAW_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    respaldo.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo guardado en: {respaldo}")
    escribir_json_drive(servicio, DATOS_EXTRA_FILE_ID, nuevos)
    MARCA.write_text(json.dumps({"fecha": hoy, "proyectos_modificados": stats["proyectos_modificados"], "planilla": a.id}, ensure_ascii=False), encoding="utf-8")
    print("Listo: 'Datos adicionales' actualizado. Publica el dashboard y recárgalo (Cmd+Shift+R).")


if __name__ == "__main__":
    main()
