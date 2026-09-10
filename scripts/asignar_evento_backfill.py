"""
Asigna el evento "Transferencia Gobierno Regional 2026 AT" a todos los
proyectos cuyo nombre comience con "ASISTENCIA TÉCNICA PARA CATASTRO PMU Y
PMB, AFECTADOS POR..." (hay uno por comuna, con el mismo texto base).

Uso:
    python3 scripts/asignar_evento_backfill.py
"""

import sys
import json
import io
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

BASE_DIR = Path(__file__).resolve().parent.parent
PROYECTOS_JSON = BASE_DIR / "para_subir_a_drive" / "proyectos.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DATOS_EXTRA_FILE_ID = "1oThL9AfQ1_3i_h676ORmL6MSAi58VF7Z"

PREFIJO_NOMBRE = "ASISTENCIA TÉCNICA PARA CATASTRO PMU Y PMB, AFECTADOS POR"
EVENTO_A_ASIGNAR = "Transferencia Gobierno Regional 2026 AT"


def obtener_credenciales():
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
    return creds


def main():
    proyectos = json.loads(PROYECTOS_JSON.read_text(encoding="utf-8"))["proyectos"]

    coincidencias = [
        p for p in proyectos
        if PREFIJO_NOMBRE.upper() in str(p.get("nombre_proyecto", "")).upper()
    ]
    print(f"Proyectos que coinciden con el nombre: {len(coincidencias)}")
    for p in coincidencias:
        print(f"  - {p.get('id_proyecto')}  |  {p.get('comuna')}  |  {p.get('nombre_proyecto')}")

    if not coincidencias:
        print("No se encontró ningún proyecto con ese nombre. No se hicieron cambios.")
        return

    print("\nConectando con Google Drive...")
    creds = obtener_credenciales()
    service = build("drive", "v3", credentials=creds)

    contenido = service.files().get_media(fileId=DATOS_EXTRA_FILE_ID).execute()
    datos_extra = json.loads(contenido.decode("utf-8")) if contenido else {}

    for p in coincidencias:
        id_proyecto = p.get("id_proyecto")
        entrada = datos_extra.get(id_proyecto, {})
        entrada["evento"] = EVENTO_A_ASIGNAR
        datos_extra[id_proyecto] = entrada

    media = MediaIoBaseUpload(
        io.BytesIO(json.dumps(datos_extra, ensure_ascii=False).encode("utf-8")),
        mimetype="application/json",
    )
    service.files().update(fileId=DATOS_EXTRA_FILE_ID, media_body=media).execute()
    print(f"\nListo. Evento '{EVENTO_A_ASIGNAR}' asignado a {len(coincidencias)} proyecto(s).")


if __name__ == "__main__":
    main()
