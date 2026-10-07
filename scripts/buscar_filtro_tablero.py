"""
Busca qué filtro del informe "Resumen Financiero" reproduce tu tablero: 286 proyectos repartidos
  por provincia: Elqui 150 / Limarí 88 / Choapa 48
  por programa : PMU 174 / PMB 78 / FRC 1 / PRBIPE 22 / PTRAC 11
  (y, como control final, por comuna).

Parte de los proyectos de ESOS CINCO programas y prueba todas las combinaciones de estados, solas y junto con
una o dos condiciones (saldo, contratos, avance, fechas, año...). Una coincidencia verdadera debe calzar con
las provincias Y con los programas a la vez; si no hay, lo dice (no se fuerza una respuesta).

    python3 scripts/buscar_filtro_tablero.py
    python3 scripts/buscar_filtro_tablero.py --todos-los-programas        # sin restringir a los 5 programas
"""
import json
import argparse
import itertools
import collections
import unicodedata
import re
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent.parent
RUTA = BASE_DIR / "para_subir_a_drive" / "rendiciones.json"
HOY = date.today().isoformat()
OBJ_PROV = {"Elqui": 150, "Limarí": 88, "Choapa": 48}
OBJ_PROG = {"PMU": 174, "PMB": 78, "FRC": 1, "PRBIPE": 22, "PTRAC": 11}
OBJ_COMUNA = {"la serena": 51, "coquimbo": 50, "punitaqui": 24, "paihuano": 22, "ovalle": 20, "salamanca": 16, "canela": 16, "rio hurtado": 15,
              "monte patria": 14, "combarbala": 13, "la higuera": 11, "illapel": 9, "vicuna": 8, "los vilos": 7, "andacollo": 7}
SIGLAS = [("mejoramiento urbano", "PMU"), ("mejoramiento de barrios", "PMB"), ("recuperacion de ciudades", "FRC"),
          ("tenencia responsable", "PTRAC"), ("revitalizacion de barrios", "PRBIPE"), ("infraestructura patrimonial", "PRBIPE")]


def norm(t):
    n = unicodedata.normalize("NFKD", str(t or ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in n if not unicodedata.combining(c)).lower()).strip()


def sigla(programa):
    n = norm(programa)
    for k, s in SIGLAS:
        if k in n:
            return s
    return None


def condiciones(proyectos):
    n = lambda p, k: p.get(k) or 0
    c = {
        "(sin condición adicional)": lambda p: True,
        "saldo por rendir > 0": lambda p: n(p, "saldo_por_rendir") > 0,
        "saldo por rendir = 0": lambda p: not n(p, "saldo_por_rendir") > 0,
        "monto contratado > 0": lambda p: n(p, "monto_contratado") > 0,
        "monto contratado = 0": lambda p: not n(p, "monto_contratado") > 0,
        "total transferido > 0": lambda p: n(p, "total_transferido") > 0,
        "total transferido = 0": lambda p: not n(p, "total_transferido") > 0,
        "rendido < transferido": lambda p: n(p, "total_rendido") < n(p, "total_transferido"),
        "rendido >= transferido": lambda p: n(p, "total_rendido") >= n(p, "total_transferido"),
        "tiene fecha de término": lambda p: bool(p.get("fecha_termino")),
        "fecha término >= hoy": lambda p: (p.get("fecha_termino") or "") >= HOY,
        "fecha término < hoy": lambda p: bool(p.get("fecha_termino")) and p["fecha_termino"] < HOY,
    }
    campos = {k for p in proyectos for k in p}
    for k, nombre in (("contratos_registrados", "contratos registrados"), ("contratos_ejecucion", "contratos en ejecución")):
        if k in campos:
            c[f"{nombre} > 0"] = (lambda k: lambda p: n(p, k) > 0)(k)
            c[f"{nombre} = 0"] = (lambda k: lambda p: not n(p, k) > 0)(k)
    if "avance_financiero" in campos:
        for u in (0, 50, 100):
            c[f"avance financiero > {u}"] = (lambda u: lambda p: n(p, "avance_financiero") > u)(u)
            c[f"avance financiero <= {u}"] = (lambda u: lambda p: n(p, "avance_financiero") <= u)(u)
    if "total_reintegros" in campos:
        c["con reintegros"] = lambda p: n(p, "total_reintegros") != 0
    for campo, etq in (("anio_aprobacion", "año aprobación"), ("anio_postulacion", "año postulación")):
        for y in range(2011, 2027):
            c[f"{etq} >= {y}"] = (lambda campo, y: lambda p: (p.get(campo) or 0) >= y)(campo, y)
            c[f"{etq} = {y}"] = (lambda campo, y: lambda p: p.get(campo) == y)(campo, y)
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", type=int, default=286)
    ap.add_argument("--todos-los-programas", action="store_true", help="no restringir a PMU/PMB/FRC/PRBIPE/PTRAC")
    ap.add_argument("--mostrar", type=int, default=8)
    a = ap.parse_args(argv)
    todos = json.loads(RUTA.read_text(encoding="utf-8"))["proyectos"]
    print("Proyectos por programa en el informe completo (siglas de tu tablero; 'otro' = programa que el tablero no muestra):")
    cuenta = collections.Counter(sigla(p.get("programa")) or "otro" for p in todos)
    print("  " + ", ".join(f"{k}: {v}" for k, v in cuenta.most_common()) + f"   (tablero: {OBJ_PROG})\n")
    proyectos = todos if a.todos_los_programas else [p for p in todos if sigla(p.get("programa"))]
    estados = sorted({p.get("estado_real") or "(sin estado)" for p in proyectos})
    conds = condiciones(proyectos)
    print(f"Base: {len(proyectos)} proyectos, {len(estados)} estados, {len(conds)} condiciones. Buscando total={a.total}...\n")

    resultados = []

    def evaluar(nombre, fn):
        lista = [p for p in proyectos if fn(p)]
        por_estado = collections.defaultdict(lambda: (collections.Counter(), collections.Counter()))
        for p in lista:
            pe = por_estado[p.get("estado_real") or "(sin estado)"]
            pe[0][p.get("provincia")] += 1
            pe[1][sigla(p.get("programa")) or "otro"] += 1
        for k in range(1, len(estados) + 1):
            for combo in itertools.combinations(estados, k):
                prov, prog = collections.Counter(), collections.Counter()
                for e in combo:
                    if e in por_estado:
                        prov.update(por_estado[e][0]); prog.update(por_estado[e][1])
                tot = sum(prov.values())
                if tot == a.total:
                    d_prov = sum(abs(prov.get(x, 0) - v) for x, v in OBJ_PROV.items())
                    d_prog = sum(abs(prog.get(x, 0) - v) for x, v in OBJ_PROG.items())
                    resultados.append((d_prov + d_prog, d_prov, d_prog, nombre, combo, dict(prov), dict(prog), fn))

    for nombre, fn in conds.items():
        evaluar(nombre, fn)
    if not any(r[0] == 0 for r in resultados):
        claves = [k for k in conds if k != "(sin condición adicional)"]
        for n1, n2 in itertools.combinations(claves, 2):
            f1, f2 = conds[n1], conds[n2]
            evaluar(f"{n1}  Y  {n2}", lambda p, f1=f1, f2=f2: f1(p) and f2(p))
    resultados.sort(key=lambda r: (r[0], len(r[4])))
    exactos = [r for r in resultados if r[0] == 0]
    if not resultados:
        print("Ninguna combinación suma exactamente ese total.")
        return
    print("COINCIDENCIAS EXACTAS (total, provincias y programas):" if exactos else "NO HAY COINCIDENCIA EXACTA. Lo más cercano (referencial, probablemente casualidad):")
    for d, dp, dg, nombre, combo, prov, prog, fn in (exactos or resultados)[:a.mostrar]:
        lista = [p for p in proyectos if p.get("estado_real") in combo and fn(p)]
        com = collections.Counter(norm(p.get("comuna")).replace("paiguano", "paihuano") for p in lista)
        d_com = sum(abs(com.get(x, 0) - v) for x, v in OBJ_COMUNA.items())
        print(f"- Estados: {', '.join(combo)}\n    condición: {nombre}\n    provincias {prov} | programas {prog}\n"
              f"    diferencias: provincias {dp}, programas {dg}, comunas {d_com}")
    if not exactos:
        print("\nConclusión: con los datos de este informe no se reproduce el tablero con filtros simples; probablemente usa otra fuente o criterio.")


if __name__ == "__main__":
    main()
