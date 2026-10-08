"""
Administra QUIÉN puede entrar al dashboard.

El dashboard pide iniciar sesión con Google y lee los datos desde archivos PRIVADOS de Drive: entra solo quien tenga
permiso sobre esos archivos. Autorizar a alguien = darle permiso en Drive; quitarle el acceso = quitárselo. La
seguridad la aplica Google, no la página.

    python3 scripts/acceso_dashboard.py estado                      # cada archivo: dueño, si es público y con quién se comparte
    python3 scripts/acceso_dashboard.py proteger                    # quita el acceso público ("cualquiera con el enlace")
    python3 scripts/acceso_dashboard.py autorizar persona@dominio.cl                 # puede VER el dashboard (lector)
    python3 scripts/acceso_dashboard.py autorizar persona@dominio.cl --rol editor    # además puede cargar Datos adicionales y visitas
    python3 scripts/acceso_dashboard.py quitar persona@dominio.cl   # le quita todo acceso
    python3 scripts/acceso_dashboard.py listar                      # quién tiene acceso (por persona)
    python3 scripts/acceso_dashboard.py revertir                    # EMERGENCIA: vuelve a lectura pública (modo anterior)
    python3 scripts/acceso_dashboard.py repo                        # revisa si el repositorio de GitHub tiene datos o credenciales
    python3 scripts/acceso_dashboard.py repo --corregir             # los saca del repositorio (no los borra de tu computador)

Roles:
    lector  -> lector de todos los archivos (ve el dashboard completo, no modifica nada)
    editor  -> lector de todos + EDITOR de "Datos adicionales" y "Visitas manuales" (lo único que se carga a mano)
Los demás archivos los actualiza solo el agente (dueño de los archivos); nadie más puede modificarlos.

La persona necesita una cuenta de Google (Gmail o institucional). No se envían correos de invitación.
"""
import re
import sys
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"
TOKEN_PATH = BASE_DIR / "token.json"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
INDEX_HTML = BASE_DIR / "docs" / "index.html"

NOMBRES = {
    "DRIVE_FILE_ID": "Proyectos",
    "DATOS_EXTRA_FILE_ID": "Datos adicionales",
    "HISTORIAL_ESTADOS_FILE_ID": "Trazabilidad",
    "VISITAS_FILE_ID": "Visitas (calendario)",
    "VISITAS_MANUALES_FILE_ID": "Visitas manuales",
    "RENDICIONES_FILE_ID": "Rendiciones",
}
EDITABLES = {"DATOS_EXTRA_FILE_ID", "VISITAS_MANUALES_FILE_ID"}      # lo que carga a mano un editor
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def archivos_de_datos(html_path: Path = None) -> list:
    """[(constante, nombre, id)] leídos de docs/index.html; se omiten los que aún no tienen ID."""
    html = (html_path or INDEX_HTML).read_text(encoding="utf-8")
    salida = []
    for const, nombre in NOMBRES.items():
        m = re.search(rf'const {const} = "([^"]+)"', html)
        if m and not m.group(1).startswith("PEGA_AQUI"):
            salida.append((const, nombre, m.group(1)))
    return salida


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


def _msg(e) -> str:
    return str(getattr(e, "reason", None) or e)[:160]


def leer(servicio, file_id: str) -> dict:
    """Dueño, si puedes compartirlo y la lista de permisos (si tu cuenta puede verla)."""
    meta = servicio.files().get(fileId=file_id, fields="id,name,owners(emailAddress),capabilities(canShare)").execute()
    info = {"id": file_id, "nombre_drive": meta.get("name"), "dueno": ((meta.get("owners") or [{}])[0]).get("emailAddress", "?"),
            "puede_compartir": bool((meta.get("capabilities") or {}).get("canShare")), "permisos": None, "error_permisos": None}
    try:
        info["permisos"] = servicio.permissions().list(fileId=file_id, fields="permissions(id,type,role,emailAddress)").execute().get("permissions", [])
    except Exception as e:                                           # una cuenta que no puede compartir no ve los permisos
        info["error_permisos"] = _msg(e)
    return info


def es_publico(info: dict) -> bool:
    return any(p.get("type") == "anyone" for p in (info["permisos"] or []))


def preguntar(texto: str) -> bool:
    return input(f"\n{texto} (s/n): ").strip().lower() in ("s", "si", "sí", "y", "yes")


# ----------------------------------------------------------------------
def cmd_estado(servicio, archivos, **_):
    print("ARCHIVOS DE DATOS DEL DASHBOARD\n")
    hay_publicos = False
    for const, nombre, fid in archivos:
        i = leer(servicio, fid)
        if i["permisos"] is None:
            print(f"- {nombre}: dueño {i['dueno']} · no puedo ver sus permisos con esta cuenta ({i['error_permisos']})")
            continue
        publico = es_publico(i)
        hay_publicos |= publico
        personas = [f"{p['emailAddress']} ({'editor' if p['role'] in ('writer', 'owner') else 'lector'})" for p in i["permisos"] if p.get("type") == "user"]
        print(f"- {nombre}: dueño {i['dueno']} · {'⚠ PÚBLICO (cualquiera con el enlace)' if publico else 'privado'}")
        print("    con acceso: " + (", ".join(personas) if personas else "(solo el dueño)"))
    print("\n" + ("⚠ Hay archivos públicos: cualquiera con el enlace puede leerlos. Para cerrarlos: python3 scripts/acceso_dashboard.py proteger"
                  if hay_publicos else "✓ Ningún archivo es público: solo entra quien esté autorizado."))


def _aviso_no_verificables(desconocidos):
    print("\n⚠ ATENCIÓN: no pude verificar ni cambiar estos archivos con tu cuenta (probablemente son de otra cuenta):")
    for nombre, i in desconocidos:
        print(f"   - {nombre} (dueño: {i['dueno']}): ábrelo en Drive con esa cuenta → Compartir → Acceso general → 'Restringido'.")
    print("   Mientras no lo hagas, ese archivo PUEDE seguir siendo público. Después de cambiarlo, verifícalo con: estado")


def cmd_proteger(servicio, archivos, si=False, **_):
    pendientes, desconocidos = [], []
    for const, nombre, fid in archivos:
        i = leer(servicio, fid)
        if i["permisos"] is None:
            desconocidos.append((nombre, i))
        elif es_publico(i):
            pendientes.append((nombre, i))
    if not pendientes:
        print("Ningún archivo visible con esta cuenta es público.")
        if desconocidos:
            _aviso_no_verificables(desconocidos)
        else:
            print("✓ Todo privado.")
        return
    print("Se quitará el acceso público a: " + ", ".join(n for n, _ in pendientes))
    print("Después, el dashboard SOLO lo verá quien esté autorizado (autorizar). Tu cuenta y las ya autorizadas siguen entrando.")
    if not si and not preguntar("¿Continuar?"):
        print("No se cambió nada.")
        return
    for nombre, i in pendientes:
        try:
            for p in [p for p in i["permisos"] if p.get("type") == "anyone"]:
                servicio.permissions().delete(fileId=i["id"], permissionId=p["id"]).execute()
            print(f"  ✓ {nombre}: ahora es privado")
        except Exception as e:
            desconocidos.append((nombre, i))
            print(f"  ✗ {nombre}: no pude cambiarlo ({_msg(e)}).")
    if desconocidos:
        _aviso_no_verificables(desconocidos)


def cmd_autorizar(servicio, archivos, correo, rol="lector", **_):
    correo = correo.strip().lower()
    if not RE_CORREO.match(correo):
        sys.exit(f"'{correo}' no parece un correo válido.")
    print(f"Autorizando a {correo} como {rol.upper()}:")
    for const, nombre, fid in archivos:
        deseado = "writer" if (rol == "editor" and const in EDITABLES) else "reader"
        try:
            i = leer(servicio, fid)
            actual = next((p for p in (i["permisos"] or []) if p.get("type") == "user" and (p.get("emailAddress") or "").lower() == correo), None)
            if actual and actual["role"] in ("owner",):
                print(f"  = {nombre}: es el dueño")
            elif actual and actual["role"] == deseado:
                print(f"  = {nombre}: ya tenía acceso como {'editor' if deseado == 'writer' else 'lector'}")
            elif actual:
                servicio.permissions().update(fileId=fid, permissionId=actual["id"], body={"role": deseado}).execute()
                print(f"  ✓ {nombre}: rol cambiado a {'editor' if deseado == 'writer' else 'lector'}")
            else:
                servicio.permissions().create(fileId=fid, body={"type": "user", "role": deseado, "emailAddress": correo},
                                              sendNotificationEmail=False, fields="id").execute()
                print(f"  ✓ {nombre}: acceso como {'editor' if deseado == 'writer' else 'lector'}")
        except Exception as e:
            print(f"  ✗ {nombre}: no pude compartirlo ({_msg(e)}). Si el archivo es de otra cuenta, compártelo desde Drive (Compartir → agregar {correo}).")
    print("\nListo en Drive. No se le envió ningún correo; avísale tú.")
    print("IMPORTANTE: si tu aplicación de Google (Google Cloud Console → Pantalla de consentimiento de OAuth) está en estado 'Prueba',")
    print(f"agrega también a {correo} en 'Usuarios de prueba' (máximo 100); si no, Google no la dejará iniciar sesión.")


def cmd_quitar(servicio, archivos, correo, si=False, **_):
    correo = correo.strip().lower()
    if not si and not preguntar(f"¿Quitar TODO el acceso de {correo} al dashboard?"):
        print("No se cambió nada.")
        return
    for const, nombre, fid in archivos:
        try:
            i = leer(servicio, fid)
            propios = [p for p in (i["permisos"] or []) if p.get("type") == "user" and (p.get("emailAddress") or "").lower() == correo and p["role"] != "owner"]
            for p in propios:
                servicio.permissions().delete(fileId=fid, permissionId=p["id"]).execute()
            print(f"  {'✓' if propios else '='} {nombre}: " + ("acceso quitado" if propios else "no tenía acceso"))
        except Exception as e:
            print(f"  ✗ {nombre}: no pude cambiarlo ({_msg(e)})")


def cmd_listar(servicio, archivos, **_):
    por_persona = {}
    for const, nombre, fid in archivos:
        i = leer(servicio, fid)
        for p in (i["permisos"] or []):
            if p.get("type") == "user":
                por_persona.setdefault(p["emailAddress"].lower(), {})[nombre] = "editor" if p["role"] in ("writer", "owner") else "lector"
    if not por_persona:
        print("Nadie más tiene acceso (solo el dueño de los archivos).")
        return
    print(f"PERSONAS CON ACCESO ({len(por_persona)})\n")
    for correo, d in sorted(por_persona.items()):
        roles = set(d.values())
        resumen = "dueño/editor" if len(d) == len(archivos) and roles == {"editor"} else ("lector" if roles == {"lector"} else "mixto")
        edita = [n for n, r in d.items() if r == "editor"]
        print(f"- {correo}: {resumen}" + (f" (edita: {', '.join(edita)})" if edita and resumen != 'dueño/editor' else "") + f" · {len(d)} de {len(archivos)} archivos")


def cmd_revertir(servicio, archivos, si=False, **_):
    print("⚠ EMERGENCIA: vuelve a dejar los archivos como 'cualquiera con el enlace puede leer' (modo anterior, SIN protección).")
    print("   Para que el dashboard funcione así debes publicar también la versión anterior de index.html (cambiar ACCESO_PROTEGIDO a false).")
    if not si and not preguntar("¿Hacer públicos los archivos de datos?"):
        print("No se cambió nada.")
        return
    for const, nombre, fid in archivos:
        try:
            i = leer(servicio, fid)
            if i["permisos"] is not None and es_publico(i):
                print(f"  = {nombre}: ya era público")
                continue
            servicio.permissions().create(fileId=fid, body={"type": "anyone", "role": "reader"}, fields="id").execute()
            print(f"  ✓ {nombre}: público otra vez")
        except Exception as e:
            print(f"  ✗ {nombre}: no pude cambiarlo ({_msg(e)})")


SECRETOS = ("client_secret.json", "token.json")
RE_DATOS = re.compile(r"(^|/)(para_subir_a_drive|data_raw|debug)/|\.(xls|xlsx|csv)$|^[^/]+\.json$|^[^/]+\.html$", re.I)
REGLAS_GITIGNORE = ["client_secret.json", "token.json", "para_subir_a_drive/", "data_raw/", "debug/", "/subdere_datos_extra.json", "*.xls", "*.xlsx", "*.csv", ".env"]
PERMITIDOS = {"package.json", "package-lock.json"}


def archivos_sospechosos(archivos_git: list) -> list:
    """Archivos que el repositorio rastrea y que contienen datos o credenciales (docs/ y scripts/ son código: se permiten)."""
    sosp = []
    for a in archivos_git:
        base = a.rsplit("/", 1)[-1]
        if a.startswith(("docs/", "scripts/", ".github/")) or base in PERMITIDOS:
            if base not in SECRETOS:
                continue
        if base in SECRETOS:
            sosp.append((a, "CREDENCIAL"))
        elif RE_DATOS.search(a):
            sosp.append((a, "datos / posible copia del dashboard"))
    return sosp


def cmd_repo(servicio=None, archivos=None, corregir=False, **_):
    try:
        salida = subprocess.run(["git", "ls-files", "-z"], cwd=BASE_DIR, capture_output=True, text=True, check=True).stdout
    except Exception as e:
        sys.exit(f"No pude leer el repositorio de git ({_msg(e)}). Ejecuta esto desde la carpeta del proyecto.")
    sosp = archivos_sospechosos([a for a in salida.split("\0") if a])
    if not sosp:
        print("✓ El repositorio no rastrea archivos de datos ni credenciales.")
        return
    print(f"⚠ El repositorio rastrea {len(sosp)} archivo(s) que NO deberían estar en GitHub (si el repositorio es público, cualquiera los ve):\n")
    for a, motivo in sosp:
        print(f"   - {a}   [{motivo}]")
    if any(m == "CREDENCIAL" for _, m in sosp):
        print("\n🔴 Hay CREDENCIALES. Aunque las quites ahora, quedan en el historial de GitHub: revoca y vuelve a crear client_secret/token en Google Cloud Console.")
    print("\nEl historial anterior de git también conserva las versiones antiguas. Para borrarlas de verdad hay que reescribir el historial")
    print("(git filter-repo) o crear un repositorio nuevo; hacer privado el repositorio no sirve si usas GitHub Pages gratuito.")
    if not corregir:
        print("\nPara sacarlos del repositorio de ahora en adelante (sin borrarlos de tu computador):  python3 scripts/acceso_dashboard.py repo --corregir")
        return
    gi = BASE_DIR / ".gitignore"
    actual = gi.read_text(encoding="utf-8") if gi.exists() else ""
    faltan = [r for r in REGLAS_GITIGNORE if r not in {l.strip() for l in actual.splitlines()}]
    if faltan:
        gi.write_text(actual.rstrip("\n") + ("\n" if actual else "") + "# Datos y credenciales: nunca van a GitHub\n" + "\n".join(faltan) + "\n", encoding="utf-8")
    for a, _m in sosp:
        subprocess.run(["git", "rm", "--cached", "-q", "--", a], cwd=BASE_DIR, check=False)
    print(f"\n✓ Quité {len(sosp)} archivo(s) del seguimiento de git y actualicé .gitignore. Tus archivos locales siguen intactos.")
    print('Ahora publica el cambio:  git add -A && git commit -m "Sacar datos del repositorio" && git push')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estado")
    p = sub.add_parser("proteger"); p.add_argument("--si", action="store_true", help="no preguntar")
    p = sub.add_parser("autorizar"); p.add_argument("correo"); p.add_argument("--rol", choices=["lector", "editor"], default="lector")
    p = sub.add_parser("quitar"); p.add_argument("correo"); p.add_argument("--si", action="store_true", help="no preguntar")
    sub.add_parser("listar")
    p = sub.add_parser("repo"); p.add_argument("--corregir", action="store_true", help="sacar esos archivos del repositorio")
    p = sub.add_parser("revertir"); p.add_argument("--si", action="store_true", help="no preguntar")
    a = ap.parse_args(argv)
    if a.cmd == "repo":                       # no necesita conectarse a Drive
        return cmd_repo(corregir=a.corregir)
    archivos = archivos_de_datos()
    if not archivos:
        sys.exit("No encontré IDs de archivos en docs/index.html. Ejecuta esto desde la carpeta del proyecto.")
    servicio = obtener_servicio_drive()
    {"estado": cmd_estado, "proteger": cmd_proteger, "autorizar": cmd_autorizar, "quitar": cmd_quitar, "listar": cmd_listar, "revertir": cmd_revertir}[a.cmd](
        servicio, archivos, **{k: v for k, v in vars(a).items() if k != "cmd"})


if __name__ == "__main__":
    main()
