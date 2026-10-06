"""
Crea en Google Drive el archivo "visitas_manuales.json" donde la pestaña "Despliegue Territorial"
guarda los registros ingresados a mano, lo comparte como "Cualquiera con el enlace: lector"
(igual que los demás archivos del dashboard) y, con --aplicar, deja su ID escrito en docs/index.html.

Se ejecuta UNA sola vez:
    python3 scripts/crear_archivo_visitas_manuales.py --aplicar
    ./scripts/publicar_semana.sh

Opciones:
    --carpeta ID   crea el archivo dentro de esa carpeta de Drive (por ejemplo la carpeta "IA")
    --aplicar      escribe el ID en docs/index.html (si no, solo lo muestra)
    --forzar       crear uno nuevo aunque ya exista uno con ese nombre
"""
import io
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
NOMBRE_ARCHIVO = "visitas_manuales.json"
HTML_PATH = BASE_DIR / "docs" / "index.html"
MARCADOR = '"PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_VISITAS_MANUALES"'


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


def crear_archivo(servicio, carpeta=None) -> str:
    from googleapiclient.http import MediaIoBaseUpload
    meta = {"name": NOMBRE_ARCHIVO, "mimeType": "application/json"}
    if carpeta:
        meta["parents"] = [carpeta]
    media = MediaIoBaseUpload(io.BytesIO(b'{"entradas": []}'), mimetype="application/json")
    archivo = servicio.files().create(body=meta, media_body=media, fields="id").execute()
    servicio.permissions().create(fileId=archivo["id"], body={"role": "reader", "type": "anyone"}).execute()
    return archivo["id"]


def aplicar_id(file_id: str, ruta_html: Path = None) -> bool:
    ruta_html = ruta_html or HTML_PATH
    html = ruta_html.read_text(encoding="utf-8")
    if html.count(MARCADOR) != 1:
        return False
    ruta_html.write_text(html.replace(MARCADOR, f'"{file_id}"'), encoding="utf-8")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args(argv)

    servicio = obtener_servicio_drive()
    existentes = servicio.files().list(q=f"name='{NOMBRE_ARCHIVO}' and trashed=false", fields="files(id,name)").execute().get("files", [])
    if existentes and not args.forzar:
        print(f"Ya existe un archivo '{NOMBRE_ARCHIVO}' en tu Drive (ID: {existentes[0]['id']}).")
        print("No creo otro para no duplicar. Si ese es el correcto, úsalo; si quieres crear uno nuevo, agrega --forzar.")
        if args.aplicar and aplicar_id(existentes[0]["id"]):
            print("Dejé ese ID escrito en docs/index.html.")
        return

    file_id = crear_archivo(servicio, args.carpeta)
    print(f"Archivo creado y compartido en lectura pública. ID: {file_id}")
    if args.aplicar:
        if aplicar_id(file_id):
            print("ID escrito en docs/index.html. Ahora publica: ./scripts/publicar_semana.sh")
        else:
            print(f"No pude escribirlo automáticamente (¿ya estaba configurado?). Reemplaza a mano en docs/index.html:\n"
                  f'  const VISITAS_MANUALES_FILE_ID = "{file_id}";')
    else:
        print(f'Pega este ID en docs/index.html:\n  const VISITAS_MANUALES_FILE_ID = "{file_id}";')


if __name__ == "__main__":
    main()
