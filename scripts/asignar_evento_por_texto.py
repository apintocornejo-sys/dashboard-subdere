"""
Crea un EVENTO (si no existe) y se lo asigna a los proyectos cuyo NOMBRE contenga un texto
(sin importar mayúsculas, tildes ni signos como paréntesis).

Ejemplo (20-oct-2026):
    python3 scripts/asignar_evento_por_texto.py --evento "Catastrofe Bocatoma CNR 2026" \\
        --texto "(CATÁSTROFE) HABILITACIÓN BOCATOMAS" --simular
    python3 scripts/asignar_evento_por_texto.py --evento "Catastrofe Bocatoma CNR 2026" \\
        --texto "(CATÁSTROFE) HABILITACIÓN BOCATOMAS"

Opciones:
    --anio-postulacion 2026   limita a ese año de postulación (por defecto: todos los años)

- Si un proyecto ya tenía OTRO evento, lo REEMPLAZA; el resumen lo lista antes de confirmar.
- Crea el evento en el desplegable de docs/index.html (después: git add -A && git commit && git push).
- Antes de escribir guarda respaldos de "Datos adicionales" y del dashboard en data_raw/. Se puede repetir.
"""
import sys
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregar_evento_dashboard as agr
import asignar_evento_listado as lst

INDEX_HTML = lst.BASE_DIR / "docs" / "index.html"


def coincide(p: dict, texto_norm: str, anio=None) -> bool:
    if anio is not None and lst.anio_postulacion(p) != anio:
        return False
    return texto_norm in lst.normalizar(p.get("nombre_proyecto"))


def planificar(proyectos: list, datos_extra: dict, evento: str, texto: str, anio=None) -> dict:
    """Calcula (sin escribir) qué proyectos cambian. Pura: se prueba sin Drive."""
    t = lst.normalizar(texto)
    nuevos, reemplazos, ya = {}, {}, 0
    for p in proyectos:
        idp = p.get("id_proyecto")
        if not idp or not coincide(p, t, anio):
            continue
        actual = lst.evento_de(datos_extra, idp).strip()
        if actual == evento:
            ya += 1
        elif actual:
            reemplazos[idp] = (p, actual)
        else:
            nuevos[idp] = p
    return {"nuevos": nuevos, "reemplazos": reemplazos, "ya": ya}


def aplicar(datos_extra: dict, ids, evento: str) -> dict:
    out = json.loads(json.dumps(datos_extra))
    for idp in ids:
        e = out.get(idp) or {}
        e["evento"] = evento
        out[idp] = e
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evento", required=True)
    ap.add_argument("--texto", required=True)
    ap.add_argument("--anio-postulacion", type=int, default=None)
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args(argv)
    evento = a.evento.strip()
    if not evento or not lst.normalizar(a.texto):
        sys.exit("Indica --evento y --texto.")
    servicio = lst.obtener_servicio_drive()
    proyectos = lst.cargar_proyectos(servicio)
    datos_extra = lst.leer_json_drive(servicio, lst.DATOS_EXTRA_FILE_ID)
    html = INDEX_HTML.read_text(encoding="utf-8")
    existentes = agr.leer_eventos(agr.RE_BLOQUE.search(html).group(2))
    crear = evento.lower() not in (e.lower() for e in existentes)
    plan = planificar(proyectos, datos_extra, evento, a.texto, a.anio_postulacion)
    n, r = plan["nuevos"], plan["reemplazos"]
    print(f"Proyectos cuyo nombre contiene '{a.texto}'" + (f" (postulación {a.anio_postulacion})" if a.anio_postulacion else "") + f": {len(n) + len(r) + plan['ya']}")
    print(f"   ya tienen '{evento}': {plan['ya']}   ·   sin evento (se asignan): {len(n)}   ·   con OTRO evento (se reemplaza): {len(r)}")
    if crear:
        print(f"\nSe CREARÁ el evento '{evento}' en el dashboard.")
    if r:
        print("\nSe REEMPLAZA el evento de:")
        for idp, (p, ev) in sorted(r.items()):
            print(f"   {idp} | {p.get('comuna')} | {str(p.get('nombre_proyecto'))[:55]} | antes: {ev}")
    print("\nSe asignan (sin evento):")
    for idp, p in sorted(n.items()):
        print(f"   {idp} | {p.get('comuna')} | post. {lst.anio_postulacion(p) or '?'} | {str(p.get('nombre_proyecto'))[:60]}")
    if a.simular:
        print("\n(Simulación: no se escribió nada.)")
        return
    total = len(n) + len(r)
    if not total and not crear:
        print("\nNada que hacer.")
        return
    if input(f"\n¿Asignar '{evento}' a {total} proyectos" + (" y crear el evento" if crear else "") + "? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se aplicó nada.")
        return
    lst.RESPALDOS_DIR.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp = lst.RESPALDOS_DIR / f"datos_extra_respaldo_{marca}.json"
    resp.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo: {resp.name}")
    if crear:      # primero el dashboard: si falla la verificación, no se escribe nada en Drive
        html_nuevo, msg = agr.agregar(html, evento)
        shutil.copy2(INDEX_HTML, lst.RESPALDOS_DIR / f"index.html.bak_evento_{marca}")
        INDEX_HTML.write_text(html_nuevo, encoding="utf-8")
        print(msg)
    lst.escribir_json_drive(servicio, lst.DATOS_EXTRA_FILE_ID, aplicar(datos_extra, list(n) + list(r), evento))
    print(f"Listo: {total} proyectos con el evento '{evento}'.")
    if crear:
        print('Ahora publica el evento nuevo: git add -A && git commit -m "Evento nuevo" && git push')


if __name__ == "__main__":
    main()
