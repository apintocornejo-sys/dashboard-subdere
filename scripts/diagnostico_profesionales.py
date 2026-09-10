"""
Diagnóstico: revisa el archivo de datos adicionales REAL en Drive y el
listado de proyectos REAL, y muestra exactamente:
  1. Cuántos proyectos no tienen "profesional" guardado en Drive todavía
  2. De esos, cuáles combinaciones de Programa + Comuna aparecen (para saber
     si falta una regla, o si simplemente falta correr el backfill/agente)

Uso:
    python3 scripts/diagnostico_profesionales.py
"""

import sys
import json
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reglas_profesionales import calcular_profesional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def main():
    proyectos = json.loads(PROYECTOS_JSON.read_text(encoding="utf-8"))["proyectos"]

    print("Conectando con Drive para leer el estado REAL de datos adicionales...")
    creds = obtener_credenciales()
    service = build("drive", "v3", credentials=creds)
    contenido = service.files().get_media(fileId=DATOS_EXTRA_FILE_ID).execute()
    datos_extra = json.loads(contenido.decode("utf-8")) if contenido else {}

    sin_asignar_en_drive = []
    for p in proyectos:
        id_proyecto = p.get("id_proyecto")
        entrada = datos_extra.get(id_proyecto, {})
        if not entrada.get("profesional"):
            sin_asignar_en_drive.append(p)

    print(f"\nTotal proyectos: {len(proyectos)}")
    print(f"Sin 'profesional' guardado en Drive ahora mismo: {len(sin_asignar_en_drive)}\n")

    # De los que están sin asignar en Drive, ¿la regla SÍ tendría una respuesta?
    # (si sí, es que falta correr el backfill/agente; si no, falta ajustar la regla)
    regla_si_resolveria = Counter()
    regla_no_resuelve = Counter()

    for p in sin_asignar_en_drive:
        programa = p.get("programa")
        comuna = p.get("comuna")
        resultado = calcular_profesional(programa, comuna)
        clave = (programa, comuna if resultado is None else None)
        if resultado:
            regla_si_resolveria[(programa,)] += 1
        else:
            regla_no_resuelve[(programa, comuna)] += 1

    if regla_si_resolveria:
        total = sum(regla_si_resolveria.values())
        print(f"⚠️  {total} proyectos SÍ tienen regla (falta correr el backfill o el agente):")
        for (programa,), n in regla_si_resolveria.most_common():
            print(f"    {n:>5}  programa={programa!r}")

    if regla_no_resuelve:
        total = sum(regla_no_resuelve.values())
        print(f"\n❌ {total} proyectos NO tienen ninguna regla que aplique (falta agregar la regla):")
        for (programa, comuna), n in regla_no_resuelve.most_common(30):
            print(f"    {n:>5}  programa={programa!r:60}  comuna={comuna!r}")


if __name__ == "__main__":
    main()
