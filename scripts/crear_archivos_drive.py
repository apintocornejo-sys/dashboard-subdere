"""
Crea (una sola vez) los archivos de Google Drive que usan las pestañas nuevas del dashboard y deja sus ID
escritos donde corresponde:

    visitas.json           -> Despliegue Territorial (visitas del calendario; parte con para_subir_a_drive/visitas.json)  -> docs/index.html
    visitas_manuales.json  -> Despliegue Territorial (registros ingresados a mano)   -> docs/index.html
    rendiciones.json       -> Rendiciones (lo escribe el agente)                      -> docs/index.html y scripts/rendiciones_financiero.py

Los archivos nuevos se crean PRIVADOS (solo tu cuenta): el dashboard exige iniciar sesión con Google y solo lo ve quien
tenga permiso (ver scripts/acceso_dashboard.py). Si ya existe uno con ese nombre, NO crea otro: usa el existente.
Es seguro volver a ejecutarlo.

    python3 scripts/crear_archivos_drive.py
    ./scripts/publicar_semana.sh     (o git add / commit / push)
"""
import io
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
HTML = BASE_DIR / "docs" / "index.html"
MODULO_RENDICIONES = BASE_DIR / "scripts" / "rendiciones_financiero.py"
VISITAS_LOCAL = BASE_DIR / "para_subir_a_drive" / "visitas.json"                       # el que genera visitas_desde_calendario.py
VISITAS_INICIAL = BASE_DIR / "para_subir_a_drive" / "visitas_snapshot_inicial.json"      # copia de las visitas que iban dentro de la página
PRIVADO = True      # los archivos nuevos NO se comparten con "cualquiera con el enlace"


def _contenido_visitas() -> bytes:
    for ruta in (VISITAS_LOCAL, VISITAS_INICIAL):
        if ruta.exists():
            return ruta.read_bytes()
    return b'{"visitas": []}'


ARCHIVOS = [
    # (nombre en Drive, contenido inicial, [(archivo a editar, marcador a reemplazar)])
    ("visitas.json", _contenido_visitas, [(HTML, '"PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_VISITAS"')]),
    ("visitas_manuales.json", b'{"entradas": []}', [(HTML, '"PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_VISITAS_MANUALES"')]),
    ("rendiciones.json", b'{"proyectos": []}', [(HTML, '"PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_RENDICIONES"'),
                                                (MODULO_RENDICIONES, '"PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_RENDICIONES"')]),
]


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
            creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), DRIVE_SCOPES).run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds)


def asegurar_archivo(servicio, nombre: str, contenido: bytes) -> tuple:
    """Devuelve (id, creado). Si ya existe uno con ese nombre, usa el existente."""
    from googleapiclient.http import MediaIoBaseUpload
    existentes = servicio.files().list(q=f"name='{nombre}' and trashed=false", fields="files(id,name)").execute().get("files", [])
    if existentes:
        return existentes[0]["id"], False
    if callable(contenido):
        contenido = contenido()
    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype="application/json")
    archivo = servicio.files().create(body={"name": nombre, "mimeType": "application/json"}, media_body=media, fields="id").execute()
    if not PRIVADO:
        servicio.permissions().create(fileId=archivo["id"], body={"role": "reader", "type": "anyone"}).execute()
    return archivo["id"], True


def aplicar(file_id: str, ruta: Path, marcador: str) -> str:
    if not ruta.exists():
        return f"no existe {ruta.name}"
    texto = ruta.read_text(encoding="utf-8")
    if texto.count(marcador) == 1:
        ruta.write_text(texto.replace(marcador, f'"{file_id}"'), encoding="utf-8")
        return f"ID escrito en {ruta.name}"
    return f"{ruta.name}: ya estaba configurado (no se toca)"


def main():
    servicio = obtener_servicio_drive()
    for nombre, contenido, destinos in ARCHIVOS:
        file_id, creado = asegurar_archivo(servicio, nombre, contenido)
        print(f"{nombre}: {'creado (privado)' if creado else 'ya existía, uso el existente'} (ID {file_id})")
        for ruta, marcador in destinos:
            print("   -", aplicar(file_id, ruta, marcador))
    print("\nListo. Ahora publica los cambios a GitHub.")


if __name__ == "__main__":
    main()
