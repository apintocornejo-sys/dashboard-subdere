from reglas_profesionales import calcular_profesional


def test_programa_con_profesional_fijo():
    assert calcular_profesional("PMB Tradicional", "OVALLE") == "Martin Rodriguez"
    assert calcular_profesional("Fondo Recuperación de Ciudades", "LA SERENA") == "Tamara Huerta"


def test_programa_dividido_por_comuna():
    assert calcular_profesional("Tradicional", "ILLAPEL") == "Tamara Huerta"
    assert calcular_profesional("Tradicional", "OVALLE") == "Romina Canihuante"
    assert calcular_profesional("Tradicional", "comuna inventada") is None


def test_programa_desconocido_no_asigna():
    assert calcular_profesional("Programa Nuevo", "OVALLE") is None
