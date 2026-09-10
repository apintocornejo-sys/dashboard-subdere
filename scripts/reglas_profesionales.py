"""
Reglas de asignación automática de "Profesional a cargo" según Programa
(y, para algunos programas, según Comuna).

Este módulo es compartido por:
  - asignar_profesionales_backfill.py  (aplica las reglas una sola vez, ahora,
    a todos los proyectos existentes)
  - agente_actualizacion.py            (aplica las mismas reglas cada semana,
    pero SOLO a proyectos que todavía no tienen un "profesional" asignado —
    nunca sobrescribe una asignación manual hecha desde el dashboard)

Para agregar/cambiar reglas en el futuro, edita las listas de abajo.
"""

# Programas cuyo profesional es siempre el mismo, sin importar la comuna
PROGRAMAS_PROFESIONAL_FIJO = {
    "Martin Rodriguez": [
        "Programa Mejoramiento de Barrios",
        "Energización",
        "Infraestructura Rural",
        "Residuos Solidos",
        "Saneamiento Sanitario",
        "PMB Tradicional",
    ],
    "Romina Canihuante": [
        "Puesta en Valor del Patrimonio",  # sin proyectos aún; queda listo para cuando aparezcan
    ],
    "Tamara Huerta": [
        "Fondo Recuperación de Ciudades",
        "Revitalización de Barrios e Infraestructura Patrimonial Emblemática",
    ],
    "Carlos Pinto": [
        "Programa Tenencia Responsable de Animales de Compañía",
    ],
}

# Programas que se dividen por comuna
PROGRAMAS_DIVIDIDOS_POR_COMUNA = [
    "Emergencia Fondo Infraestructura Educacional",
    "Tradicional",
    "Emergencia",
    "Ministerio de Transporte y Telecomunicación",
    "Fondo Catástrofe",   # sin proyectos aún; queda listo para cuando aparezcan
    "Emergencia Turismo",  # sin proyectos aún; queda listo para cuando aparezcan
    "Subsecretaría Prevención del Delito",
]

COMUNAS_TAMARA_HUERTA = {
    "LA HIGUERA", "COQUIMBO", "ANDACOLLO", "CANELA", "LOS VILOS", "ILLAPEL", "SALAMANCA",
}
COMUNAS_ROMINA_CANIHUANTE = {
    "LA SERENA", "VICUÑA", "PAIGUANO", "OVALLE", "PUNITAQUI", "MONTE PATRIA",
    "COMBARBALÁ", "RÍO HURTADO",
}

# Programas explícitamente sin designar (no se les asigna nadie)
PROGRAMAS_SIN_DESIGNAR = []


def calcular_profesional(programa: str, comuna: str):
    """Devuelve el nombre del profesional que corresponde, o None si no aplica
    ninguna regla (programa desconocido, o explícitamente sin designar)."""
    if programa in PROGRAMAS_SIN_DESIGNAR:
        return None

    for profesional, programas in PROGRAMAS_PROFESIONAL_FIJO.items():
        if programa in programas:
            return profesional

    if programa in PROGRAMAS_DIVIDIDOS_POR_COMUNA:
        comuna_norm = (comuna or "").strip().upper()
        if comuna_norm in COMUNAS_TAMARA_HUERTA:
            return "Tamara Huerta"
        if comuna_norm in COMUNAS_ROMINA_CANIHUANTE:
            return "Romina Canihuante"
        return None  # comuna no contemplada en la regla

    return None  # programa no contemplado en ninguna regla todavía
