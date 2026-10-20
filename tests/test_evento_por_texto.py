import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import asignar_evento_por_texto as m

EV = "Catastrofe Bocatoma CNR 2026"
P = [
    {"id_proyecto": "A", "nombre_proyecto": "(CATÁSTROFE) HABILITACIÓN BOCATOMAS Y CANALES", "anio_postulacion": 2026},
    {"id_proyecto": "B", "nombre_proyecto": "(Catastrofe) habilitacion bocatomas rio", "anio_postulacion": 2025},
    {"id_proyecto": "C", "nombre_proyecto": "CATÁSTROFE- HABILITACIÓN DE CAMINOS", "anio_postulacion": 2026},
    {"id_proyecto": "D", "nombre_proyecto": "(CATASTROFE) HABILITACION BOCATOMAS X", "anio_postulacion": 2026},
]
EXTRA = {"B": {"evento": "FRC"}, "D": {"evento": EV}}
T = "(CATÁSTROFE) HABILITACIÓN BOCATOMAS"


def test_planificar_todos_los_anios():
    r = m.planificar(P, EXTRA, EV, T)
    assert set(r["nuevos"]) == {"A"} and set(r["reemplazos"]) == {"B"} and r["ya"] == 1


def test_planificar_con_anio():
    r = m.planificar(P, EXTRA, EV, T, 2026)
    assert set(r["nuevos"]) == {"A"} and r["reemplazos"] == {} and r["ya"] == 1


def test_aplicar():
    out = m.aplicar({"A": {"profesional": "Y"}}, ["A", "Z"], EV)
    assert out == {"A": {"profesional": "Y", "evento": EV}, "Z": {"evento": EV}}
