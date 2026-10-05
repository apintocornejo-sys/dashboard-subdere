"""
Asigna un EVENTO a los proyectos de un listado de nombres.

Cómo funciona:
  1. Lee los proyectos publicados en Drive (la misma fuente que usa el dashboard).
  2. Busca cada nombre del listado, ignorando tildes, mayúsculas, paréntesis,
     guiones y espacios de más. Si no hay coincidencia exacta, busca la más
     parecida (errores de tipeo) y la marca como "aproximada" para que la revises.
  3. Separa los resultados: los que YA tienen el evento, los NUEVOS, y los que
     tienen OTRO evento distinto (conflicto: nunca se reemplaza sin preguntarte).
  4. Te muestra el resumen completo, incluyendo los nombres del listado que NO
     están en el dashboard, y pregunta antes de cambiar nada.
  5. Guarda un respaldo local de "datos adicionales" y recién ahí escribe en Drive.

Uso (desde la carpeta del proyecto):
    python3 scripts/asignar_evento_listado.py ficha --simular    # solo mirar
    python3 scripts/asignar_evento_listado.py ficha              # aplicar (pregunta antes)
    python3 scripts/asignar_evento_listado.py tgr2026 --simular

  "ficha"   = Ficha Simplificada SUBDERE Catastrofe 2026   (usa scripts/listados/ficha.txt)
  "tgr2026" = Transferencia Gobierno Regional 2026         (usa scripts/listados/tgr2026.txt)

Para otro evento o listado:
    python3 scripts/asignar_evento_listado.py "FET 2022" --lista mi_listado.txt

Para uno o pocos proyectos, escribiendo el nombre directo (entre comillas):
    python3 scripts/asignar_evento_listado.py ficha --nombre "CATÁSTROFE - HABILITACIÓN ... COMUNA DE PUNITAQUI"
    (se puede repetir --nombre para varios proyectos)

Para un proyecto puntual que no calzó por nombre:
    # 1) buscarlo por palabras clave (muestra ID, año, evento actual y nombre):
    python3 scripts/asignar_evento_listado.py ficha --buscar andacollo caldera pozos
    # 2) asignarlo por su ID (pide confirmación igual que siempre):
    python3 scripts/asignar_evento_listado.py ficha --ids 1-C-2026-1234

Los listados son archivos de texto con un nombre de proyecto por línea.
"""

import sys
import io
import json
import re
import argparse
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LISTADOS_DIR = Path(__file__).resolve().parent / "listados"
PROYECTOS_JSON_LOCAL = BASE_DIR / "para_subir_a_drive" / "proyectos.json"
RESPALDOS_DIR = BASE_DIR / "data_raw"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_FILE_ID = "1ZRi0TAbjIozOnZ00cbH9O68sX4Ejlds8"           # proyectos.json
DATOS_EXTRA_FILE_ID = "1oThL9AfQ1_3i_h676ORmL6MSAi58VF7Z"     # datos adicionales

UMBRAL_APROXIMADO = 0.92   # parecido mínimo (0 a 1) para proponer una coincidencia aproximada
MARGEN_APROXIMADO = 0.02   # la mejor candidata debe superar a la segunda por al menos esto

# Mismos eventos que el formulario "Datos adicionales" del dashboard.
EVENTOS_VALIDOS = [
    "CHA 2022", "CSV 2024", "CUOTA CORE", "Emergencia Lluvias 2017", "EPS 2000 Millones",
    "FET 2021", "FET 2022", "FRC", "Transferencia Gobierno Regional 2024",
    "Transferencia Gobierno Regional 2025", "Transferencia Gobierno Regional 2026",
    "Transferencia Gobierno Regional 2026 AT", "SATE 2023", "SPD",
    "Ficha Simplificada SUBDERE Catastrofe 2026",
]
# Atajos para no escribir el nombre completo
ALIAS = {
    "ficha": "Ficha Simplificada SUBDERE Catastrofe 2026",
    "tgr2026": "Transferencia Gobierno Regional 2026",
}

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


def anio_del_evento(evento: str):
    """Año que termina el nombre del evento ('... 2026' -> 2026); None si no tiene."""
    m = re.findall(r"\b(20\d\d)\b", evento)
    return int(m[-1]) if m else None


def comunas_mencionadas(texto_norm: str) -> set:
    """Comunas que aparecen como palabra completa en un texto ya normalizado."""
    texto_norm = texto_norm.replace("paihuano", "paiguano")   # el nombre se escribe de dos formas
    return {c for c in COMUNAS if re.search(r"\b" + c.lower() + r"\b", texto_norm)}


def leer_listado(ruta) -> list:
    nombres = []
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        linea = linea.strip().lstrip("*•-").strip()
        if linea:
            nombres.append(linea)
    return nombres


def resolver_evento(texto: str) -> str:
    """Acepta un atajo (ficha, tgr2026) o el nombre exacto; valida que sea un evento real."""
    if texto.lower() in ALIAS:
        return ALIAS[texto.lower()]
    for e in EVENTOS_VALIDOS:
        if e.lower() == texto.lower():
            return e
    sugerencias = get_close_matches(texto, EVENTOS_VALIDOS + list(ALIAS), n=3, cutoff=0.5)
    msg = f"'{texto}' no es un evento válido del dashboard."
    if sugerencias:
        msg += "\n  ¿Quisiste decir: " + " | ".join(sugerencias) + " ?"
    msg += "\n  Eventos válidos: " + ", ".join(EVENTOS_VALIDOS)
    raise SystemExit(msg)


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


def puntaje_pistas(n_listado: str, n_proyecto: str) -> float:
    """Parecido para SUGERIR candidatos (solo orienta; nunca asigna): el mayor entre la similitud
    de texto y la fracción de palabras del listado que aparecen en el proyecto."""
    sm = SequenceMatcher(None, n_listado, n_proyecto)
    if sm.real_quick_ratio() < 0.45 or sm.quick_ratio() < 0.45:
        texto = 0.0
    else:
        texto = sm.ratio()
    palabras = set(n_listado.split())
    comunes = len(palabras & set(n_proyecto.split())) / len(palabras) if palabras else 0.0
    return max(texto, comunes)


def buscar(nombres: list, proyectos: list, anio_preferido=None) -> dict:
    """Devuelve {'exactos', 'aproximados', 'sin_coincidencia', 'ambiguos'} con el detalle."""
    con_id = [p for p in proyectos if p.get("id_proyecto")]
    indice = {}
    for p in con_id:
        indice.setdefault(normalizar(p.get("nombre_proyecto")), []).append(p)
    todos_norm = [(normalizar(p.get("nombre_proyecto")), p) for p in con_id]

    res = {"exactos": [], "aproximados": [], "sin_coincidencia": [], "ambiguos": []}
    pendientes = []

    # Pasada 1: coincidencias exactas (ignorando tildes, signos y mayúsculas)
    for nombre in nombres:
        n = normalizar(nombre)
        candidatos = indice.get(n, [])
        if len(candidatos) > 1 and anio_preferido:   # mismo nombre repetido: preferir el año del evento
            preferidos = [p for p in candidatos if anio_postulacion(p) == anio_preferido]
            candidatos = preferidos if preferidos else candidatos
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

    # Pasada 2: para los que quedaron sin calzar, la coincidencia más parecida (aproximada).
    # Se busca en TODOS los proyectos, de cualquier año.
    for nombre in pendientes:
        n = normalizar(nombre)
        mencionadas = comunas_mencionadas(n)
        puntajes = []
        for nombre_p, p in todos_norm:
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
            # Sin coincidencia: las 3 pistas más cercanas (de cualquier año) para que puedas identificarlo
            pistas = sorted(((puntaje_pistas(n, nombre_p), p) for nombre_p, p in todos_norm
                             if p["id_proyecto"] not in reservados),
                            key=lambda t: t[0], reverse=True)[:3]
            res["sin_coincidencia"].append({"nombre": nombre, "pistas": pistas})
    return res


def buscar_por_palabras(palabras: list, proyectos: list) -> list:
    """Proyectos cuyo nombre contiene TODAS las palabras (ignorando tildes y mayúsculas)."""
    tokens = [normalizar(w) for w in palabras if normalizar(w)]
    out = []
    for p in proyectos:
        if not p.get("id_proyecto"):
            continue
        nombre = normalizar(p.get("nombre_proyecto")) + " " + normalizar(p.get("comuna"))
        if all(t in nombre for t in tokens):
            out.append(p)
    return out


# ----------------------------------------------------------------------
# Presentación
# ----------------------------------------------------------------------
def evento_de(datos_extra, id_proyecto) -> str:
    return (datos_extra.get(id_proyecto, {}) or {}).get("evento", "") or ""


def linea_proyecto(p, datos_extra, evento):
    actual = evento_de(datos_extra, p["id_proyecto"])
    if actual == evento:
        marca = "  [ya tenía este evento]"
    elif actual:
        marca = f"  [⚠ ahora tiene: {actual}]"
    else:
        marca = "  [nuevo]"
    return f"{p['id_proyecto']} | {p.get('comuna')} | post. {anio_postulacion(p) or '?'} | {p.get('estado')}{marca}"


def aviso_comuna(nombre_listado, proyecto):
    """Alerta si la comuna que menciona el nombre del listado no coincide con la del proyecto."""
    mencionadas = comunas_mencionadas(normalizar(nombre_listado))
    comuna_p = normalizar(proyecto.get("comuna")).replace("paihuano", "paiguano")
    if len(mencionadas) == 1 and comuna_p and comuna_p not in {c.lower() for c in mencionadas}:
        return f"      ⚠ el listado menciona {list(mencionadas)[0]} pero el proyecto está en {proyecto.get('comuna')}"
    return None


def mostrar_resumen(res, datos_extra, evento, total_nombres):
    print("\n" + "=" * 78)
    print(f"RESULTADO DE LA BÚSQUEDA  ({total_nombres} nombres en el listado)")
    print("=" * 78)
    print(f"  ✔ Coincidencias exactas ............ {len(res['exactos'])}")
    print(f"  ≈ Coincidencias aproximadas ........ {len(res['aproximados'])}   (revisar)")
    print(f"  ⚠ Ambiguos (nombre repetido) ....... {len(res['ambiguos'])}")
    print(f"  ✘ NO están en el dashboard ......... {len(res['sin_coincidencia'])}")

    if res["exactos"]:
        print("\n✔ EXACTOS")
        for r in res["exactos"]:
            print(f"  - {linea_proyecto(r['proyecto'], datos_extra, evento)}")
            print(f"      {r['proyecto'].get('nombre_proyecto')}")
            av = aviso_comuna(r["nombre"], r["proyecto"])
            if av:
                print(av)

    if res["aproximados"]:
        print("\n≈ APROXIMADOS  (el nombre del listado no calza exacto; revisa que sea el proyecto correcto)")
        for r in res["aproximados"]:
            print(f"  - {linea_proyecto(r['proyecto'], datos_extra, evento)}   (parecido {r['parecido']:.0%})")
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
                print(f"      · {linea_proyecto(p, datos_extra, evento)}  | postulación {anio_postulacion(p)}")

    if res["sin_coincidencia"]:
        print("\n✘ NO ESTÁN EN EL DASHBOARD  (no encontré ningún proyecto con ese nombre)")
        for r in res["sin_coincidencia"]:
            print(f"  - {r['nombre']}")
            for puntaje, p in r["pistas"]:
                print(f"      pista ({puntaje:.0%}): {p['id_proyecto']} | {p.get('comuna')} | post. {anio_postulacion(p) or '?'} | {p.get('nombre_proyecto')}")
        print("\n  Si alguno de estos SÍ existe con otro nombre, asígnalo por su ID:")
        print("    python3 scripts/asignar_evento_listado.py <evento> --ids <ID>")
        print("  o búscalo por palabras:  --buscar palabra1 palabra2")


def mostrar_otros_con_el_evento(proyectos, datos_extra, evento, ids_del_listado):
    """Proyectos que YA tienen este evento pero NO están en el listado (no se tocan)."""
    por_id = {p["id_proyecto"]: p for p in proyectos if p.get("id_proyecto")}
    otros = [i for i, d in datos_extra.items() if (d or {}).get("evento") == evento and i not in ids_del_listado]
    if otros:
        print(f"\nℹ Hay {len(otros)} proyecto(s) que YA tienen el evento '{evento}' y NO están en tu listado")
        print("  (no los modifico; si no corresponden, se pueden corregir en 'Datos adicionales'):")
        for i in otros:
            p = por_id.get(i, {})
            print(f"  - {i} | {p.get('comuna', '?')} | {p.get('nombre_proyecto', '(ya no está en el listado actual de proyectos)')}")


def preguntar(texto) -> bool:
    return input(f"\n{texto} (s/n): ").strip().lower() in ("s", "si", "sí", "y", "yes")


# ----------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("evento", help='atajo ("ficha", "tgr2026") o nombre exacto del evento entre comillas')
    ap.add_argument("--simular", action="store_true", help="solo muestra el resultado; no cambia nada")
    ap.add_argument("--lista", help="archivo de texto con los nombres (uno por línea)")
    ap.add_argument("--nombre", action="append", metavar="NOMBRE",
                    help="nombre de un proyecto (entre comillas); se puede repetir. Reemplaza al archivo de listado")
    ap.add_argument("--buscar", nargs="+", metavar="PALABRA",
                    help="busca proyectos por palabras clave y los muestra (no cambia nada)")
    ap.add_argument("--ids", nargs="+", metavar="ID", help="asigna el evento a estos proyectos, por su ID")
    args = ap.parse_args(argv)

    evento = resolver_evento(args.evento)
    nombres, ruta_lista = [], None
    if args.nombre and not args.buscar and not args.ids:
        nombres = [n.strip() for n in args.nombre if n.strip()]
        ruta_lista = Path("(escrito en el comando)")
    elif not args.buscar and not args.ids:
        if args.lista:
            ruta_lista = Path(args.lista)
        elif args.evento.lower() in ALIAS:
            ruta_lista = LISTADOS_DIR / f"{args.evento.lower()}.txt"
        else:
            raise SystemExit("Para este evento indica el archivo de nombres con --lista archivo.txt "
                             "(o usa --ids / --buscar)")
        if not ruta_lista.exists():
            raise SystemExit(f"No encuentro el listado: {ruta_lista}")
        nombres = leer_listado(ruta_lista)
    print(f"Evento: '{evento}'")

    print("Conectando con Google Drive...")
    servicio = obtener_servicio_drive()
    proyectos = cargar_proyectos(servicio)
    datos_extra = leer_json_drive(servicio, DATOS_EXTRA_FILE_ID)
    print(f"Proyectos cargados: {len(proyectos)}")

    # ---- Modo búsqueda por palabras: solo muestra ----
    if args.buscar:
        hallados = buscar_por_palabras(args.buscar, proyectos)
        print(f"\nProyectos que contienen {' + '.join(args.buscar)}: {len(hallados)}")
        for p in hallados[:40]:
            actual = evento_de(datos_extra, p["id_proyecto"]) or "(sin evento)"
            print(f"  - {p['id_proyecto']} | {p.get('comuna')} | post. {anio_postulacion(p) or '?'} | {p.get('estado')} | evento: {actual}")
            print(f"      {p.get('nombre_proyecto')}")
        if len(hallados) > 40:
            print(f"  ... y {len(hallados) - 40} más (agrega más palabras para acotar)")
        if hallados:
            print(f"\nPara asignar '{evento}' a alguno: python3 scripts/asignar_evento_listado.py {args.evento} --ids <ID>")
        return

    # ---- Modo por ID: el listado son los proyectos indicados ----
    if args.ids:
        por_id = {p["id_proyecto"]: p for p in proyectos if p.get("id_proyecto")}
        faltan = [i for i in args.ids if i not in por_id]
        if faltan:
            raise SystemExit("No encuentro estos ID en el listado de proyectos: " + ", ".join(faltan))
        res = {"exactos": [{"nombre": i, "proyecto": por_id[i], "parecido": 1.0} for i in dict.fromkeys(args.ids)],
               "aproximados": [], "sin_coincidencia": [], "ambiguos": []}
        nombres = list(args.ids)
        print(f"Proyectos indicados por ID: {len(nombres)}")
    else:
        print(f"Listado: {len(nombres)} proyecto(s) ({ruta_lista.name}).")
        res = buscar(nombres, proyectos, anio_del_evento(evento))
    mostrar_resumen(res, datos_extra, evento, len(nombres))

    exactos = [r["proyecto"] for r in res["exactos"]]
    aprox = [r["proyecto"] for r in res["aproximados"]]
    ids_listado = {p["id_proyecto"] for p in exactos + aprox}

    if args.simular:
        # Vista previa del reparto (suponiendo que se incluyen los aproximados)
        todos = exactos + aprox
        ya = [p for p in todos if evento_de(datos_extra, p["id_proyecto"]) == evento]
        conf = [p for p in todos if evento_de(datos_extra, p["id_proyecto"]) not in ("", evento)]
        print(f"\nREPARTO: {len(todos) - len(ya) - len(conf)} nuevos | {len(ya)} ya lo tenían | {len(conf)} con OTRO evento (conflicto)")
        mostrar_otros_con_el_evento(proyectos, datos_extra, evento, ids_listado)
        print("\n[Simulación] No se cambió nada.")
        return

    a_considerar = list(exactos)
    if aprox and preguntar(f"¿Incluir también las {len(aprox)} coincidencias APROXIMADAS (después de revisarlas arriba)?"):
        a_considerar += aprox

    # Un mismo proyecto no debería aparecer dos veces
    vistos, unicos = set(), []
    for p in a_considerar:
        if p["id_proyecto"] not in vistos:
            vistos.add(p["id_proyecto"]); unicos.append(p)
    a_considerar = unicos
    mostrar_otros_con_el_evento(proyectos, datos_extra, evento, ids_listado)

    ya_tienen = [p for p in a_considerar if evento_de(datos_extra, p["id_proyecto"]) == evento]
    nuevos = [p for p in a_considerar if evento_de(datos_extra, p["id_proyecto"]) == ""]
    conflictos = [p for p in a_considerar if evento_de(datos_extra, p["id_proyecto"]) not in ("", evento)]

    # Conflictos: tienen OTRO evento. Nunca se reemplaza sin preguntar.
    reemplazar = []
    if conflictos:
        print(f"\n⚠ {len(conflictos)} proyecto(s) del listado YA tienen otro evento:")
        for p in conflictos:
            print(f"  - {p['id_proyecto']} | {p.get('comuna')} | tiene: {evento_de(datos_extra, p['id_proyecto'])}")
            print(f"      {p.get('nombre_proyecto')}")
        if preguntar(f"¿Reemplazar ese evento por '{evento}' en esos {len(conflictos)} proyectos? (n = dejarlos como están)"):
            reemplazar = conflictos

    a_escribir = nuevos + reemplazar
    print("\n" + "-" * 78)
    print(f"Se agregará '{evento}' a {len(nuevos)} proyecto(s) nuevo(s)"
          + (f" y se REEMPLAZARÁ el evento en {len(reemplazar)}" if reemplazar else "") + ".")
    print(f"Sin cambios: {len(ya_tienen)} ya lo tenían" + (f", {len(conflictos) - len(reemplazar)} se dejan con su otro evento" if conflictos else "") + ".")
    if not a_escribir:
        print("No hay nada que cambiar.")
        return
    if not preguntar("¿Aplicar estos cambios en Drive?"):
        print("Cancelado. No se hicieron cambios.")
        return

    # Respaldo local ANTES de escribir
    RESPALDOS_DIR.mkdir(exist_ok=True)
    respaldo = RESPALDOS_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    respaldo.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo guardado en: {respaldo}")

    for p in a_escribir:
        entrada = datos_extra.get(p["id_proyecto"], {}) or {}
        entrada["evento"] = evento
        datos_extra[p["id_proyecto"]] = entrada
    escribir_json_drive(servicio, DATOS_EXTRA_FILE_ID, datos_extra)
    print(f"\nListo. Evento '{evento}' asignado a {len(a_escribir)} proyecto(s) en Drive.")
    print("Recarga el dashboard (Cmd+Shift+R) para ver los cambios.")


if __name__ == "__main__":
    main()
