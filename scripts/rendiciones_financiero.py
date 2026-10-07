"""
Rendiciones — informe "Resumen Financiero" de SUBDERE en Línea.

Qué hace:
  1. (en el agente) Con la MISMA sesión ya iniciada para descargar los proyectos, abre
     INFORMES -> "Resumen Financiero" -> "Cargar Informe" -> "Exportar Excel".
  2. Procesa ese Excel y calcula los saldos:
        Saldo Contable       = Monto Asignado  - Monto Contratado
        Saldo por Transferir = Monto Contratado - Total Transferido
        Saldo por Rendir     = columna del informe (o Total Transferido - Total Rendido)
  3. Sube el resultado a Drive (archivo rendiciones.json) para la pestaña "Rendiciones".

Uso manual (con un Excel ya descargado):
    python3 scripts/rendiciones_financiero.py --archivo data_raw/Resumen_Financiero_XXXX.xls
    python3 scripts/rendiciones_financiero.py --archivo ARCHIVO.xls --diagnostico   # solo muestra qué columnas reconoció
    python3 scripts/rendiciones_financiero.py --archivo ARCHIVO.xls --sin-subir     # procesa pero no sube a Drive

Las columnas se reconocen por su NOMBRE (sin importar tildes, mayúsculas ni signos), así que no
depende de su posición. Si falta alguna, lo avisa claramente y sigue con las demás.
"""
import io
import re
import sys
import json
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_BACKUP_DIR = BASE_DIR / "data_raw"
DRIVE_UPLOAD_DIR = BASE_DIR / "para_subir_a_drive"
RENDICIONES_FILE_ID = "1sCsHF4NxTFcIwRkCTTbUq6rf0_dSviBT"

ULTIMO_EXCEL = None   # lo deja descargar_en_sesion() para el paso siguiente (publicar)

# Campo -> nombres posibles de la columna (normalizados: minúsculas, sin tildes ni signos).
# Se prueba primero la igualdad exacta y, para nombres de 2+ palabras, también "contiene".
ALIAS = {
    "provincia": ["provincia"],
    "comuna": ["comuna asociacion", "comuna"],
    "programa": ["programa"],
    "subprograma": ["subprograma", "sub programa", "plan"],
    "id_proyecto": ["id proyecto", "id. proyecto", "codigo proyecto"],
    "nombre": ["nombre proyecto", "nombre del proyecto", "nombre iniciativa", "nombre", "proyecto", "descripcion proyecto", "glosa proyecto"],
    "monto_asignado": ["monto asignado", "total asignado", "aporte subdere asignado", "monto aprobado", "asignado"],
    "monto_contratado": ["monto contratado", "total contratado", "contratado"],
    "monto_vigente": ["monto vigente", "total vigente", "vigente"],
    "total_transferido": ["total transferido", "monto transferido", "total transferencias", "transferido"],
    "total_rendido": ["total rendido", "monto rendido", "total rendiciones", "rendido"],
    "saldo_por_rendir": ["saldo por rendir", "saldo x rendir", "saldo rendir", "por rendir"],
    "plazo_ejecucion": ["plazo ejecucion", "plazo de ejecucion", "plazo"],
    "fecha_postulacion": ["fecha postulacion", "fecha de postulacion"],
    "fecha_asignacion": ["fecha asignacion", "fecha de asignacion", "fecha aprobacion", "fecha de aprobacion", "fecha resolucion", "fecha convenio"],
    "fecha_inicio": ["fecha inicio", "fecha de inicio", "fecha inicio ejecucion", "fecha inicio obra"],
    "fecha_termino": ["fecha termino", "fecha de termino", "fecha termino proyecto", "fecha termino ejecucion", "fecha termino contrato"],
    # Opcionales (los usa el Modo Reunión si el informe las trae)
    "estado_real": ["estado real", "estado ejecucion", "estado proyecto", "estado"],
    "contrato_plataforma": ["con contrato en plataforma", "contrato en plataforma", "contrato plataforma"],
    # Columnas del Resumen Financiero real de SUBDERE en Línea que sirven para replicar el tablero
    "contratos_registrados": ["contratos registrados"],
    "contratos_ejecucion": ["contratos en ejecucion"],
    "avance_financiero": ["avance financiero"],
    "total_reintegros": ["total reintegros"],
    "modalidad_ejecucion": ["modalidad ejecucion"],
    "transf_anios_anteriores": ["transf anos anteriores"],
    "transf_anio_actual": ["transf ano actual"],
}
OBLIGATORIAS = ["id_proyecto", "comuna", "programa", "monto_asignado"]
CAMPOS_MONTO = ["monto_asignado", "monto_contratado", "monto_vigente", "total_transferido", "total_rendido", "saldo_por_rendir"]

PROVINCIAS = {"ELQUI": "Elqui", "LIMARI": "Limarí", "CHOAPA": "Choapa"}
COMUNA_A_PROVINCIA = {
    "LA SERENA": "Elqui", "COQUIMBO": "Elqui", "ANDACOLLO": "Elqui", "LA HIGUERA": "Elqui", "PAIGUANO": "Elqui", "PAIHUANO": "Elqui",
    "VICUÑA": "Elqui", "OVALLE": "Limarí", "COMBARBALÁ": "Limarí", "MONTE PATRIA": "Limarí", "PUNITAQUI": "Limarí",
    "RÍO HURTADO": "Limarí", "ILLAPEL": "Choapa", "CANELA": "Choapa", "LOS VILOS": "Choapa", "SALAMANCA": "Choapa",
}


# ----------------------------------------------------------------------
# Utilidades de lectura
# ----------------------------------------------------------------------
def norm(texto) -> str:
    n = unicodedata.normalize("NFKD", str(texto if texto is not None else ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in n if not unicodedata.combining(c)).lower()).strip()


def _celda(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def a_monto(v):
    """'$ 1.234.567' / '1.234.567' / '-500' / '(500)' -> entero; vacío o 'no aplica' -> None."""
    s = _celda(v)
    if not s or norm(s) in ("no aplica", "n a", "na", "s i", "sin informacion"):
        return None
    negativo = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    if re.search(r",\d{1,2}$", s):          # decimales a la chilena: 1.234,50
        s = s.split(",")[0]
    digitos = re.sub(r"\D", "", s)
    if not digitos:
        return None
    n = int(digitos)
    return -n if negativo else n


def a_porcentaje(v):
    """'85,3%' / '85.3' / '100 %' -> número tal como viene (85.3, 100.0); vacío -> None."""
    s = _celda(v).replace("%", "").strip()
    if not s or norm(s) in ("no aplica", "n a", "na"):
        return None
    if re.search(r"\d\.\d{3}(?!\d)", s) and "," in s:      # 1.234,5
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.\-]", "", s))
    except ValueError:
        return None


def a_fecha(v):
    """Devuelve 'YYYY-MM-DD' o None. Acepta 2026-08-12 y 12/08/2026."""
    s = _celda(v)
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def a_plazo_dias(v):
    """'60 días' -> 60 ; '6 meses' -> 180 ; 'no aplica' -> None."""
    s = norm(_celda(v))
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    n = int(m.group(1))
    return n * 30 if "mes" in s else n


def _puntaje_encabezado(valores) -> int:
    conocidos = {a for lista in ALIAS.values() for a in lista}
    return sum(1 for v in valores if norm(v) in conocidos)


def leer_texto(ruta: Path) -> str:
    """Decodifica el archivo SIN perder letras: UTF-8 (con o sin BOM) y, si no, Windows-1252/Latin-1.
    (SUBDERE guarda el Excel en una codificación antigua: leerlo como UTF-8 con errors="ignore" borraba las tildes.)"""
    crudo = Path(ruta).read_bytes()
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return crudo.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return crudo.decode("latin-1")


def leer_tabla(ruta: Path):
    """Lee el Excel de SUBDERE (tabla HTML con extensión .xls). Devuelve (encabezados, filas) como texto."""
    import pandas as pd
    try:
        tablas = pd.read_html(io.StringIO(leer_texto(ruta)))
    except Exception:
        try:
            tablas = pd.read_html(str(ruta))
        except Exception:
            tablas = [pd.read_excel(str(ruta), header=None)]       # por si algún día viene como Excel real
    tabla = max(tablas, key=lambda t: t.shape[0])

    # Candidatos a encabezado: las columnas (si ya son texto) y las primeras filas
    candidatos = []
    cols = [" ".join(str(p) for p in c if "Unnamed" not in str(p)) if isinstance(c, tuple) else str(c) for c in tabla.columns]
    candidatos.append((_puntaje_encabezado(cols), -1, cols))
    for i in range(min(6, len(tabla))):
        fila = [_celda(x) for x in tabla.iloc[i].tolist()]
        candidatos.append((_puntaje_encabezado(fila), i, fila))
    puntaje, idx, encabezados = max(candidatos, key=lambda t: (t[0], -t[1] if t[1] >= 0 else 1))
    filas = tabla.iloc[idx + 1:] if idx >= 0 else tabla
    return [str(h) for h in encabezados], [[_celda(x) for x in r] for r in filas.values.tolist()]


def mapear_columnas(encabezados):
    """Asocia cada campo con el índice de su columna. Devuelve (mapa, no_encontradas)."""
    normas = [norm(h) for h in encabezados]
    usado, mapa = set(), {}
    for campo, alias in ALIAS.items():
        encontrado = None
        for a in alias:                                           # 1) igualdad exacta
            for i, n in enumerate(normas):
                if n == a and i not in usado:
                    encontrado = i
                    break
            if encontrado is not None:
                break
        if encontrado is None:                                    # 2) "contiene" (solo alias de 2+ palabras)
            for a in alias:
                if len(a.split()) < 2:
                    continue
                for i, n in enumerate(normas):
                    if i not in usado and re.search(rf"\b{re.escape(a)}\b", n):
                        encontrado = i
                        break
                if encontrado is not None:
                    break
        if encontrado is not None:
            mapa[campo] = encontrado
            usado.add(encontrado)
    return mapa, [c for c in ALIAS if c not in mapa]


# ----------------------------------------------------------------------
# Procesamiento
# ----------------------------------------------------------------------
def cargar_nombres(base_dir: Path = BASE_DIR) -> dict:
    """id_proyecto -> nombre, tomado de proyectos.json (por si el informe financiero no trae el nombre)."""
    for ruta in (base_dir / "para_subir_a_drive" / "proyectos.json", base_dir / "docs" / "data" / "proyectos.json"):
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
            return {p["id_proyecto"]: p.get("nombre_proyecto") for p in data.get("proyectos", []) if p.get("id_proyecto")}
        except Exception:
            continue
    return {}


def procesar_tabla(encabezados, filas, nombres=None, ahora: datetime = None) -> dict:
    ahora = ahora or datetime.now()
    nombres = nombres or {}
    mapa, no_encontradas = mapear_columnas(encabezados)
    advertencias = []
    faltan_oblig = [c for c in OBLIGATORIAS if c not in mapa]
    if faltan_oblig:
        advertencias.append("No se encontró la columna: " + ", ".join(faltan_oblig))

    def g(fila, campo):
        i = mapa.get(campo)
        return fila[i] if i is not None and i < len(fila) else ""

    proyectos, vistos, duplicados = [], {}, 0
    for fila in filas:
        texto_fila = " ".join(fila).strip().lower()
        id_p = g(fila, "id_proyecto").strip()
        if not texto_fila or re.match(r"^(totales?|n[°º] ?proyectos)", texto_fila):
            continue
        if not id_p and not g(fila, "nombre").strip():
            continue
        if re.match(r"^(totales?|n[°º])", g(fila, "region") or g(fila, "provincia") or ""):
            continue

        rec = {"id_proyecto": id_p or None}
        comuna = g(fila, "comuna").strip().upper()
        rec["comuna"] = comuna or None
        prov = g(fila, "provincia").strip()
        rec["provincia"] = PROVINCIAS.get(norm(prov).upper()) or COMUNA_A_PROVINCIA.get(comuna) or (prov.title() if prov else None)
        rec["programa"] = g(fila, "programa").strip() or None
        rec["subprograma"] = g(fila, "subprograma").strip() or None
        rec["nombre"] = g(fila, "nombre").strip() or nombres.get(id_p) or None

        for campo in CAMPOS_MONTO:
            rec[campo] = a_monto(g(fila, campo))
        asig, contr, transf = rec["monto_asignado"], rec["monto_contratado"], rec["total_transferido"]
        rec["saldo_contable"] = asig - contr if asig is not None and contr is not None else None
        rec["saldo_por_transferir"] = contr - transf if contr is not None and transf is not None else None
        if rec["saldo_por_rendir"] is None and transf is not None and rec["total_rendido"] is not None:
            rec["saldo_por_rendir"] = transf - rec["total_rendido"]

        rec["plazo_ejecucion"] = a_plazo_dias(g(fila, "plazo_ejecucion"))
        rec["fecha_postulacion"] = a_fecha(g(fila, "fecha_postulacion"))
        rec["fecha_asignacion"] = a_fecha(g(fila, "fecha_asignacion"))
        fecha_inicio = a_fecha(g(fila, "fecha_inicio"))
        rec["fecha_termino"] = a_fecha(g(fila, "fecha_termino"))
        rec["termino_estimado"] = False
        if not rec["fecha_termino"] and rec["plazo_ejecucion"]:
            base = fecha_inicio or rec["fecha_asignacion"]
            if base:
                rec["fecha_termino"] = (datetime.strptime(base, "%Y-%m-%d") + timedelta(days=rec["plazo_ejecucion"])).strftime("%Y-%m-%d")
                rec["termino_estimado"] = True
        for campo in ("total_reintegros", "transf_anios_anteriores", "transf_anio_actual", "contratos_registrados", "contratos_ejecucion"):
            rec[campo] = a_monto(g(fila, campo))
        rec["avance_financiero"] = a_porcentaje(g(fila, "avance_financiero"))
        rec["modalidad_ejecucion"] = g(fila, "modalidad_ejecucion").strip() or None
        rec["estado_real"] = g(fila, "estado_real").strip() or None
        cp = norm(g(fila, "contrato_plataforma"))
        rec["contrato_plataforma"] = "SI" if cp in ("si", "s", "1", "true", "yes") else "NO" if cp in ("no", "n", "0", "false") else None
        rec["anio_aprobacion"] = int(rec["fecha_asignacion"][:4]) if rec["fecha_asignacion"] else None
        rec["anio_postulacion"] = int(rec["fecha_postulacion"][:4]) if rec["fecha_postulacion"] else None

        firma = json.dumps(rec, sort_keys=True, ensure_ascii=False)
        if id_p and firma in vistos:                  # fila idéntica repetida: se descarta
            duplicados += 1
            continue
        vistos[firma] = True
        proyectos.append({k: v for k, v in rec.items() if v is not None})

    ids = [p.get("id_proyecto") for p in proyectos if p.get("id_proyecto")]
    repetidos = len(ids) - len(set(ids))
    if repetidos:
        advertencias.append(f"{repetidos} fila(s) comparten Id. Proyecto con datos distintos (¿una por fuente de financiamiento?): se conservan todas.")
    if duplicados:
        advertencias.append(f"Se descartaron {duplicados} fila(s) idénticas repetidas.")
    for campo, texto in (("monto_contratado", "Monto Contratado"), ("monto_vigente", "Monto Vigente"), ("total_transferido", "Total Transferido")):
        if campo not in mapa:
            advertencias.append(f"El informe no trae la columna '{texto}': sus montos y saldos asociados quedan vacíos.")
    if "saldo_por_rendir" not in mapa and "total_rendido" not in mapa:
        advertencias.append("El informe no trae 'Saldo por Rendir' ni 'Total Rendido': el Saldo por Rendir queda vacío.")
    if "estado_real" not in mapa:
        advertencias.append("El informe no trae 'Estado Real': en el Modo Reunión, el gráfico de estados usa el estado del listado de proyectos y 'Sin Iniciar' no se puede calcular.")
    if "fecha_asignacion" not in mapa:
        advertencias.append("El informe no trae 'Fecha de Asignación': el filtro por esa fecha y el 'Año de Aprobación' quedan vacíos.")
    if "fecha_termino" not in mapa:
        if "fecha_inicio" in mapa or "fecha_asignacion" in mapa:
            advertencias.append("El informe no trae 'Fecha de Término': se estima como fecha de inicio (o de asignación) + plazo de ejecución.")
        else:
            advertencias.append("El informe no trae 'Fecha de Término' ni una fecha desde la cual calcularla (inicio o asignación): "
                                "el filtro por término y las alertas de plazo quedan sin datos.")

    return {
        "fecha_actualizacion": ahora.strftime("%Y-%m-%d"),
        "hora_actualizacion": ahora.strftime("%H:%M"),
        "total_proyectos": len(proyectos),
        "columnas_detectadas": {c: encabezados[i] for c, i in mapa.items()},
        "columnas_no_encontradas": no_encontradas,
        "advertencias": advertencias,
        "proyectos": proyectos,
    }


def procesar_excel(ruta_excel: Path, base_dir: Path = BASE_DIR, ahora: datetime = None) -> dict:
    encabezados, filas = leer_tabla(ruta_excel)
    return procesar_tabla(encabezados, filas, cargar_nombres(base_dir), ahora)


def escribir_json(payload: dict, base_dir: Path = BASE_DIR) -> Path:
    destino = base_dir / "para_subir_a_drive"
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "rendiciones.json"
    ruta.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return ruta


def es_utilizable(payload: dict) -> bool:
    """Evita subir a Drive un resultado vacío o sin las columnas básicas (se conserva la versión anterior)."""
    cols = payload.get("columnas_detectadas", {})
    return payload.get("total_proyectos", 0) > 0 and all(c in cols for c in OBLIGATORIAS)


# ----------------------------------------------------------------------
# Subida a Drive (mismo patrón que el agente: ID fijo, nunca se busca por nombre)
# ----------------------------------------------------------------------
def subir_a_drive(ruta_json: Path, obtener_credenciales, log=print):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if RENDICIONES_FILE_ID.startswith("PEGA_AQUI"):
        log("Rendiciones: falta configurar RENDICIONES_FILE_ID (ejecuta scripts/crear_archivos_drive.py). "
            "El archivo quedó en para_subir_a_drive/rendiciones.json.")
        return False
    service = build("drive", "v3", credentials=obtener_credenciales())
    media = MediaFileUpload(str(ruta_json), mimetype="application/json", resumable=False)
    service.files().update(fileId=RENDICIONES_FILE_ID, media_body=media).execute()
    log("Rendiciones: archivo actualizado en Drive correctamente.")
    return True


def publicar(log, obtener_credenciales, ruta_excel: Path = None, base_dir: Path = BASE_DIR):
    """Procesa el Resumen Financiero descargado en esta corrida y lo sube a Drive."""
    ruta_excel = ruta_excel or ULTIMO_EXCEL
    if not ruta_excel:
        log("Rendiciones: no se descargó el Resumen Financiero en esta corrida; se omite.")
        return False
    payload = procesar_excel(Path(ruta_excel), base_dir)
    for a in payload["advertencias"]:
        log(f"Rendiciones: aviso — {a}")
    if not es_utilizable(payload):
        log("Rendiciones: ERROR — el informe no trae las columnas básicas "
            f"({', '.join(OBLIGATORIAS)}). NO se sube a Drive (queda la versión anterior).")
        log(f"Rendiciones: columnas que sí reconocí: {payload['columnas_detectadas']}")
        log("Ejecuta: python3 scripts/rendiciones_financiero.py --archivo "
            f"{ruta_excel} --diagnostico   y pásame el resultado.")
        return False
    ruta_json = escribir_json(payload, base_dir)
    log(f"Rendiciones: {payload['total_proyectos']} proyectos procesados.")
    return subir_a_drive(ruta_json, obtener_credenciales, log)


# ----------------------------------------------------------------------
# Descarga con Playwright, en la MISMA sesión ya iniciada por el agente
# ----------------------------------------------------------------------
def _frames_con_texto(page, texto, exacto=False):
    salida = []
    for f in page.frames:
        try:
            if f.get_by_text(texto, exact=exacto).count() > 0:
                salida.append(f)
        except Exception:
            continue
    return salida


def _esperar_frame(page, texto, intentos=10, pausa=1000):
    for _ in range(intentos):
        fr = _frames_con_texto(page, texto)
        if fr:
            return fr[0]
        page.wait_for_timeout(pausa)
    return None


# El menú del portal son IMÁGENES con ID: el grupo INFORMES es #imenu3 y sus reportes son #imenu3_1, _5, _6 y _9.
# "Resumen Financiero" es probablemente el segundo (#imenu3_5), pero NO se asume: se prueba cada uno y se
# verifica por su contenido (el filtro "Fuente Financiamiento" solo lo tiene este informe).
GRUPO_INFORMES = "#imenu3"
ITEMS_INFORMES = [5, 6, 9, 1]
MARCA_RESUMEN_FINANCIERO = "Fuente Financiamiento"


def descargar_en_sesion(page, log, base_dir: Path = BASE_DIR) -> Path:
    """Con la sesión ya abierta: INFORMES -> Resumen Financiero -> Cargar Informe -> Exportar Excel."""
    global ULTIMO_EXCEL
    debug = base_dir / "debug"
    debug.mkdir(parents=True, exist_ok=True)

    def foto(nombre):
        try:
            page.screenshot(path=str(debug / f"rf_{nombre}.png"), full_page=True)
        except Exception:
            pass

    def falla(paso, extra=""):
        foto("error")
        for i, f in enumerate(page.frames):          # texto de cada frame, para diagnosticar sin adivinar
            try:
                (debug / f"rf_frame_{i}_{f.name or 'principal'}.txt").write_text(f.inner_text("body")[:3000], encoding="utf-8")
            except Exception:
                pass
        nombres = [f.name for f in page.frames]
        raise RuntimeError(f"{paso} {extra} Frames disponibles: {nombres}. Revisa debug/rf_*.png y debug/rf_frame_*.txt")

    log(f"Rendiciones: abriendo el grupo INFORMES ({GRUPO_INFORMES})...")
    try:
        page.click(GRUPO_INFORMES, timeout=10000)
    except Exception as e:
        falla(f"No pude abrir el grupo INFORMES ({GRUPO_INFORMES}).", f"Detalle: {e}.")
    page.wait_for_timeout(1500)
    foto("01_informes")

    # Reportes que ofrece el portal (por si cambian los números); se prueban primero los esperados
    try:
        existentes = page.evaluate("[...document.querySelectorAll('img[id^=\"imenu3_\"]')].map(e => e.id)")
    except Exception:
        existentes = []
    preferidos = [f"imenu3_{n}" for n in ITEMS_INFORMES]
    candidatos = [c for c in preferidos if not existentes or c in existentes] + [c for c in existentes if c not in preferidos]
    log(f"Rendiciones: reportes del grupo INFORMES: {existentes or '(no pude listarlos; uso los esperados)'}")

    frame = None
    for cid in candidatos:
        log(f"Rendiciones: probando #{cid}...")
        try:
            page.click(f"#{cid}", timeout=8000)
        except Exception as e:
            log(f"Rendiciones: no pude hacer clic en #{cid} ({e}).")
            continue
        page.wait_for_timeout(3000)
        candidato = _esperar_frame(page, MARCA_RESUMEN_FINANCIERO, intentos=6)
        foto(f"02_{cid}")
        if candidato is not None and _frames_con_texto(page, "Cargar Informe"):
            frame = candidato if candidato.get_by_text("Cargar Informe").count() > 0 else _frames_con_texto(page, "Cargar Informe")[0]
            log(f"Rendiciones: 'Resumen Financiero' encontrado en #{cid}.")
            break
        log(f"Rendiciones: #{cid} no es el Resumen Financiero; pruebo el siguiente.")
    if frame is None:
        falla("No encontré el informe 'Resumen Financiero' (con el filtro 'Fuente Financiamiento' y el botón 'Cargar Informe').",
              f"Probé: {candidatos}.")

    log("Rendiciones: cargando el informe (puede tardar)...")
    try:
        frame.get_by_text("Cargar Informe").first.click(timeout=10000)
    except Exception:
        frame.click("text=Cargar Informe", timeout=10000)
    try:
        frame.wait_for_selector("text=N° Proyectos", timeout=90000)
    except Exception:
        frame.wait_for_timeout(8000)
    foto("03_informe_cargado")

    log("Rendiciones: exportando a Excel...")
    try:
        with page.expect_download(timeout=120000) as info:
            frame.get_by_text("Exportar Excel").first.click(timeout=10000)
    except Exception as e:
        falla("No pude exportar el Excel del Resumen Financiero.", f"Detalle: {e}.")
    RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_BACKUP_DIR / f"Resumen_Financiero_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xls"
    info.value.save_as(dest)
    ULTIMO_EXCEL = dest
    log(f"Rendiciones: Excel descargado: {dest}")
    return dest


# ----------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", required=True, help="Excel del Resumen Financiero ya descargado")
    ap.add_argument("--diagnostico", action="store_true", help="solo muestra qué columnas reconoció (no escribe nada)")
    ap.add_argument("--sin-subir", action="store_true", help="genera para_subir_a_drive/rendiciones.json pero no lo sube a Drive")
    args = ap.parse_args(argv)

    encabezados, filas = leer_tabla(Path(args.archivo))
    payload = procesar_tabla(encabezados, filas, cargar_nombres())
    if args.diagnostico:
        print(f"Filas de datos leídas: {len(filas)} | proyectos procesados: {payload['total_proyectos']}")
        print("\nENCABEZADOS del informe (en orden):")
        for i, h in enumerate(encabezados):
            print(f"  {i:>2}. {h}")
        print("\nCOLUMNAS RECONOCIDAS (campo -> encabezado del informe):")
        for c, h in payload["columnas_detectadas"].items():
            print(f"  {c:<20} <- {h}")
        print("\nNO ENCONTRADAS:", ", ".join(payload["columnas_no_encontradas"]) or "(ninguna)")
        print("\nAVISOS:", *(payload["advertencias"] or ["(ninguno)"]), sep="\n  - ")
        return
    for a in payload["advertencias"]:
        print("Aviso:", a)
    if not es_utilizable(payload):
        sys.exit("El informe no trae las columnas básicas. Ejecuta con --diagnostico y revisa los encabezados.")
    ruta = escribir_json(payload)
    print(f"Listo: {payload['total_proyectos']} proyectos -> {ruta}")
    if not args.sin_subir:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import agente_actualizacion as ag
        subir_a_drive(ruta, ag.obtener_credenciales_drive, print)


if __name__ == "__main__":
    main()
