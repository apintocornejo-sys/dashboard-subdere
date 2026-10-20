import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import asignar_evento_cartera_catastrofe as c

TGR, CAT = "Transferencia Gobierno Regional 2026", "Transferencia SUBDERE Catastrofe 2026"


def test_planificar():
    cartera = {"1-C-2026-1": "Transferencia Gobierno Regional 2026", "1-C-2026-2": "Ficha Simplificada SUBDERE Catastrofe 2026",
               "1-C-2026-3": "Ficha Simplificada SUBDERE Catastrofe 2026", "1-C-2026-4": "Ficha Simplificada SUBDERE Catastrofe 2026",
               "X": "Ficha simplificada subdere catástrofe 2026", "1-C-2026-5": "Otra fuente"}
    ids = {"1-C-2026-1", "1-C-2026-2", "1-C-2026-3", "1-C-2026-4", "1-C-2026-5"}
    extra = {"1-C-2026-3": {"evento": "FRC"}, "1-C-2026-4": {"evento": CAT}}
    r = c.planificar(cartera, ids, extra)
    assert r["nuevos"] == {"1-C-2026-1": TGR, "1-C-2026-2": CAT}
    assert r["reemplazos"] == {"1-C-2026-3": (CAT, "FRC")}
    assert r["ya"] == 1 and r["fuera"] == ["X"] and dict(r["sin_regla"]) == {"Otra fuente": 1}


def test_aplicar_conserva_campos():
    extra = {"A": {"profesional": "Y"}}
    out = c.aplicar(extra, {"A": CAT, "B": TGR})
    assert out == {"A": {"profesional": "Y", "evento": CAT}, "B": {"evento": TGR}} and extra == {"A": {"profesional": "Y"}}


def test_renombra_evento_antiguo():
    extra = {"Z-1": {"evento": c.EVENTO_ANTIGUO}, "Z-2": {"evento": "FRC"}, "1-C-2026-2": {"evento": c.EVENTO_ANTIGUO}}
    r = c.planificar({"1-C-2026-2": c.EVENTO_ANTIGUO}, {"1-C-2026-2"}, extra)
    assert r["renombrar"] == {"Z-1": CAT}                 # Z-1 no está en la planilla: solo se renombra
    assert r["nuevos"] == {} and r["reemplazos"] == {"1-C-2026-2": (CAT, c.EVENTO_ANTIGUO)}
