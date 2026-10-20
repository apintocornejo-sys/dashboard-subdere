import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import asignar_evento_por_nombre as m

E = m.EVENTO
P = [
    {"id_proyecto": "A", "nombre_proyecto": "Reposición por CATÁSTROFE de camino", "anio_postulacion": 2026},
    {"id_proyecto": "B", "nombre_proyecto": "Habilitación de Caminos rurales", "anio_postulacion": "2026"},
    {"id_proyecto": "C", "nombre_proyecto": "Habilitacion de caminos", "anio_postulacion": 2025},     # otro año: no
    {"id_proyecto": "D", "nombre_proyecto": "Plaza", "anio_postulacion": 2026},                        # otro nombre: no
    {"id_proyecto": "E", "nombre_proyecto": "Catastrofe sistema frontal", "anio_postulacion": 2026},
    {"id_proyecto": "F", "nombre_proyecto": "Catastrofe agua", "anio_postulacion": 2026},
]
EXTRA = {"E": {"evento": "FRC"}, "F": {"evento": E}}


def test_planificar():
    r = m.planificar(P, EXTRA)
    assert set(r["nuevos"]) == {"A", "B"}
    assert set(r["reemplazos"]) == {"E"} and r["reemplazos"]["E"][1] == "FRC"
    assert r["ya"] == 1


def test_aplicar_conserva_otros_campos():
    extra = {"A": {"profesional": "X"}}
    out = m.aplicar(extra, ["A", "B"])
    assert out["A"] == {"profesional": "X", "evento": E} and out["B"] == {"evento": E}
    assert extra == {"A": {"profesional": "X"}}      # no muta el original
