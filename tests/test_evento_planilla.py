import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import asignar_evento_planilla as ev

EXISTENTES = ["FRC", "EPS 2000 Millones", "CHA 2022"]


def test_id_limpio():
    assert ev.id_limpio("41030209.0") == "41030209"
    assert ev.id_limpio(" 1-C-2021-1092 ") == "1-C-2021-1092"
    assert ev.id_limpio("4103210701-C [FET]") == "4103210701-C[FET]"


def test_nombre_evento_unifica_equivalentes():
    assert ev.nombre_evento("EPS 2.000 Millones", EXISTENTES) == "EPS 2000 Millones"
    assert ev.nombre_evento("  cha   2022 ", EXISTENTES) == "CHA 2022"
    assert ev.nombre_evento("MM 1.894", EXISTENTES) == "MM 1.894"
    assert ev.nombre_evento("", EXISTENTES) is None


def test_planificar_no_pisa_y_separa():
    filas = {
        "41030209.0": {"evento": "PMB IRAL 2025"},          # se asigna (id con .0)
        "A-1": {"evento": "FRC"},                           # ya igual
        "A-2": {"evento": "CHA 2022"},                      # conflicto
        "A-3": {"evento": None},                            # sin evento
        "ZZ": {"evento": "FRC 2024"},                       # no está en el dashboard
    }
    datos = {"A-1": {"evento": "FRC"}, "A-2": {"evento": "FET 2021"}}
    plan = ev.planificar(filas, {"41030209", "A-1", "A-2", "A-3"}, datos, EXISTENTES)
    assert plan["asignar"] == {"41030209": "PMB IRAL 2025"}
    assert plan["ya_iguales"] == ["A-1"]
    assert plan["conflictos"] == [("A-2", "FET 2021", "CHA 2022")]
    assert plan["fuera"] == [("ZZ", "FRC 2024")]
    assert plan["sin_evento"] == 1
    assert plan["eventos_nuevos"] == ["PMB IRAL 2025"]


def test_aplicar_nunca_pisa_y_es_idempotente():
    datos = {"A": {"evento": "X"}, "B": {"nota": "n"}}
    nuevo = ev.aplicar_asignacion(datos, {"A": "Y", "B": "Z", "C": "W"}, "2026-10-13")
    assert nuevo["A"]["evento"] == "X"
    assert nuevo["B"]["evento"] == "Z" and nuevo["B"]["nota"] == "n"
    assert nuevo["C"]["evento"] == "W"
    assert datos["B"].get("evento") is None                    # no modifica el original
    plan2 = ev.planificar({"B": {"evento": "Z"}}, {"B"}, nuevo, ["Z"])
    assert plan2["asignar"] == {} and plan2["ya_iguales"] == ["B"]


def test_agregar_eventos_html_en_orden():
    html = 'x\nconst EVENTOS = [\n  "FRC",\n  "CHA 2022",\n];\ny'
    nuevo, _ = ev.agregar_eventos_html(html, ["FRC 2024", "MM600"])
    lista = ev.agr.leer_eventos(ev.agr.RE_BLOQUE.search(nuevo).group(2))
    assert lista == ["FRC", "FRC 2024", "CHA 2022", "MM600"]


REN = {"Transferencia Gobierno Regional 2025 Arrastre": "MM 1.894"}


def test_renombre_arrastre_a_mm():
    filas = {"A": {"evento": "MM 1.894"}, "B": {"evento": "MM 1.894"}}
    datos = {"A": {"evento": "Transferencia Gobierno Regional 2025 Arrastre"},
             "C": {"evento": "Transferencia Gobierno Regional 2025 Arrastre"},   # no está en la planilla: igual se renombra
             "D": {"evento": "CHA 2022"}}
    exist = ["CHA 2022", "Transferencia Gobierno Regional 2025 Arrastre"]
    plan = ev.planificar(filas, {"A", "B", "C", "D"}, datos, exist, REN)
    assert plan["renombrar"] == {"A": "MM 1.894", "C": "MM 1.894"}
    assert plan["asignar"] == {"B": "MM 1.894"}
    assert plan["conflictos"] == [] and plan["ya_iguales"] == ["A"]
    assert plan["eventos_nuevos"] == ["MM 1.894"]
    assert plan["eventos_a_borrar"] == ["Transferencia Gobierno Regional 2025 Arrastre"]
    nuevo = ev.aplicar_asignacion(datos, plan["asignar"], "2026-10-13", plan["renombrar"])
    assert [nuevo[k]["evento"] for k in "ABCD" if k in nuevo] == ["MM 1.894", "MM 1.894", "MM 1.894", "CHA 2022"]
    assert datos["A"]["evento"].endswith("Arrastre")                     # no modifica el original


def test_reemplazar_evento_html_misma_posicion():
    html = 'x\nconst EVENTOS = [\n  "FRC",\n  "Transferencia Gobierno Regional 2025 Arrastre",\n  "SPD",\n];\ny'
    nuevo, _ = ev.reemplazar_evento_html(html, "Transferencia Gobierno Regional 2025 Arrastre", "MM 1.894")
    assert ev.agr.leer_eventos(ev.agr.RE_BLOQUE.search(nuevo).group(2)) == ["FRC", "MM 1.894", "SPD"]
    ya, _ = ev.reemplazar_evento_html(nuevo, "Transferencia Gobierno Regional 2025 Arrastre", "MM 1.894")
    assert ya == nuevo
