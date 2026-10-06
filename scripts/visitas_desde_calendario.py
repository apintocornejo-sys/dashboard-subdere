"""
Convierte el calendario de la URS Coquimbo (archivo .ics de Google Calendar) en el archivo
de visitas que usa la pestaña "Despliegue Territorial" del dashboard.

Del calendario SOLO se extrae: fecha, comuna, tipo (reunión / ceremonia / inauguración / visita)
y modalidad (presencial / online). Nunca se guardan títulos, lugares, descripciones ni asistentes.

Reglas (resumen):
  - Se consideran los eventos desde el 1 de marzo de 2026 hasta hoy (no los agendados a futuro).
  - La comuna se determina por el TÍTULO (ignorando "SUBDERE Coquimbo", "Región de Coquimbo", etc.),
    o por el LUGAR (formato Google Maps), o por sectores conocidos (Guayacán, Cruz de Caña, Pichidangui...).
  - Los eventos en la oficina de la URS, Gobierno Regional o Delegación NO son visitas a una comuna
    (salvo que el título diga "visita" / "terreno").
  - Solo se conservan reuniones, ceremonias, inauguraciones y visitas (según palabras del título).
  - "Online" = es una REUNIÓN con enlace de Meet y SIN lugar físico (visitas, ceremonias e inauguraciones son siempre presenciales).
  - Ajustes manuales en scripts/listados/visitas_ajustes.json.

Uso:
    python3 scripts/visitas_desde_calendario.py --ics URS_Coquimbo.ics
    python3 scripts/visitas_desde_calendario.py --ics URS_Coquimbo.ics --revision revision_PRIVADO.xlsx
"""
import re
import sys
import json
import argparse
import unicodedata
import datetime as dt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
AJUSTES_PATH = Path(__file__).resolve().parent / "listados" / "visitas_ajustes.json"
SALIDA_DEFECTO = BASE_DIR / "para_subir_a_drive" / "visitas.json"
DESDE = dt.date(2026, 3, 1)

# Nombres como los escribe el mapa del dashboard
ALIAS_COMUNAS = {
    "LA SERENA": ["la serena"], "COQUIMBO": ["coquimbo"], "ANDACOLLO": ["andacollo"], "LA HIGUERA": ["la higuera"],
    "PAIHUANO": ["paiguano", "paihuano"], "VICUÑA": ["vicuna"], "OVALLE": ["ovalle"], "COMBARBALÁ": ["combarbala"],
    "MONTE PATRIA": ["monte patria"], "PUNITAQUI": ["punitaqui"], "RÍO HURTADO": ["rio hurtado"], "ILLAPEL": ["illapel"],
    "CANELA": ["canela"], "LOS VILOS": ["los vilos"], "SALAMANCA": ["salamanca"],
}
# Sectores / localidades -> comuna
LOCALIDADES = {
    "COQUIMBO": ["cruz de cana", "guayacan", "herradura", "guanaquero", "guanaqueros", "tongoy", "pan de azucar", "penuelas", "las tacas", "lagunillas", "baron"],
    "LA SERENA": ["la compania", "las companias", "el romeral", "altovalsol", "algarrobito", "cuatro esquinas", "las rojas", "el milagro", "san joaquin"],
    "OVALLE": ["fray jorge", "valle del encanto", "sotaqui", "cerrillos de tamaya", "tamaya"],
    "LOS VILOS": ["pichidangui", "caleta chigualoco", "quilimari"],
    "CANELA": ["huentelauquen"],
    "LA HIGUERA": ["punta colorada", "los choros", "caleta hornos", "chungungo", "incahuasi", "la higuera baja"],
    "VICUÑA": ["el arrayan", "la calera", "peralillo", "rivadavia", "el molle"],
    "PAIHUANO": ["pisco elqui", "montegrande", "horcon", "alcohuaz", "chanar blanco"],
    "MONTE PATRIA": ["el palqui", "caren", "chanchoquin"],
    "ILLAPEL": ["carquindano"],
}
# Lugares institucionales regionales / internos (no son visita a una comuna)
LUGARES_REGIONALES = ["subdere urs", "oficina urs", "urs coquimbo", "arturo prat 255", "arturo prat 350", "gobierno regional",
                      "delegacion presidencial", "delegacion provincial", "secretaria regional ministerial", "diplade",
                      "consejo regional", "edificio maria elena", "salon prat", "gabriel gonzales videla", "gabriel gonzalez videla",
                      "dpr", "subdere"]
# Frases institucionales que contienen "Coquimbo" pero no indican la comuna
FRASES_INSTITUCIONALES = ["subdere coquimbo", "urs coquimbo", "region de coquimbo", "gobierno regional de coquimbo",
                          "gobierno regional coquimbo", "delegacion presidencial coquimbo", "delegacion presidencial regional de coquimbo",
                          "gore coquimbo", "iv region de coquimbo", "seremi de coquimbo"]
VIRTUAL = re.compile(r"meet\.google|zoom|teams|webex|online|virtual|videoconferencia|a definir|por definir")
PALABRAS_VISITA = r"\b(visita|visitas|terreno|gira|inspeccion|supervision|evaluacion de danos|evaluacion danos)\b"

# Tipos de actividad (por palabras del título). Prioridad: visita > inauguración > ceremonia > reunión
FAMILIAS = [
    ("visita", PALABRAS_VISITA),
    ("inauguracion", r"\b(inaugura\w*|inaugural)\b"),
    ("ceremonia", r"\b(ceremonia|acto|izamiento|entrega|lanzamiento|cuenta publica|aniversario|desfile|conmemoracion|celebracion|homenaje|firma|premiacion|reconocimiento|dia mundial|dia del|dia de los|dia de las|dia de la|primera piedra|1ra piedra|1era piedra|recepcion oficial|medalla|fiesta|gala|te deum|misa)\b"),
    ("reunion", r"\b(reunion|reuniones|mesa|gabinete|comite|audiencia|asamblea|consejo|conversatorio|coordinacion|taller|encuentro|jornada|sesion|congreso|cumbre|cabildo|charla|seminario|bilateral)\b"),
]
ASOCIACION_CLAVES = ["asociacion de municipalidades", "asociacion de municipios", "municipios rurales", "municipalidades rurales", "amur"]
ASOCIACION = "ASOCIACIÓN"   # clave especial (no es una comuna del mapa)


def norm(texto) -> str:
    n = unicodedata.normalize("NFKD", str(texto or ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in n if not unicodedata.combining(c)).lower()).strip()


def tipo_de(titulo: str) -> str:
    t = norm(titulo)
    for nombre, patron in FAMILIAS:
        if re.search(patron, t):
            return nombre
    return "otro"


def _comunas_en(texto_norm: str) -> list:
    n = f" {texto_norm} "
    return [c for c, al in ALIAS_COMUNAS.items() if any(f" {a} " in n for a in al)]


def _localidad(texto_norm: str) -> list:
    n = f" {texto_norm} "
    return [c for c, ls in LOCALIDADES.items() if any(f" {l} " in n for l in ls)]


def _titulo_limpio(titulo: str) -> str:
    n = norm(titulo)
    for frase in FRASES_INSTITUCIONALES:
        n = n.replace(frase, " ")
    return re.sub(r"\s+", " ", n).strip()


def _lugar_fisico(lugar: str) -> bool:
    l = (lugar or "").strip()
    return bool(l) and not VIRTUAL.search(l.lower()) and not l.lower().startswith("http")


def _comuna_de_lugar(lugar: str):
    """Comuna según el lugar (formato Google Maps: 'Sitio, Dirección, CP Comuna, Región, País')."""
    if not (lugar or "").strip():
        return None
    segs = [s.strip() for s in lugar.split(",") if s.strip()]
    for s in reversed(segs):
        ns = norm(s)
        if ns in ("coquimbo", "chile", "region de coquimbo"):
            continue
        c = _comunas_en(re.sub(r"region de coquimbo|coquimbo chile", "", ns))
        if c:
            return c[-1]
    loc = _localidad(norm(lugar))
    if loc:
        return loc[0]
    if _comunas_en(norm(segs[0] if segs else "")) == ["COQUIMBO"] and norm(lugar).endswith("coquimbo chile"):
        return "COQUIMBO"
    return None


def clasificar(ev: dict, ajustes: list) -> dict:
    """Devuelve {fecha, comuna, tipo, online, nivel, cuenta, evidencia}. nivel: valido / regional / sin_comuna / multi."""
    titulo, lugar = ev["titulo"], ev["lugar"]
    tn = _titulo_limpio(titulo)
    online = ev["meet"] and not _lugar_fisico(lugar)
    res = dict(fecha=ev["ini"], titulo=titulo, lugar=lugar, comuna=None, tipo=tipo_de(titulo),
               online=online, nivel="sin_comuna", evidencia="")

    # Ajustes manuales
    aj = next((a for a in ajustes if a.get("fecha") == ev["ini"].isoformat()
               and norm(a.get("titulo_contiene", "")) in norm(titulo)), None)
    if aj and aj.get("incluir") is False:
        res.update(nivel="excluido", evidencia="ajuste manual")
        return res
    if aj and aj.get("tipo"):
        res["tipo"] = aj["tipo"]
    # Google agrega Meet automáticamente a casi todos los eventos: solo una REUNIÓN sin lugar físico puede ser online.
    # Una visita, ceremonia o inauguración es siempre presencial.
    res["online"] = bool(ev["meet"] and not _lugar_fisico(lugar) and res["tipo"] == "reunion")

    # Asociación de Municipios Rurales (no es una comuna)
    if any(k in norm(titulo) for k in ASOCIACION_CLAVES) or (aj and aj.get("comuna") == ASOCIACION):
        res.update(comuna=ASOCIACION, nivel="valido", evidencia="asociación")
        return res
    if aj and aj.get("comuna"):
        res.update(comuna=aj["comuna"], nivel="valido", evidencia="ajuste manual")
        if aj.get("online") is not None:
            res["online"] = bool(aj["online"])
        return res

    c_lugar = _comuna_de_lugar(lugar)
    cand = list(dict.fromkeys(_comunas_en(tn)))
    if len(cand) == 1:
        res.update(comuna=cand[0], evidencia="título")
    elif len(cand) > 1:
        if c_lugar in cand:
            res.update(comuna=c_lugar, evidencia="lugar (el título nombra varias)")
        else:
            res.update(nivel="multi", evidencia="título nombra varias comunas: " + ", ".join(cand))
            return res
    elif _localidad(tn):
        res.update(comuna=_localidad(tn)[0], evidencia="localidad en título")
    elif c_lugar:
        res.update(comuna=c_lugar, evidencia="lugar")
    if not res["comuna"]:
        return res

    # Lugar institucional regional: no es una visita a la comuna (salvo "visita"/"terreno" en el título)
    ln = norm(lugar)
    regional = any(f" {k} " in f" {ln} " or ln.startswith(k) for k in LUGARES_REGIONALES)
    if regional and not re.search(PALABRAS_VISITA, tn):
        res["nivel"] = "regional"
        return res
    res["nivel"] = "valido"
    return res


def leer_eventos(ruta_ics: Path) -> list:
    from icalendar import Calendar
    cal = Calendar.from_ical(Path(ruta_ics).read_bytes())
    tz = dt.timezone(dt.timedelta(hours=-3))
    eventos = []
    for c in cal.walk("VEVENT"):
        if str(c.get("STATUS", "")).upper() == "CANCELLED":
            continue
        ini = c.decoded("DTSTART")
        d_ini = ini if not isinstance(ini, dt.datetime) else ini.astimezone(tz).date()
        eventos.append(dict(titulo=str(c.get("SUMMARY", "") or ""), lugar=str(c.get("LOCATION", "") or ""),
                            ini=d_ini, meet=bool(c.get("X-GOOGLE-CONFERENCE"))))
    return eventos


def cargar_ajustes() -> list:
    try:
        return json.loads(AJUSTES_PATH.read_text(encoding="utf-8")).get("ajustes", [])
    except FileNotFoundError:
        return []


def procesar(eventos: list, hoy: dt.date = None, ajustes: list = None) -> dict:
    hoy = hoy or dt.date.today()
    ajustes = cargar_ajustes() if ajustes is None else ajustes
    clasificados = [clasificar(e, ajustes) for e in eventos if DESDE <= e["ini"] <= hoy]
    validos = [r for r in clasificados if r["nivel"] == "valido" and r["tipo"] != "otro"]
    # Una fila por (fecha, comuna, tipo, modalidad): solo estos 4 datos se publican
    unicos = sorted({(r["fecha"].isoformat(), r["comuna"], r["tipo"], bool(r["online"])) for r in validos})
    salida = {
        "desde": DESDE.isoformat(),
        "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "visitas": [dict(fecha=f, comuna=c, tipo=t, online=o) for f, c, t, o in unicos],
    }
    return {"salida": salida, "clasificados": clasificados}


NIVELES = {"valido": "Presencial / online en la comuna", "regional": "En oficina URS / GORE / Delegación",
           "sin_comuna": "Sin comuna identificable", "multi": "Nombra varias comunas", "excluido": "Excluido por ajuste manual"}


def escribir_revision(clasificados: list, ruta: Path):
    import pandas as pd
    filas = []
    for r in clasificados:
        cuenta = "Sí" if (r["nivel"] == "valido" and r["tipo"] != "otro") else "No"
        motivo = (NIVELES[r["nivel"]] if r["nivel"] != "valido" else ("Tipo no reconocido (no es reunión/ceremonia/inauguración/visita)" if r["tipo"] == "otro" else "Cuenta"))
        filas.append({"Fecha": r["fecha"].isoformat(), "Título": r["titulo"][:120], "Lugar": r["lugar"].replace("\n", " ")[:90],
                      "Comuna": r["comuna"] or "", "Tipo": r["tipo"], "Modalidad": "Online" if r["online"] else "Presencial",
                      "Cuenta": cuenta, "Motivo": motivo, "¿Incluir? (escribe Sí)": ""})
    df = pd.DataFrame(filas).sort_values("Fecha")
    resumen = df.groupby(["Cuenta", "Motivo"]).size().reset_index(name="Eventos").sort_values("Eventos", ascending=False)
    rescatables = df[(df["Cuenta"] == "No") & (df["Motivo"].str.startswith("Tipo no reconocido") | df["Motivo"].str.startswith("Sin comuna") | df["Motivo"].str.startswith("Nombra"))]
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        resumen.to_excel(w, sheet_name="Resumen", index=False, startrow=2)
        df.to_excel(w, sheet_name="Todos los eventos", index=False)
        rescatables.to_excel(w, sheet_name="Posibles de rescatar", index=False)
        for nombre, ws in w.sheets.items():
            anchos = (46, 28, 10) if nombre == "Resumen" else (13, 60, 48, 15, 13, 11, 8, 52, 18)
            for col, ancho in zip("ABCDEFGHI", anchos):
                ws.column_dimensions[col].width = ancho
            if nombre != "Resumen":
                ws.auto_filter.ref = ws.dimensions
                ws.freeze_panes = "A2"
        w.sheets["Resumen"]["A1"] = "Clasificación de eventos del calendario URS Coquimbo — DOCUMENTO PRIVADO, NO PUBLICAR"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ics", required=True, help="archivo .ics exportado de Google Calendar")
    ap.add_argument("--salida", default=str(SALIDA_DEFECTO), help="dónde escribir visitas.json")
    ap.add_argument("--revision", help="si se indica, escribe una planilla PRIVADA con la clasificación de cada evento")
    args = ap.parse_args(argv)

    resultado = procesar(leer_eventos(Path(args.ics)))
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultado["salida"], ensure_ascii=False), encoding="utf-8")
    v = resultado["salida"]["visitas"]
    print(f"Visitas únicas guardadas: {len(v)} (solo fecha, comuna, tipo y modalidad) -> {salida}")
    if args.revision:
        escribir_revision(resultado["clasificados"], Path(args.revision))
        print(f"Planilla privada de revisión: {args.revision}")


if __name__ == "__main__":
    main()
