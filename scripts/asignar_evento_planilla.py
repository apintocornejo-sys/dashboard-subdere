"""
Asigna el EVENTO de cada proyecto desde la "Planilla Resumen y Control de Seguimiento URS Coquimbo"
y crea en el dashboard los eventos que falten.

Qué hace:
  1. Lee la columna "Evento" de la planilla (de Drive o de un Excel descargado).
  2. Cruza cada fila con los proyectos del dashboard por ID (corrige IDs como "41030209.0").
     Los proyectos de la planilla que NO están en el dashboard se listan aparte y no se tocan.
  3. Agrega a "Datos adicionales" el evento de cada proyecto, SOLO si está vacío:
     nunca reemplaza un evento ya asignado a mano (los conflictos se muestran para que decidas).
  4. Crea en el desplegable del dashboard (docs/index.html) los eventos que aún no existen.
     Los nombres equivalentes a uno existente se unifican (ej.: "EPS 2.000 Millones" -> "EPS 2000 Millones").
  5. Muestra el resumen, pide confirmación y guarda un respaldo de "Datos adicionales" antes de escribir.

Se puede repetir sin problema: cuando aparezcan proyectos nuevos en el dashboard que ya tengan evento en la
planilla, lo completa; lo que ya está asignado no se vuelve a tocar.

Uso (desde la carpeta del proyecto):
    python3 scripts/asignar_evento_planilla.py --simular                 # solo muestra qué haría
    python3 scripts/asignar_evento_planilla.py                           # aplica (pregunta antes)
    python3 scripts/asignar_evento_planilla.py --id ID_DE_LA_PLANILLA    # planilla original de Rodrigo
    python3 scripts/asignar_evento_planilla.py --archivo planilla.xlsx   # Excel descargado a mano
Después: git add -A && git commit -m "Eventos de la planilla" && git push   (publica los eventos nuevos)
"""
import re
import sys
import copy
import json
import shutil
import argparse
import collections
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importar_planilla_seguimiento as imp          # lector de la planilla y funciones de Drive
import agregar_evento_dashboard as agr               # alta de eventos en docs/index.html
import asignar_evento_listado as lst                 # proyectos publicados en Drive

BASE_DIR = imp.BASE_DIR
INDEX_HTML = BASE_DIR / "docs" / "index.html"
PLANILLA_ID = imp.PLANILLA_ID
DATOS_EXTRA_FILE_ID = imp.DATOS_EXTRA_FILE_ID
MARCADOR = "planilla de seguimiento (evento)"
# Eventos que cambian de nombre: "nombre antiguo" -> "nombre nuevo". Es una orden explícita del usuario (13-oct-2026):
# "Transferencia Gobierno Regional 2025 Arrastre" y "MM 1.894" son el mismo evento y queda solo "MM 1.894".
RENOMBRES = {"Transferencia Gobierno Regional 2025 Arrastre": "MM 1.894"}


def id_limpio(i) -> str:
    """'41030209.0' -> '41030209'; sin espacios (Excel convierte algunos códigos numéricos en decimales)."""
    s = re.sub(r"\s+", "", str(i or ""))
    return re.sub(r"\.0$", "", s)


def clave_evento(nombre: str) -> str:
    """Clave para comparar nombres de evento: sin tildes/mayúsculas y sin puntos de miles ('2.000' = '2000')."""
    t = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", str(nombre or ""))
    return imp.norm(t).replace(" ", "")


def nombre_evento(texto, existentes: list):
    """Nombre canónico: el de un evento existente si es equivalente; si no, el de la planilla (espacios limpios)."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    if not t:
        return None
    por_clave = {clave_evento(e): e for e in existentes}
    return por_clave.get(clave_evento(t), t)


def renombrado(nombre, renombres: dict):
    """Aplica la tabla de renombres (comparando sin mayúsculas/tildes); si no está, devuelve el nombre igual."""
    k = {clave_evento(a): b for a, b in renombres.items()}
    return k.get(clave_evento(nombre), nombre)


def planificar(filas: dict, ids_dashboard: set, datos_extra: dict, eventos_existentes: list, renombres: dict = None) -> dict:
    """Calcula (sin escribir nada) qué se asignaría. Pura: se puede probar sin Drive."""
    renombres = renombres or {}
    ids_norm = {id_limpio(i): i for i in ids_dashboard}
    asignar, ya_iguales, conflictos, fuera = {}, [], [], []
    sin_evento = 0
    # Proyectos que hoy tienen un evento con nombre antiguo: pasan al nombre nuevo (todos, estén o no en la planilla)
    renombrar = {i: renombrado(d["evento"], renombres) for i, d in datos_extra.items()
                 if (d or {}).get("evento") and renombrado(d["evento"], renombres) != d["evento"]}
    for idp_planilla, f in filas.items():
        evento = nombre_evento(renombrado(f.get("evento"), renombres), eventos_existentes)
        if not evento:
            sin_evento += 1
            continue
        real = ids_norm.get(id_limpio(idp_planilla))
        if real is None:
            fuera.append((idp_planilla, evento))
            continue
        actual = renombrado(((datos_extra.get(real) or {}).get("evento") or "").strip(), renombres)
        if not actual:
            asignar[real] = evento
        elif clave_evento(actual) == clave_evento(evento):
            ya_iguales.append(real)
        else:
            conflictos.append((real, actual, evento))
    existentes_k = {clave_evento(e) for e in eventos_existentes}
    destinos = set(asignar.values()) | set(renombrar.values())
    nuevos = sorted({e for e in destinos if clave_evento(e) not in existentes_k}, key=lambda s: (clave_evento(s)))
    viejos_k = {clave_evento(a) for a in renombres}
    a_borrar = [e for e in eventos_existentes if clave_evento(e) in viejos_k]
    return {"asignar": asignar, "ya_iguales": ya_iguales, "conflictos": conflictos, "fuera": fuera,
            "sin_evento": sin_evento, "eventos_nuevos": nuevos, "renombrar": renombrar, "eventos_a_borrar": a_borrar}


def aplicar_asignacion(datos_extra: dict, asignar: dict, hoy: str, renombrar: dict = None) -> dict:
    nuevos = copy.deepcopy(datos_extra)
    for idp, evento in (renombrar or {}).items():     # cambio de nombre ordenado por el usuario
        nuevos[idp]["evento"] = evento
        nuevos[idp]["actualizado"] = hoy
        nuevos[idp]["ultima_edicion_por"] = MARCADOR + " · evento renombrado"
    for idp, evento in asignar.items():
        ex = nuevos.get(idp) or {}
        if ex.get("evento"):                       # defensa: jamás pisar
            continue
        ex["evento"] = evento
        ex["actualizado"] = hoy
        ex["ultima_edicion_por"] = MARCADOR
        nuevos[idp] = ex
    return nuevos


def agregar_eventos_html(html: str, nombres: list):
    """Agrega los eventos al desplegable de docs/index.html (usa la misma lógica que agregar_evento_dashboard.py)."""
    mensajes = []
    for n in nombres:
        html, msg = agr.agregar(html, n)
        mensajes.append(msg)
    return html, mensajes


def reemplazar_evento_html(html: str, viejo: str, nuevo: str):
    """Cambia 'viejo' por 'nuevo' en el desplegable, en la misma posición (si 'nuevo' ya está, solo quita 'viejo')."""
    m = agr.RE_BLOQUE.search(html)
    lista = agr.leer_eventos(m.group(2))
    if viejo not in lista:
        return html, f"El evento '{viejo}' ya no estaba en el desplegable."
    if clave_evento(nuevo) in {clave_evento(e) for e in lista}:
        lista = [e for e in lista if e != viejo]
    else:
        lista = [nuevo if e == viejo else e for e in lista]
    html_nuevo = html[:m.start()] + m.group(1) + "\n" + "\n".join(agr._js(e) for e in lista) + m.group(3) + html[m.end():]
    if agr.leer_eventos(agr.RE_BLOQUE.search(html_nuevo).group(2)) != lista:
        raise ValueError("La verificación falló: la lista resultante no es la esperada. No se escribió nada.")
    return html_nuevo, f"Evento '{viejo}' reemplazado por '{nuevo}' en el desplegable."


def resumen(plan: dict, nombres_por_id: dict, eventos_existentes: list) -> str:
    L = []
    por_evento = collections.Counter(plan["asignar"].values())
    if plan["renombrar"]:
        L.append(f"RENOMBRE: {len(plan['renombrar'])} proyectos pasan del evento antiguo a '{', '.join(sorted(set(plan['renombrar'].values())))}'"
                 f"; se elimina del desplegable: {', '.join(plan['eventos_a_borrar']) or '(ya no estaba)'}\n")
    L.append(f"Proyectos a los que se les ASIGNARÁ evento: {len(plan['asignar'])}")
    for e, n in sorted(por_evento.items(), key=lambda x: (-x[1], x[0])):
        marca = "" if clave_evento(e) in {clave_evento(x) for x in eventos_existentes} else "   <-- evento NUEVO (se crea en el dashboard)"
        L.append(f"   {n:>4}  {e}{marca}")
    L.append(f"\nYa tenían ese mismo evento (no se tocan): {len(plan['ya_iguales'])}")
    L.append(f"Planilla sin evento en esa fila (no se asigna nada): {plan['sin_evento']}")
    if plan["conflictos"]:
        L.append(f"\n⚠ CONFLICTOS: {len(plan['conflictos'])} proyectos ya tienen OTRO evento; NO se cambian:")
        for idp, act, nue in plan["conflictos"][:25]:
            L.append(f"   {idp}  actual: {act!r}  ·  planilla: {nue!r}  ·  {nombres_por_id.get(idp, '')[:60]}")
    if plan["fuera"]:
        L.append(f"\nEn la planilla pero NO están (aún) en el dashboard: {len(plan['fuera'])} (se asignarán en una próxima ejecución, cuando aparezcan):")
        for idp, e in plan["fuera"][:25]:
            L.append(f"   {idp}  ({e})")
    L.append(f"\nEventos nuevos que se crearán en el desplegable: {len(plan['eventos_nuevos'])}")
    for e in plan["eventos_nuevos"]:
        L.append(f"   + {e}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", help="Excel de la planilla ya descargado (si no, se descarga de Drive)")
    ap.add_argument("--id", default=PLANILLA_ID, help="ID de la planilla en Drive")
    ap.add_argument("--simular", action="store_true", help="solo muestra el resumen; no escribe nada")
    ap.add_argument("--si", action="store_true", help="no preguntar confirmación")
    a = ap.parse_args(argv)
    hoy = date.today().isoformat()
    if not INDEX_HTML.exists():
        sys.exit(f"No encuentro {INDEX_HTML}. Ejecuta esto desde la carpeta del proyecto.")

    servicio = imp.obtener_servicio_drive()
    if a.archivo:
        ruta = Path(a.archivo)
    else:
        ruta = imp.descargar_planilla(servicio, a.id, imp.RAW_DIR / f"planilla_seguimiento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        imp.proteger_gitignore()
    planilla = imp.leer_planilla(ruta)
    if "evento" not in planilla["columnas"]:
        sys.exit("La planilla no tiene una columna 'Evento'.")
    proyectos = lst.cargar_proyectos(servicio)
    datos_extra = imp.leer_json_drive(servicio, DATOS_EXTRA_FILE_ID)
    html = INDEX_HTML.read_text(encoding="utf-8")
    existentes = agr.leer_eventos(agr.RE_BLOQUE.search(html).group(2))

    plan = planificar(planilla["filas"], {p["id_proyecto"] for p in proyectos}, datos_extra, existentes, RENOMBRES)
    nombres = {p["id_proyecto"]: p.get("nombre_proyecto", "") for p in proyectos}
    print(f"Hoja usada: '{planilla['hoja']}' · {len(planilla['filas'])} proyectos en la planilla · {len(proyectos)} en el dashboard\n")
    print(resumen(plan, nombres, existentes))
    if a.simular:
        print("\n(Simulación: no se escribió nada.)")
        return
    if not (plan["asignar"] or plan["eventos_nuevos"] or plan["renombrar"] or plan["eventos_a_borrar"]):
        print("\nNada que hacer: todo está al día.")
        return
    if not a.si and input("\n¿Aplicar? Se asigna en 'Datos adicionales' (Drive) y se crean los eventos en docs/index.html [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se aplicó nada.")
        return

    imp.RAW_DIR.mkdir(parents=True, exist_ok=True)
    respaldo = imp.RAW_DIR / f"datos_extra_respaldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    respaldo.write_text(json.dumps(datos_extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Respaldo de Datos adicionales: {respaldo.name}")

    # 1) primero los eventos en el dashboard (si falla la verificación, no se escribe nada en Drive)
    if plan["eventos_nuevos"] or plan["eventos_a_borrar"]:
        html_nuevo = html
        for viejo in plan["eventos_a_borrar"]:
            destino = renombrado(viejo, RENOMBRES)
            html_nuevo, _ = reemplazar_evento_html(html_nuevo, viejo, destino)
        html_nuevo, msgs = agregar_eventos_html(html_nuevo, plan["eventos_nuevos"])
        bak = imp.RAW_DIR / f"index.html.bak_evento_{datetime.now().strftime('%Y%m%d_%H%M%S')}"   # fuera de docs/ y de git
        shutil.copy2(INDEX_HTML, bak)
        INDEX_HTML.write_text(html_nuevo, encoding="utf-8")
        print(f"Respaldo del dashboard: {bak.name} · eventos nuevos: {len(plan['eventos_nuevos'])} · eventos eliminados: {len(plan['eventos_a_borrar'])}")
    # 2) luego la asignación en Datos adicionales
    imp.escribir_json_drive(servicio, DATOS_EXTRA_FILE_ID, aplicar_asignacion(datos_extra, plan["asignar"], hoy, plan["renombrar"]))
    print(f"Listo: {len(plan['asignar'])} proyectos con evento asignado y {len(plan['renombrar'])} renombrados.")
    print("Ahora publica: git add -A && git commit -m \"Eventos de la planilla de seguimiento\" && git push")


if __name__ == "__main__":
    main()
