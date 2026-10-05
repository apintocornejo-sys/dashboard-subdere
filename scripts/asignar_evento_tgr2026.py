"""
Asigna el evento "Transferencia Gobierno Regional 2026" a los proyectos de un
listado de nombres.

Cómo funciona:
  1. Lee los proyectos publicados en Drive (la misma fuente que usa el dashboard).
  2. Busca cada nombre del listado, ignorando tildes, mayúsculas, paréntesis,
     guiones y espacios de más. Si no hay coincidencia exacta, busca la más
     parecida (para errores de tipeo) y la marca como "aproximada" para que
     la revises.
  3. Muestra un resumen COMPLETO y te pregunta antes de cambiar nada.
  4. Guarda un respaldo local de "datos adicionales" y recién ahí escribe en Drive.

Uso:
    python3 scripts/asignar_evento_tgr2026.py              # normal (pregunta antes de aplicar)
    python3 scripts/asignar_evento_tgr2026.py --simular    # solo muestra, no cambia nada
    python3 scripts/asignar_evento_tgr2026.py --lista otro_listado.txt   # usar otro listado

Para cambiar el listado: edita LISTADO_PROYECTOS aquí abajo (un nombre por línea)
o usa --lista con un archivo de texto (un nombre por línea).
"""

import sys
import io
import json
import re
import argparse
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROYECTOS_JSON_LOCAL = BASE_DIR / "para_subir_a_drive" / "proyectos.json"
RESPALDOS_DIR = BASE_DIR / "data_raw"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_FILE_ID = "1ZRi0TAbjIozOnZ00cbH9O68sX4Ejlds8"           # proyectos.json
DATOS_EXTRA_FILE_ID = "1oThL9AfQ1_3i_h676ORmL6MSAi58VF7Z"     # datos adicionales

EVENTO_A_ASIGNAR = "Transferencia Gobierno Regional 2026"
UMBRAL_APROXIMADO = 0.92   # parecido mínimo (0 a 1) para proponer una coincidencia aproximada
MARGEN_APROXIMADO = 0.02   # la mejor candidata debe superar a la segunda por al menos esto

# Un nombre por línea. (La línea 3 del listado original traía dos proyectos
# pegados; aquí están separados.)
LISTADO_PROYECTOS = """
CATÁSTROFE- HABILITACIÓN CAMINOS PÚBLICOS SECTOR SUR Y ORIENTE, COMBARBALÁ
CATÁSTROFE- HABILITACIÓN CAMINOS PÚBLICOS, SECTOR RURAL PONIENTE, COMBARBALÁ
(CATÁSTROFE) HABILITACIÓN DE CAMINOS EN SECTORES URBANOS Y RURALES, COMUNA DE ILLAPEL
(CATASTROFE) HABILITACIÓN Y DESPEJE DE CAMINOS EN LA COMUNA DE COQUIMBO
(CATASTROFE) SERVICIOS DE LIMPIEZA Y SANITIZACION DE CALLES Y PUNTOS CRITICOS DE LA COMUNA DE COQUIMBO
CATASTROFE-HABILITACIÓN DE CAMINOS RURALES SECTOR CORDILLERA, COMUNA DE VICUÑA
CATASTROFE- HABILITACIÓN DE CAMINOS RURALES SECTOR COSTA , COMUNA DE VICUÑA
(CATÁSTROFE) HABILITACIÓN DE CAMINOS RURALES SECTORES SEMICONCENTRADOS DE LA COMUNA CANELA
(CATÁSTROFE) HABILITACIÓN DE CAMINOS RURALES SECTORES CONCENTRADOS DE LA COMUNA DE CANELA
(CATÁSTROFE) HABILITACIÓN DE CAMINOS RURALES SECTORES COSTEROS DE LA COMUNA DE CANELA
(CATÁSTROFE) HABILITACIÓN DE RED VIAL LOCAL NO PAVIMENTADA, SECTORES MONTE PATRIA - RIO HUATULAME, COMUNA DE MONTE PATRIA
(CATÁSTROFE) HABILITACIÓN DE RED VIAL LOCAL NO PAVIMENTADA, SECTORES RIO GRANDE - RIO RAPEL - RIO MOSTAZAL, COMUNA DE MONTE PATRIA
CATÁSTROFE- HABILITACIÓN CAMINOS PÚBLICOS, SECTOR RURAL NORTE, COMBARBALÁ
CATÁSTROFE - HABILITACIÓN VIALIDADES SECTOR VIÑA VIEJA, COMUNA DE PUNITAQUI
(CATÁSTROFE) HABILITACIÓN DE CAMINOS EN SECTORES RURALES, COMUNA DE ILLAPEL
(CATÁSTROFE) LIMPIEZA Y SANITIZACIÓN DEL ESPACIO PÚBLICO EN LOS SECTORE URBANO DE LA COMUNA DE SALAMANCA
(CATÁSTROFE) DESTRONQUE EN ESPACIOS PÚBLICOS DE LOCALIDADES AFECTADAS POR SISTEMA FRONTAL, COMUNA DE PAIHUANO.
(CATÁSTROFE) HABILITACIÓN DE CAMINOS PÚBLICOS EN LOCALIDADES AFECTADAS POR SISTEMA FRONTAL, COMUNA DE PAIHUANO.
(CATÁSTROFE) MEJORAMIENTO DE CAMINOS PÚBLICOS EN LOCALIDADES AFECTADAS POR SISTEMA FRONTAL, COMUNA DE PAIHUANO
(CATÁSTROFE) SANITIZACIÓN DE CAMINOS PÚBLICOS EN LOCALIDADES AFECTADAS POR SISTEMA FRONTAL, COMUNA DE PAIHUANO.
(CATÁSTROFE) HABILITACION RED VIAL MEDIANTE LIMPIEZA, PODA Y DESPEJE DE CAMINOS, VARIOS SECTORES DE LA COMUNA DE MONTE PATRIA
CATASTROFE HABILITACIÓN Y LIMPIEZA DE PLAYAS Y ESPACIO PUBLICO AV DEL MAR: EL FARO, AV. DEL MAR, AV. PACÍFICO, P. ANTONIO AGUILAR, AV. FCO. DE AGUIRRE
CATASTROFE HABILITACIÓN Y LIMPIEZA DE PLAYAS Y ESPACIO PUBLICO AV DEL MAR: AV. DEL MAR - LAS HIGUERAS, LOS PERALES, HORTENCIA BUSTAMANET, LAS HIGUERAS
CATASTROFE HABILITACIÓN Y LIMPIEZA DE PLAYAS Y ESPACIO PUBLICO AV DEL MAR : AV. DEL MAR - LOS PERALES - LOS LÚCUMOS - AV. PACÍFICO - LOS PERALES
CATASTROFE HABILITACIÓN Y LIMPIEZA DE PLAYAS Y ESPACIO PUBLICO AV DEL MAR: AV. DEL MAR - LOS LÚCUMOS - CANTO DEL AGUA - AV. PACÍFICO.
CATRÁSTROFE - HABILITACIÓN VIALIDADES VARIOS SECTORES, COMUNA DE PUNITAQUI
(CATASTROFE) HABILITACION RED VIAL LOCAL DE LA HIGUERA, PUNTA COLORADA, LOS CHOROS Y CALETA LOS HORNOS, COMUNA DE LA HIGUERA
(CATASTROFE) HABILITACION RED VIAL LOCAL DE PUNTA DE CHOROS, COMUNA DE LA HIGUERA
(CATASTROFE) HABILITACION RED VIAL LOCAL DE CHUNGUNGO, COMUNA DE LA HIGUERA
(CATASTROFE) HABILITACIÓN DE ESPACIO PUBLICO VARIAS CALLES DE PICHIDANGUI, COMUNA DE LOS VILOS
(CATÁSTROFE) HABILITACIÓN DE RED VIAL LOCAL NO PAVIMENTADA, FLOR DEL VALLE - CERRILLOS DE RAPEL, COMUNA DE MONTE PATRIA
(CATÁSTROFE) HABILITACIÓN VIALIDADES VARIAS LOCALIDADES, ZONA BAJA, COMUNA DE RIO HURTADO
"""

COMUNAS = ["LA SERENA", "COQUIMBO", "ANDACOLLO", "LA HIGUERA", "PAIGUANO", "VICUNA", "OVALLE",
           "COMBARBALA", "MONTE PATRIA", "PUNITAQUI", "RIO HURTADO", "ILLAPEL", "CANELA",
           "LOS VILOS", "SALAMANCA"]


# ----------------------------------------------------------------------
# Utilidades de texto
# ----------------------------------------------------------------------
def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin signos: deja solo letras/números separados por 1 espacio."""
    nfkd = unicodedata.normalize("NFKD", str(texto or ""))
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


def comunas_mencionadas(texto_norm: str) -> set:
    """Comunas que aparecen como palabra completa en un texto ya normalizado."""
    texto_norm = texto_norm.replace("paihuano", "paiguano")   # el nombre se escribe de dos formas
    return {c for c in COMUNAS if re.search(r"\b" + c.lower() + r"\b", texto_norm)}


def leer_listado(ruta: str = None) -> list:
    bruto = Path(ruta).read_text(encoding="utf-8") if ruta else LISTADO_PROYECTOS
    nombres = []
    for linea in bruto.splitlines():
        linea = linea.strip().lstrip("*•-").strip()
        if linea:
            nombres.append(linea)
    return nombres


# ----------------------------------------------------------------------
# Drive (aisladas para poder probar el resto sin conexión)
# ----------------------------------------------------------------------
def obtener_servicio_drive():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def leer_json_drive(servicio, file_id: str):
    contenido = servicio.files().get_media(fileId=file_id).execute()
    return json.loads(contenido.decode("utf-8")) if contenido else {}


def escribir_json_drive(servicio, file_id: str, datos: dict):
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(datos, ensure_ascii=False).encode("utf-8")),
                              mimetype="application/json")
    servicio.files().update(fileId=file_id, media_body=media).execute()


def cargar_proyectos(servicio) -> list:
    """Los proyectos publicados en Drive (fuente del dashboard); si falla, el archivo local."""
    try:
        return leer_json_drive(servicio, DRIVE_FILE_ID)["proyectos"]
    except Exception as e:
        print(f"  (No pude leer los proyectos desde Drive: {e}. Uso el archivo local.)")
        return json.loads(PROYECTOS_JSON_LOCAL.read_text(encoding="utf-8"))["proyectos"]


# ----------------------------------------------------------------------
# Búsqueda
# ----------------------------------------------------------------------
def anio_postulacion(p):
    try:
        return int(float(p.get("anio_postulacion")))
    except (TypeError, ValueError):
        return None


def buscar(nombres: list, proyectos: list) -> dict:
    """Devuelve {'exactos', 'aproximados', 'sin_coincidencia', 'ambiguos'} con el detalle."""
    indice = {}
    for p in proyectos:
        if p.get("id_proyecto"):
            indice.setdefault(normalizar(p.get("nombre_proyecto")), []).append(p)

    pool_2026 = [p for p in proyectos if p.get("id_proyecto") and anio_postulacion(p) == 2026]
    pool_fuzzy = [(normalizar(p.get("nombre_proyecto")), p) for p in (pool_2026 or proyectos) if p.get("id_proyecto")]

    res = {"exactos": [], "aproximados": [], "sin_coincidencia": [], "ambiguos": []}
    pendientes = []

    # Pasada 1: coincidencias exactas (ignorando tildes, signos y mayúsculas)
    for nombre in nombres:
        n = normalizar(nombre)
        candidatos = indice.get(n, [])
        if len(candidatos) > 1:                      # mismo nombre repetido: preferir los de postulación 2026
            c2026 = [p for p in candidatos if anio_postulacion(p) == 2026]
            candidatos = c2026 if c2026 else candidatos
        if len(candidatos) == 1:
            res["exactos"].append({"nombre": nombre, "proyecto": candidatos[0], "parecido": 1.0})
        elif len(candidatos) > 1:
            res["ambiguos"].append({"nombre": nombre, "proyectos": candidatos})
        else:
            pendientes.append(nombre)

    # Los proyectos ya calzados exactos quedan "reservados": no pueden ser la coincidencia
    # aproximada de otro nombre (p. ej. un proyecto hermano de la misma comuna).
    reservados = {r["proyecto"]["id_proyecto"] for r in res["exactos"]}
    for r in res["ambiguos"]:
        reservados |= {p["id_proyecto"] for p in r["proyectos"]}

    # Pasada 2: para los que quedaron sin calzar, la coincidencia más parecida (aproximada)
    for nombre in pendientes:
        n = normalizar(nombre)
        mencionadas = comunas_mencionadas(n)
        puntajes = []
        for nombre_p, p in pool_fuzzy:
            if p["id_proyecto"] in reservados:
                continue
            # Si el listado nombra una comuna y el proyecto está en otra, es otro proyecto (hermano): descartar
            comuna_p = normalizar(p.get("comuna")).replace("paihuano", "paiguano")
            if len(mencionadas) == 1 and comuna_p and comuna_p not in {c.lower() for c in mencionadas}:
                continue
            sm = SequenceMatcher(None, n, nombre_p)
            if sm.real_quick_ratio() < UMBRAL_APROXIMADO or sm.quick_ratio() < UMBRAL_APROXIMADO:
                continue
            puntajes.append((sm.ratio(), p))
        puntajes.sort(key=lambda t: t[0], reverse=True)
        if puntajes and puntajes[0][0] >= UMBRAL_APROXIMADO and \
           (len(puntajes) == 1 or puntajes[0][0] - puntajes[1][0] >= MARGEN_APROXIMADO):
            res["aproximados"].append({"nombre": nombre, "proyecto": puntajes[0][1], "parecido": puntajes[0][0]})
            reservados.add(puntajes[0][1]["id_proyecto"])
        else:
            res["sin_coincidencia"].append({"nombre": nombre, "mejor": puntajes[0] if puntajes else None})
    return res


# ----------------------------------------------------------------------
# Presentación
# ----------------------------------------------------------------------
def linea_proyecto(p, datos_extra):
    evento_actual = (datos_extra.get(p["id_proyecto"], {}) or {}).get("evento", "")
    if evento_actual == EVENTO_A_ASIGNAR:
        marca = "  [ya tenía este evento]"
    elif evento_actual:
        marca = f"  [antes: {evento_actual}]"
    else:
        marca = ""
    return f"{p['id_proyecto']} | {p.get('comuna')} | {p.get('estado')}{marca}"


def aviso_comuna(nombre_listado, proyecto):
    """Alerta si la comuna que menciona el nombre del listado no coincide con la del proyecto."""
    mencionadas = comunas_mencionadas(normalizar(nombre_listado))
    comuna_p = normalizar(proyecto.get("comuna")).replace("paihuano", "paiguano")
    if len(mencionadas) == 1 and comuna_p and comuna_p not in {c.lower() for c in mencionadas}:
        return f"      ⚠ el listado menciona {list(mencionadas)[0]} pero el proyecto está en {proyecto.get('comuna')}"
    return None


def mostrar_resumen(res, datos_extra, total_nombres):
    print("\n" + "=" * 78)
    print(f"RESULTADO DE LA BÚSQUEDA  ({total_nombres} nombres en el listado)")
    print("=" * 78)
    print(f"  ✔ Coincidencias exactas ........ {len(res['exactos'])}")
    print(f"  ≈ Coincidencias aproximadas .... {len(res['aproximados'])}   (revisar)")
    print(f"  ⚠ Ambiguos (nombre repetido) ... {len(res['ambiguos'])}")
    print(f"  ✘ Sin coincidencia ............. {len(res['sin_coincidencia'])}")

    if res["exactos"]:
        print("\n✔ EXACTOS")
        for r in res["exactos"]:
            print(f"  - {linea_proyecto(r['proyecto'], datos_extra)}")
            print(f"      {r['proyecto'].get('nombre_proyecto')}")
            av = aviso_comuna(r["nombre"], r["proyecto"])
            if av:
                print(av)

    if res["aproximados"]:
        print("\n≈ APROXIMADOS  (el nombre del listado no calza exacto; revisa que sea el proyecto correcto)")
        for r in res["aproximados"]:
            print(f"  - {linea_proyecto(r['proyecto'], datos_extra)}   (parecido {r['parecido']:.0%})")
            print(f"      listado : {r['nombre']}")
            print(f"      SUBDERE : {r['proyecto'].get('nombre_proyecto')}")
            av = aviso_comuna(r["nombre"], r["proyecto"])
            if av:
                print(av)

    if res["ambiguos"]:
        print("\n⚠ AMBIGUOS  (hay varios proyectos con ese mismo nombre — NO se asignan)")
        for r in res["ambiguos"]:
            print(f"  - {r['nombre']}")
            for p in r["proyectos"]:
                print(f"      · {linea_proyecto(p, datos_extra)}  | postulación {anio_postulacion(p)}")

    if res["sin_coincidencia"]:
        print("\n✘ SIN COINCIDENCIA  (no encontré un proyecto con ese nombre)")
        for r in res["sin_coincidencia"]:
            print(f"  - {r['nombre']}")
            if r["mejor"]:
                print(f"      lo más parecido ({r['mejor'][0]:.0%}): {r['mejor'][1].get('id_proyecto')} | {r['mejor'][1].get('nombre_proyecto')}")


def mostrar_otros_con_el_evento(proyectos, datos_extra, ids_a_asignar):
    """Proyectos que YA tienen este evento pero NO están en el listado (no se tocan)."""
    por_id = {p["id_proyecto"]: p for p in proyectos if p.get("id_proyecto")}
    otros = [i for i, d in datos_extra.items()
             if (d or {}).get("evento") == EVENTO_A_ASIGNAR and i not in ids_a_asignar]
    if otros:
        print(f"\nℹ Hay {len(otros)} proyecto(s) que YA tienen el evento '{EVENTO_A_ASIGNAR}' y NO están en tu listado")
        print("  (no los modifico; si no corresponden, se pueden corregir en 'Datos adicionales'):")
        for i in otros:
            p = por_id.get(i, {})
            print(f"  - {i} | {p.get('comuna', '?')} | {p.get('nombre_proyecto', '(no está en el listado actual de proyectos)')}")


def preguntar(texto) -> bool:
    return input(f"\n{texto} (s/n): ").strip().lower() in ("s", "si", "sí", "y", "yes")


# ----------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="solo muestra el resultado; no cambia nada")
    ap.add_argument("--lista", help="archivo de texto con los nombres (uno por línea) en vez del listado incluido")
    args = ap.parse_args(argv)

    nombres = leer_listado(args.lista)
    print(f"Listado: {len(nombres)} proyectos para el evento '{EVENTO_A_ASIGNAR}'.")

    print("Conectando con Google Drive...")
    servicio = obtener_servicio_drive()
    proyectos = cargar_proyectos(servicio)
    datos_extra = leer_json_drive(servicio, DATOS_EXTRA_FILE_ID)
    print(f"Proyectos cargados: {len(proyectos)}")

    res = buscar(nombres, proyectos)
    mostrar_resumen(res, datos_extra, len(nombres))

    a_asignar = [r["proyecto"] for r in res["exactos"]]
    if args.simular:
        mostrar_otros_con_el_evento(proyectos, datos_extra, {p["id_proyecto"] for p in a_asignar + [r["proyecto"] for r in res["aproximados"]]})
        print("\n[Simulación] No se cambió nada.")
        return

    if res["aproximados"] and preguntar(f"¿Incluir también las {len(res['aproximados'])} coincidencias APROXIMADAS (después de revisarlas arriba)?"):
        a_asignar += [r["proyecto"] for r in res["aproximados"]]

    # Un mismo proyecto no debería aparecer dos veces
    vistos, unicos = set(), []
    for p in a_asignar:
        if p["id_proyecto"] not in vistos:
            vistos.add(p["id_proyecto"]); unicos.append(p)
    a_asignar = unicos

    mostrar_otros_con_el_evento(proyectos, datos_extra, vistos)

    if not a_asignar:
        print("\nNo hay proyectos para asignar. No se hicieron cambios.")
        return

    nuevos = sum(1 for p in a_asignar if (datos_extra.get(p["id_proyecto"], {}) or {}).get("evento") != EVENTO_A_ASIGNAR)
    print(f"\nSe asignará '{EVENTO_A_ASIGNAR}' a {len(a_asignar)} proyecto(s) ({nuevos} cambian, {len(a_asignar) - nuevos} ya lo tenían).")
    if not preguntar("¿Aplicar estos cambios en Drive?"):
        print("Cancelado. No se hicieron cambios.")
        return

    # Respaldo local ANTES de escribir
    RESPALDOS_DIR.mkdir(exist_ok=True)
    respaldo = RESPALDOS_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    respaldo.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo guardado en: {respaldo}")

    for p in a_asignar:
        entrada = datos_extra.get(p["id_proyecto"], {}) or {}
        entrada["evento"] = EVENTO_A_ASIGNAR
        datos_extra[p["id_proyecto"]] = entrada
    escribir_json_drive(servicio, DATOS_EXTRA_FILE_ID, datos_extra)
    print(f"\nListo. Evento '{EVENTO_A_ASIGNAR}' asignado a {len(a_asignar)} proyecto(s) en Drive.")
    print("Recarga el dashboard (Cmd+Shift+R) para ver los cambios.")


if __name__ == "__main__":
    main()
