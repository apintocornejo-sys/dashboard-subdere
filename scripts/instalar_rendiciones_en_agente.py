"""
Conecta "Rendiciones" con tu agente_actualizacion.py, SIN reemplazarlo: inserta dos bloques pequeños
(deja un respaldo y no hace nada si ya estaban). Se ejecuta una sola vez:

    python3 scripts/instalar_rendiciones_en_agente.py

Después, el comando de siempre actualiza ambos dashboards:
    python3 scripts/agente_actualizacion.py
"""
import re
import sys
import shutil
import py_compile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
AGENTE = BASE_DIR / "scripts" / "agente_actualizacion.py"
GITIGNORE = BASE_DIR / ".gitignore"

BLOQUE_DESCARGA = '''{i}# --- Rendiciones: mismo inicio de sesión, segundo informe (si falla, NO interrumpe la descarga de proyectos) ---
{i}try:
{i}    sys.path.insert(0, str(BASE_DIR / "scripts"))
{i}    import rendiciones_financiero
{i}    rendiciones_financiero.descargar_en_sesion(page, log, BASE_DIR)
{i}except Exception as e:
{i}    log(f"Rendiciones: no se pudo descargar el Resumen Financiero ({{e}}). El flujo de proyectos continúa.")

'''
BLOQUE_MAIN = '''{i}try:
{i}    sys.path.insert(0, str(BASE_DIR / "scripts"))
{i}    import rendiciones_financiero
{i}    rendiciones_financiero.publicar(log, obtener_credenciales_drive, base_dir=BASE_DIR)
{i}except Exception as e:
{i}    log(f"ERROR en Rendiciones: {{e}}")
{i}    log("Esto no detiene el resto del flujo.")

'''
RE_DESCARGA = re.compile(r"^([ \t]*)browser\.close\(\)[ \t]*\n[ \t]*return dest[ \t]*$", re.M)
RE_MAIN = re.compile(r"^([ \t]*)try:[ \t]*\n[ \t]*publicar_en_github\(\)", re.M)


def parchear(codigo: str):
    """Devuelve (codigo_nuevo, [mensajes]) o lanza ValueError si no encuentra dónde insertar."""
    msgs = []
    if "rendiciones_financiero.descargar_en_sesion" not in codigo:
        m = RE_DESCARGA.search(codigo)
        if not m:
            raise ValueError("descarga")
        codigo = codigo[:m.start()] + BLOQUE_DESCARGA.format(i=m.group(1)) + codigo[m.start():]
        msgs.append("Insertado el paso de descarga (dentro de descargar_excel_subdere).")
    else:
        msgs.append("El paso de descarga ya estaba instalado.")
    if "rendiciones_financiero.publicar" not in codigo:
        m = RE_MAIN.search(codigo)
        if not m:
            raise ValueError("main")
        codigo = codigo[:m.start()] + BLOQUE_MAIN.format(i=m.group(1)) + codigo[m.start():]
        msgs.append("Insertado el paso de publicación (en main(), antes de subir a GitHub).")
    else:
        msgs.append("El paso de publicación ya estaba instalado.")
    return codigo, msgs


LINEAS_GITIGNORE = [
    "data_raw/Resumen_Financiero_*",        # Excel financieros crudos
    "para_subir_a_drive/rendiciones.json",  # ya vive en Drive; evita ~1 MB nuevo en el historial en cada corrida (3 veces al día)
    "debug/",                               # capturas del portal (pueden mostrar montos)
]


def proteger_gitignore():
    """Los datos financieros crudos no se suben a GitHub (el repositorio es público)."""
    actual = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else ""
    lineas_actuales = {l.strip() for l in actual.splitlines()}
    faltan = [l for l in LINEAS_GITIGNORE if l not in lineas_actuales]
    if not faltan:
        return "El .gitignore ya excluía los archivos financieros."
    GITIGNORE.write_text(actual.rstrip("\n") + ("\n" if actual else "") + "# Rendiciones: datos financieros que no deben subirse a GitHub\n" + "\n".join(faltan) + "\n", encoding="utf-8")
    return "Agregué al .gitignore: " + ", ".join(faltan)


def main():
    if not AGENTE.exists():
        sys.exit(f"No encuentro {AGENTE}. Ejecuta esto desde la carpeta del proyecto.")
    original = AGENTE.read_text(encoding="utf-8")
    try:
        nuevo, msgs = parchear(original)
    except ValueError as e:
        print("No pude ubicar automáticamente dónde insertar el paso de", e, "en tu agente_actualizacion.py.")
        print("No se modificó nada. Pásame el archivo y lo ajusto.")
        sys.exit(1)
    if nuevo != original:
        respaldo = AGENTE.with_name(AGENTE.name + ".bak_antes_rendiciones")
        if not respaldo.exists():
            shutil.copy2(AGENTE, respaldo)
        AGENTE.write_text(nuevo, encoding="utf-8")
        try:
            py_compile.compile(str(AGENTE), doraise=True)
        except py_compile.PyCompileError as err:
            shutil.copy2(respaldo, AGENTE)
            sys.exit(f"El agente modificado no compilaba; lo dejé como estaba. Detalle: {err}")
        print(f"Respaldo: {respaldo.name}")
    for m in msgs:
        print(" -", m)
    print(" -", proteger_gitignore())
    print("\nListo. Ahora ejecuta: python3 scripts/crear_archivos_drive.py   (una sola vez)")


if __name__ == "__main__":
    main()
