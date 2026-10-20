"""
Asigna el evento "Transferencia Gobierno Regional 2026" a los proyectos con AÑO DE POSTULACIÓN 2026
cuyo NOMBRE contenga "catástrofe" o "habilitación de caminos" (sin importar mayúsculas ni tildes).

- Si el proyecto ya tenía OTRO evento, lo REEMPLAZA (es lo que se pidió); el resumen lo lista antes de confirmar.
- Antes de escribir guarda un respaldo de "Datos adicionales" en data_raw/.
- Se puede repetir: lo que ya tiene el evento no se vuelve a tocar.

Uso:
    python3 scripts/asignar_evento_por_nombre.py --simular
    python3 scripts/asignar_evento_por_nombre.py          # pregunta antes de escribir
"""
import sys
import json
import argparse
import collections
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asignar_evento_listado as lst

EVENTO = "Transferencia Gobierno Regional 2026"
ANIO_POSTULACION = 2026
PALABRAS = ["catastrofe", "habilitacion de caminos"]      # ya sin tildes (se compara normalizado)


def coincide(p: dict) -> list:
    """Palabras clave que aparecen en el nombre del proyecto (vacío si no es de postulación 2026)."""
    if lst.anio_postulacion(p) != ANIO_POSTULACION:
        return []
    n = lst.normalizar(p.get("nombre_proyecto"))
    return [w for w in PALABRAS if w in n]


def planificar(proyectos: list, datos_extra: dict) -> dict:
    """Calcula (sin escribir) qué proyectos cambian. Pura: se prueba sin Drive."""
    nuevos, reemplazos, ya = {}, {}, 0
    for p in proyectos:
        idp = p.get("id_proyecto")
        if not idp or not coincide(p):
            continue
        actual = lst.evento_de(datos_extra, idp).strip()
        if actual == EVENTO:
            ya += 1
        elif actual:
            reemplazos[idp] = (p, actual)
        else:
            nuevos[idp] = p
    return {"nuevos": nuevos, "reemplazos": reemplazos, "ya": ya}


def aplicar(datos_extra: dict, ids) -> dict:
    out = json.loads(json.dumps(datos_extra))
    for idp in ids:
        e = out.get(idp) or {}
        e["evento"] = EVENTO
        out[idp] = e
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args(argv)
    if EVENTO not in lst.EVENTOS_VALIDOS:
        sys.exit(f"El evento '{EVENTO}' no existe en el dashboard; agrégalo primero.")
    servicio = lst.obtener_servicio_drive()
    proyectos = lst.cargar_proyectos(servicio)
    datos_extra = lst.leer_json_drive(servicio, lst.DATOS_EXTRA_FILE_ID)
    plan = planificar(proyectos, datos_extra)
    n, r = plan["nuevos"], plan["reemplazos"]
    por_palabra = collections.Counter(w for p in list(n.values()) + [x[0] for x in r.values()] for w in coincide(p))
    print(f"Proyectos de postulación {ANIO_POSTULACION} con {' / '.join(PALABRAS)} en el nombre: {len(n) + len(r) + plan['ya']}")
    print(f"   ya tienen '{EVENTO}': {plan['ya']}   ·   sin evento (se asignan): {len(n)}   ·   con OTRO evento (se reemplaza): {len(r)}")
    for w, c in por_palabra.items():
        print(f"   {c:>4} contienen '{w}'")
    if r:
        print("\nSe REEMPLAZA el evento de estos:")
        for idp, (p, ev) in sorted(r.items()):
            print(f"   {idp} | {p.get('comuna')} | {str(p.get('nombre_proyecto'))[:60]} | antes: {ev}")
    print("\nSe asignan (sin evento):")
    for idp, p in sorted(n.items()):
        print(f"   {idp} | {p.get('comuna')} | {str(p.get('nombre_proyecto'))[:70]}")
    if a.simular:
        print("\n(Simulación: no se escribió nada.)")
        return
    total = len(n) + len(r)
    if not total:
        print("\nNada que hacer.")
        return
    if input(f"\n¿Asignar '{EVENTO}' a {total} proyectos en 'Datos adicionales' (Drive)? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se aplicó nada.")
        return
    lst.RESPALDOS_DIR.mkdir(exist_ok=True)
    resp = lst.RESPALDOS_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    resp.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo: {resp.name}")
    lst.escribir_json_drive(servicio, lst.DATOS_EXTRA_FILE_ID, aplicar(datos_extra, list(n) + list(r)))
    print(f"Listo: {total} proyectos con el evento '{EVENTO}'. Se verá en el dashboard en la próxima carga.")


if __name__ == "__main__":
    main()
