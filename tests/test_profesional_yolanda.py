import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from reglas_profesionales import calcular_profesional
import asignar_profesional_yolanda as y

COM_Y = ["LOS VILOS", "ANDACOLLO", "LA HIGUERA", "PUNITAQUI", "MONTE PATRIA", "RÍO HURTADO"]
PROG_Y = ["Emergencia", "Tradicional", "Emergencia Fondo Infraestructura Educacional",
          "Subsecretaría Prevención del Delito", "Ministerio de Transporte y Telecomunicación"]


def test_yolanda_en_sus_comunas_y_programas():
    for c in COM_Y:
        for p in PROG_Y:
            assert calcular_profesional(p, c) == "Yolanda Moya", (p, c)
    assert calcular_profesional("Tradicional", "Río Hurtado") == "Yolanda Moya"      # sin importar mayúsculas
    assert calcular_profesional("Tradicional", "RIO HURTADO") == "Yolanda Moya"      # ni tildes


def test_resto_queda_como_antes():
    assert calcular_profesional("Tradicional", "ILLAPEL") == "Tamara Huerta"
    assert calcular_profesional("Tradicional", "COQUIMBO") == "Tamara Huerta"
    assert calcular_profesional("Emergencia", "OVALLE") == "Romina Canihuante"
    assert calcular_profesional("Emergencia", "LA SERENA") == "Romina Canihuante"
    # programas con profesional fijo no cambian aunque la comuna sea de Yolanda
    assert calcular_profesional("PMB Tradicional", "LOS VILOS") == "Martin Rodriguez"
    assert calcular_profesional("Programa Mejoramiento de Barrios", "PUNITAQUI") == "Martin Rodriguez"
    assert calcular_profesional("Programa Tenencia Responsable de Animales de Compañía", "ANDACOLLO") == "Carlos Pinto"


def test_planificar_reemplaza_y_no_toca_otros():
    proy = [
        {"id_proyecto": "A", "programa": "Emergencia", "comuna": "LOS VILOS"},      # Tamara -> Yolanda
        {"id_proyecto": "B", "programa": "Tradicional", "comuna": "PUNITAQUI"},     # Romina -> Yolanda
        {"id_proyecto": "C", "programa": "Tradicional", "comuna": "ILLAPEL"},       # no corresponde
        {"id_proyecto": "D", "programa": "Emergencia", "comuna": "ANDACOLLO"},      # ya es de Yolanda
        {"id_proyecto": "E", "programa": "Emergencia", "comuna": "LA HIGUERA"},     # sin profesional
    ]
    datos = {"A": {"profesional": "Tamara Huerta", "evento": "X"}, "B": {"profesional": "Romina Canihuante"},
             "C": {"profesional": "Tamara Huerta"}, "D": {"profesional": "Yolanda Moya"}}
    plan = y.planificar(proy, datos)
    assert sorted(plan["cambios"]) == ["A", "B", "E"] and plan["ya"] == 1
    assert plan["previos"]["Tamara Huerta"] == 1 and plan["previos"]["(sin profesional)"] == 1
    nuevo = y.aplicar(datos, plan["cambios"])
    assert [nuevo[k]["profesional"] for k in "ABCDE" if k in nuevo] == ["Yolanda Moya", "Yolanda Moya", "Tamara Huerta", "Yolanda Moya", "Yolanda Moya"]
    assert nuevo["A"]["evento"] == "X"                       # conserva el resto de los datos
    assert datos["A"]["profesional"] == "Tamara Huerta"      # no modifica el original
