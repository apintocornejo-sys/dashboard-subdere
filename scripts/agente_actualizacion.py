"""
Agente de actualización semanal — SUBDERE Dashboard
=====================================================

Automatiza el flujo completo:
  1. Login en SUBDERE en Línea + descarga del Excel (Playwright)
  2. Procesa el Excel -> genera proyectos.json (reutiliza parse_y_publicar.py)
  3. Sube el proyectos.json a Google Drive, reemplazando el archivo existente
     (mismo ID de siempre -> el dashboard nunca deja de apuntar al lugar correcto)
  4. Deja el respaldo del Excel + cualquier cambio de código subido a GitHub

Uso normal (flujo completo automático):
    python3 scripts/agente_actualizacion.py

Uso de respaldo, si el paso 1 (descarga automática) falla y ya tienes el
Excel descargado a mano:
    python3 scripts/agente_actualizacion.py --archivo /ruta/al/Listado_Proyectos_XXXX.xls

======================================================================
CONFIGURACIÓN REQUERIDA (una sola vez, ver README.md sección "Agente"):

  1. Variables de entorno (archivo .env en la raíz del proyecto):
       SUBDERE_USUARIO=tu_usuario
       SUBDERE_CLAVE=tu_clave

  2. Un archivo client_secret.json (credencial OAuth tipo "App de escritorio"
     descargada de Google Cloud Console) en la raíz del proyecto.
     La primera vez que corras el agente, se abrirá tu navegador para que
     autorices el acceso a Drive; después queda guardado en token.json y
     no se te volverá a pedir.

  NUNCA subas .env, client_secret.json ni token.json a GitHub — ya están
  agregados a .gitignore.
======================================================================
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_BACKUP_DIR = BASE_DIR / "data_raw"
DRIVE_UPLOAD_DIR = BASE_DIR / "para_subir_a_drive"
LOG_FILE = BASE_DIR / "agente_log.txt"

DRIVE_FILE_ID = "1ZRi0TAbjIozOnZ00cbH9O68sX4Ejlds8"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

LOGIN_URL = "http://www.subdereenlinea.gov.cl/"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def cargar_env():
    """Carga variables desde .env sin depender de librerías externas."""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ----------------------------------------------------------------------
# PASO 1: Descarga automática desde SUBDERE en Línea
# ----------------------------------------------------------------------
def descargar_excel_subdere() -> Path:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    usuario = os.environ.get("SUBDERE_USUARIO")
    clave = os.environ.get("SUBDERE_CLAVE")
    if not usuario or not clave:
        raise RuntimeError(
            "Faltan SUBDERE_USUARIO / SUBDERE_CLAVE en tu archivo .env. "
            "Ver README.md sección 'Agente'."
        )

    RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    debug_dir = BASE_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        headless = os.environ.get("AGENTE_HEADLESS", "false").lower() != "false"
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        log("Abriendo el portal de SUBDERE en Línea...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("load", timeout=30000)

        page.screenshot(path=str(debug_dir / "01_pagina_inicial.png"), full_page=True)
        (debug_dir / "01_pagina_inicial.html").write_text(page.content(), encoding="utf-8")
        log(f"Debug: título de la página cargada = '{page.title()}' / URL final = {page.url}")

        try:
            page.fill('input[type="text"]', usuario, timeout=15000)
            page.fill('input[type="password"]', clave, timeout=15000)
        except Exception as e:
            page.screenshot(path=str(debug_dir / "02_error_login.png"), full_page=True)
            (debug_dir / "02_error_login.html").write_text(page.content(), encoding="utf-8")
            raise RuntimeError(
                f"No se encontraron los campos de login. Revisa debug/01_pagina_inicial.png "
                f"y debug/02_error_login.png para ver qué cargó realmente. Detalle: {e}"
            )
        page.click("text=Entrar")
        page.wait_for_timeout(2000)

        # Pantalla de selección de perfil (aparece si tienes más de un perfil activo)
        try:
            page.wait_for_selector("text=Selección de Perfiles", timeout=8000)
            log("Seleccionando perfil: Funcionario Técnico URS")
            # "Funcionario Técnico URS" es siempre la primera opción de la lista
            page.locator('input[type="radio"]').first.check()
            page.wait_for_timeout(500)
            page.click("text=Continuar")
            page.wait_for_timeout(2000)
        except PWTimeout:
            log("No apareció selección de perfiles (cuenta con un solo perfil activo).")

        page.screenshot(path=str(debug_dir / "03_tras_login.png"), full_page=True)
        (debug_dir / "03_tras_login.html").write_text(page.content(), encoding="utf-8")
        log(f"Debug: título tras login = '{page.title()}' / URL = {page.url}")

        # El menú lateral (MÓDULOS / INFORMES) vive en la página principal,
        # como íconos-imagen (no texto). El grupo "MÓDULOS" es #imenu1, y
        # "Presentación Proyectos" es el 3er ítem del grupo: #imenu1_5.
        log("Abriendo el grupo MÓDULOS...")
        page.click("#imenu1", timeout=10000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(debug_dir / "04_tras_click_modulos.png"), full_page=True)

        log("Haciendo clic en Presentación Proyectos...")
        page.click("#imenu1_5", timeout=10000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(debug_dir / "05_tras_click_presentacion.png"), full_page=True)

        # El contenido del módulo (filtros, tabla, botones) vive en un frame
        # anidado cuyo nombre puede variar según el módulo. En vez de asumir
        # un nombre fijo, buscamos el frame que realmente contiene el botón
        # "Cargar Proyectos".
        page.wait_for_timeout(2000)
        frame = None
        for _ in range(10):  # reintenta hasta 10 veces mientras el frame termina de cargar
            for f in page.frames:
                try:
                    if f.get_by_text("Cargar Proyectos").count() > 0:
                        frame = f
                        break
                except Exception:
                    continue
            if frame:
                break
            page.wait_for_timeout(1000)

        if frame is None:
            page.screenshot(path=str(debug_dir / "06_error_frame.png"), full_page=True)
            nombres = [f.name for f in page.frames]
            raise RuntimeError(
                f"No se encontró ningún frame con el botón 'Cargar Proyectos'. "
                f"Frames disponibles: {nombres}. Revisa debug/05_tras_click_presentacion.png"
            )

        (debug_dir / "07_frame_presentacion.html").write_text(frame.content(), encoding="utf-8")
        log(f"Frame de trabajo encontrado: '{frame.name}'")

        log("Cargando el listado de proyectos...")
        frame.click("text=Cargar Proyectos")
        frame.wait_for_timeout(4000)  # deja que la tabla termine de renderizar

        log("Exportando a Excel...")
        with page.expect_download(timeout=60000) as download_info:
            frame.click("text=Exportar Excel")
        download = download_info.value

        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = RAW_BACKUP_DIR / f"Listado_Proyectos_{fecha}.xls"
        download.save_as(dest)
        log(f"Excel descargado: {dest}")

        browser.close()
        return dest


# ----------------------------------------------------------------------
# PASO 2: Procesar el Excel -> proyectos.json
# ----------------------------------------------------------------------
def procesar_excel(ruta_excel: Path) -> Path:
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    import parse_y_publicar  # reutiliza el parser ya existente

    log(f"Procesando {ruta_excel.name}...")
    df = parse_y_publicar.parse_file(ruta_excel)

    DRIVE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    if ruta_excel.parent != RAW_BACKUP_DIR:
        backup_path = RAW_BACKUP_DIR / f"Listado_Proyectos_{today}.xls"
        backup_path.write_bytes(ruta_excel.read_bytes())

    cols = [c for c in parse_y_publicar.FIELDS_TO_PUBLISH if c in df.columns]
    import pandas as pd
    df_pub = df[cols].copy()
    df_pub = df_pub.where(pd.notnull(df_pub), None)

    payload = {
        "fecha_actualizacion": today,
        "total_proyectos": len(df_pub),
        "proyectos": json.loads(df_pub.to_json(orient="records", force_ascii=False)),
    }

    out_path = DRIVE_UPLOAD_DIR / "proyectos.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log(f"Procesado: {len(df_pub)} proyectos, actualizado al {today}")
    return out_path


# ----------------------------------------------------------------------
# PASO 3: Subir a Google Drive (reemplaza el archivo, mismo ID de siempre)
# ----------------------------------------------------------------------
def subir_a_drive(ruta_json: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log("Renovando token de acceso a Drive...")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                raise RuntimeError(
                    f"No se encontró {CLIENT_SECRET_PATH.name}. "
                    "Ver README.md sección 'Agente' para crearlo en Google Cloud Console."
                )
            log("Primera vez: se abrirá tu navegador para autorizar acceso a Drive...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    service = build("drive", "v3", credentials=creds)

    log(f"Subiendo nueva versión del archivo a Drive (ID {DRIVE_FILE_ID})...")
    media = MediaFileUpload(str(ruta_json), mimetype="application/json", resumable=False)
    service.files().update(fileId=DRIVE_FILE_ID, media_body=media).execute()
    log("Archivo actualizado en Drive correctamente.")


# ----------------------------------------------------------------------
# PASO 4: Respaldo en GitHub
# ----------------------------------------------------------------------
def publicar_en_github():
    log("Subiendo respaldo y cambios a GitHub...")
    result = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True)
    if not result.stdout.strip():
        log("No hay cambios nuevos que subir a GitHub.")
        return

    fecha = datetime.now().strftime("%Y-%m-%d")
    subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"Actualización automática {fecha}"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)
    log(f"Cambios subidos a GitHub ({fecha}).")


# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Agente de actualización semanal SUBDERE")
    parser.add_argument("--archivo", help="Ruta a un Excel ya descargado (omite el paso de descarga automática)")
    args = parser.parse_args()

    cargar_env()
    log("=" * 60)
    log("Iniciando flujo de actualización")

    try:
        if args.archivo:
            ruta_excel = Path(args.archivo)
            if not ruta_excel.exists():
                log(f"ERROR: no existe el archivo {ruta_excel}")
                sys.exit(1)
            log(f"Usando archivo entregado manualmente: {ruta_excel}")
        else:
            ruta_excel = descargar_excel_subdere()
    except Exception as e:
        log(f"ERROR en la descarga automática: {e}")
        log("Puedes descargar el Excel manualmente y volver a correr con:")
        log("  python3 scripts/agente_actualizacion.py --archivo /ruta/al/archivo.xls")
        sys.exit(1)

    try:
        ruta_json = procesar_excel(ruta_excel)
    except Exception as e:
        log(f"ERROR al procesar el Excel: {e}")
        sys.exit(1)

    try:
        subir_a_drive(ruta_json)
    except Exception as e:
        log(f"ERROR al subir a Drive: {e}")
        log("El archivo procesado sigue disponible en para_subir_a_drive/proyectos.json")
        log("para subirlo manualmente si prefieres, mientras resolvemos el error.")
        sys.exit(1)

    try:
        publicar_en_github()
    except Exception as e:
        log(f"ERROR al subir a GitHub: {e}")
        sys.exit(1)

    log("Flujo completo terminado sin errores. ✅")
    log("=" * 60)


if __name__ == "__main__":
    main()
