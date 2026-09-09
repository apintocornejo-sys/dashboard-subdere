"""
Asigna "Profesional a cargo" a TODOS los proyectos existentes, según las
reglas de reglas_profesionales.py. Pensado para correr UNA VEZ ahora, para
dejar el dashboard al día con la nueva política de asignación.

De ahí en adelante, el agente semanal (agente_actualizacion.py) aplica las
mismas reglas automáticamente solo a proyectos nuevos, sin volver a tocar
los que ya tengan un profesional asignado (manual o automático).

Uso:
    python3 scripts/asignar_profesionales_backfill.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reglas_profesionales import calcular_profesional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

BASE_DIR = Path(__file__).resolve().parent.parent
PROYECTOS_JSON = BASE_DIR / "para_subir_a_drive" / "proyectos.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

DATOS_EXTRA_FILE_ID = "1oThL9AfQ1_3i_h676ORmL6MSAi58VF7Z"


def obtener_credenciales():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_PATH.exists():
                print(f"Falta {CLIENT_SECRET_PATH.name}. Revisa README_AGENTE.md.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def main():
    if not PROYECTOS_JSON.exists():
        print(f"No existe {PROYECTOS_JSON}. Corre primero el agente o el parser.")
        sys.exit(1)

    proyectos = json.loads(PROYECTOS_JSON.read_text(encoding="utf-8"))["proyectos"]

    print("Conectando con Google Drive (puede abrir el navegador para autorizar)...")
    creds = obtener_credenciales()
    service = build("drive", "v3", credentials=creds)

    print("Descargando datos adicionales actuales...")
    contenido = service.files().get_media(fileId=DATOS_EXTRA_FILE_ID).execute()
    datos_extra = json.loads(contenido.decode("utf-8")) if contenido else {}

    resumen = {}
    sin_regla = 0
    ya_tenian = 0

    for p in proyectos:
        id_proyecto = p.get("id_proyecto")
        if not id_proyecto:
            continue
        profesional = calcular_profesional(p.get("programa"), p.get("comuna"))

        entrada = datos_extra.get(id_proyecto, {})
        if profesional is None:
            sin_regla += 1
            continue

        entrada["profesional"] = profesional
        datos_extra[id_proyecto] = entrada
        resumen[profesional] = resumen.get(profesional, 0) + 1

    print("\nResumen de asignación:")
    for profesional, n in sorted(resumen.items(), key=lambda x: -x[1]):
        print(f"  {profesional}: {n} proyectos")
    print(f"  Sin regla aplicable (programa no contemplado o sin designar): {sin_regla} proyectos")

    print("\nSubiendo datos adicionales actualizados a Drive...")
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(datos_extra, ensure_ascii=False).encode("utf-8")), mimetype="application/json")
    service.files().update(fileId=DATOS_EXTRA_FILE_ID, media_body=media).execute()
    print("Listo. El dashboard ya debería reflejar las asignaciones al recargar.")


if __name__ == "__main__":
    main()
