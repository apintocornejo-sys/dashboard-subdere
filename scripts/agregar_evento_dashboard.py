"""
Agrega un EVENTO nuevo al desplegable de "Datos adicionales" del dashboard (docs/index.html).

    python3 scripts/agregar_evento_dashboard.py "Transferencia Gobierno Regional 2025 Arrastre"

- Si el evento ya existe (sin importar mayúsculas), no hace nada.
- Si el nombre empieza con el de otro evento (p. ej. "... 2025" + " Arrastre"), lo deja justo después de ese.
- Guarda un respaldo de docs/index.html antes de modificarlo y verifica el resultado.
- No toca nada más del dashboard (tus ID de Drive y demás configuración quedan como están).
Después de agregarlo: publica (git add/commit/push) y asigna proyectos con scripts/asignar_evento_listado.py.
"""
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = BASE_DIR / "docs" / "index.html"
RE_BLOQUE = re.compile(r"(const EVENTOS = \[)(.*?)(\n\];)", re.S)


def leer_eventos(bloque: str) -> list:
    return [e.replace('\\"', '"').replace("\\\\", "\\") for e in re.findall(r'"((?:[^"\\]|\\.)*)"', bloque)]


def _js(e: str) -> str:
    return '  "' + e.replace("\\", "\\\\").replace('"', '\\"') + '",'


def agregar(html: str, nombre: str):
    """Devuelve (html_nuevo, mensaje). Lanza ValueError si no encuentra la lista de eventos o la verificación falla."""
    m = RE_BLOQUE.search(html)
    if not m:
        raise ValueError("No encontré 'const EVENTOS = [...]' en docs/index.html")
    existentes = leer_eventos(m.group(2))
    if nombre.lower() in (e.lower() for e in existentes):
        return html, f"El evento '{nombre}' ya existe en el dashboard; no se cambió nada."
    # Justo después del evento "padre" (si el nombre empieza con el de otro evento); si no, al final
    padres = [e for e in existentes if nombre.lower().startswith(e.lower() + " ")]
    pos = existentes.index(max(padres, key=len)) + 1 if padres else len(existentes)
    lista = existentes[:pos] + [nombre] + existentes[pos:]
    html_nuevo = html[:m.start()] + m.group(1) + "\n" + "\n".join(_js(e) for e in lista) + m.group(3) + html[m.end():]
    if leer_eventos(RE_BLOQUE.search(html_nuevo).group(2)) != lista:
        raise ValueError("La verificación falló: la lista resultante no es la esperada. No se escribió nada.")
    return html_nuevo, f"Evento '{nombre}' agregado al desplegable de Datos adicionales" + (f" (después de '{max(padres, key=len)}')." if padres else " (al final).")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not argv[0].strip():
        sys.exit('Uso: python3 scripts/agregar_evento_dashboard.py "Nombre del evento"')
    nombre = argv[0].strip()
    if not INDEX_HTML.exists():
        sys.exit(f"No encuentro {INDEX_HTML}. Ejecuta esto desde la carpeta del proyecto.")
    html = INDEX_HTML.read_text(encoding="utf-8")
    try:
        nuevo, msg = agregar(html, nombre)
    except ValueError as e:
        sys.exit(str(e))
    if nuevo != html:
        respaldo = INDEX_HTML.with_name(f"index.html.bak_evento_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(INDEX_HTML, respaldo)
        INDEX_HTML.write_text(nuevo, encoding="utf-8")
        print(f"Respaldo: {respaldo.name}")
    print(msg)
    if nuevo != html:
        print("Ahora publica el dashboard (git add / commit / push) y asigna los proyectos con scripts/asignar_evento_listado.py")


if __name__ == "__main__":
    main()
