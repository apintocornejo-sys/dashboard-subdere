"""Pruebas del procesador de Rendiciones (scripts/rendiciones_financiero.py)."""
from datetime import datetime

import rendiciones_financiero as rf

AHORA = datetime(2026, 10, 13, 12, 0)

ENCABEZADOS = ["Provincia", "Comuna", "Programa", "Subprograma", "Id. Proyecto", "Nombre Proyecto",
               "Monto Asignado", "Monto Contratado", "Total Transferido", "Total Rendido",
               "Plazo Ejecución", "Fecha Asignación"]


def fila(**kw):
    base = {"Provincia": "Elqui", "Comuna": "La Serena", "Programa": "PMB", "Subprograma": "Tradicional",
            "Id. Proyecto": "1-C-2026-1", "Nombre Proyecto": "Plaza", "Monto Asignado": "$ 1.000.000",
            "Monto Contratado": "$ 800.000", "Total Transferido": "$ 500.000", "Total Rendido": "$ 200.000",
            "Plazo Ejecución": "60 días", "Fecha Asignación": "01/07/2026"}
    base.update(kw)
    return [base[h] for h in ENCABEZADOS]


def test_a_monto():
    assert rf.a_monto("$ 1.234.567") == 1234567
    assert rf.a_monto("-500") == -500
    assert rf.a_monto("(500)") == -500
    assert rf.a_monto("1.234,50") == 1234
    assert rf.a_monto("") is None
    assert rf.a_monto("No aplica") is None


def test_a_porcentaje():
    assert rf.a_porcentaje("85,3%") == 85.3
    assert rf.a_porcentaje("100 %") == 100.0
    assert rf.a_porcentaje("") is None


def test_a_fecha():
    assert rf.a_fecha("2026-08-12") == "2026-08-12"
    assert rf.a_fecha("12/08/2026") == "2026-08-12"
    assert rf.a_fecha("31/02/2026") is None
    assert rf.a_fecha("") is None


def test_a_plazo_dias():
    assert rf.a_plazo_dias("60 días") == 60
    assert rf.a_plazo_dias("6 meses") == 180
    assert rf.a_plazo_dias("no aplica") is None


def test_mapear_columnas_reconoce_tildes_y_alias():
    mapa, faltan = rf.mapear_columnas(ENCABEZADOS)
    for campo in ("provincia", "comuna", "programa", "id_proyecto", "monto_asignado", "monto_contratado",
                  "total_transferido", "total_rendido", "plazo_ejecucion", "fecha_asignacion"):
        assert campo in mapa, campo
    assert "fecha_termino" in faltan


def test_saldos_y_formulas():
    r = rf.procesar_tabla(ENCABEZADOS, [fila()], ahora=AHORA)
    p = r["proyectos"][0]
    assert p["saldo_contable"] == 200_000          # asignado - contratado
    assert p["saldo_por_transferir"] == 300_000    # contratado - transferido
    assert p["saldo_por_rendir"] == 300_000        # transferido - rendido (el informe no trae la columna)
    assert p["anio_aprobacion"] == 2026
    assert r["total_proyectos"] == 1


def test_fecha_termino_se_estima_con_plazo():
    p = rf.procesar_tabla(ENCABEZADOS, [fila()], ahora=AHORA)["proyectos"][0]
    assert p["fecha_termino"] == "2026-08-30"       # 01-07 + 60 días
    assert p["termino_estimado"] is True


def test_se_descartan_totales_y_duplicados():
    totales = ["Totales"] + [""] * (len(ENCABEZADOS) - 1)
    r = rf.procesar_tabla(ENCABEZADOS, [fila(), fila(), totales], ahora=AHORA)
    assert r["total_proyectos"] == 1
    assert any("idénticas" in a for a in r["advertencias"])


def test_advierte_si_falta_columna_obligatoria():
    r = rf.procesar_tabla(["Comuna", "Programa"], [["La Serena", "PMB"]], ahora=AHORA)
    assert any("No se encontró la columna" in a for a in r["advertencias"])


def test_provincia_se_deduce_de_la_comuna():
    p = rf.procesar_tabla(ENCABEZADOS, [fila(Provincia="", Comuna="Ovalle")], ahora=AHORA)["proyectos"][0]
    assert p["provincia"] == "Limarí"
