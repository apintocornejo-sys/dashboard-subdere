"""Revisiones estáticas de docs/index.html (seguridad y sintaxis). No necesitan navegador ni internet."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "docs" / "index.html").read_text(encoding="utf-8")


def test_sintaxis_javascript(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node no está instalado")
    bloques = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", HTML, re.S)
    assert bloques
    for i, b in enumerate(bloques):
        f = tmp_path / f"b{i}.js"
        f.write_text(b, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[:500]


def test_scripts_de_cdn_con_sri():
    tags = re.findall(r"<script[^>]*src=\"(https://[^\"]+)\"[^>]*>", HTML)
    sin_sri = [t for t in re.findall(r"<script[^>]*src=\"https://[^\"]+\"[^>]*>", HTML)
               if "accounts.google.com" not in t and "integrity=" not in t]
    assert tags and not sin_sri, f"Scripts sin integrity: {sin_sri}"


def test_sin_llaves_ni_secretos():
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", HTML), "Hay una llave de API en el HTML"
    assert "GOCSPX-" not in HTML, "Hay un client secret en el HTML"


def test_csp_y_acceso_protegido():
    assert "Content-Security-Policy" in HTML
    assert re.search(r"const ACCESO_PROTEGIDO = true", HTML)


def test_texto_dinamico_va_escapado():
    """Los campos que vienen de los datos nunca se interpolan crudos en plantillas HTML."""
    campos = "nombre_proyecto|nombre|comuna|programa|subprograma|estado|profesional|provincia|id_proyecto"
    crudos = []
    for n, linea in enumerate(HTML.splitlines(), 1):
        if "|${" in linea:      # claves internas (no HTML), p. ej. `${v.fecha}|${v.comuna}`
            continue
        for m in re.finditer(r"\$\{\s*[A-Za-z_]\w*\.(?:%s)\s*(?:\?\?\s*'[^']*')?\s*\}" % campos, linea):
            crudos.append((n, m.group(0)))
    assert not crudos, f"Interpolaciones sin escapar (usa accesoEsc): {crudos[:10]}"


def test_pestanas_accesibles_por_teclado():
    assert "setAttribute('role', 'tablist')" in HTML
    assert "setAttribute('role', 'tab')" in HTML
    assert "'aria-selected'" in HTML and "ArrowRight" in HTML


def test_graficos_con_texto_alternativo_y_foco_visible():
    assert "setAttribute('role', 'img')" in HTML and "aria-label" in HTML
    assert ":focus-visible" in HTML


def test_csp_permite_hoja_de_fuentes():
    # la hoja de la fuente de respaldo se pide con fetch: sin esto aparece un error de CSP en la consola
    assert "connect-src 'self' https://cdn.jsdelivr.net" in HTML


def test_canvas_no_ensancha_la_pagina_en_celular():
    assert re.search(r"canvas\s*\{\s*max-width:100%", HTML)


def test_listas_de_configuracion_estan_en_un_solo_bloque():
    """Profesionales, eventos, estados y comunas se editan solo en el bloque CONFIGURACIÓN DEL DASHBOARD."""
    ini = HTML.index("CONFIGURACIÓN DEL DASHBOARD")
    fin = HTML.index("fin de la configuración")
    for nombre in ("PROFESIONALES", "TODAS_LAS_COMUNAS", "ABREVIACIONES_ESTADO", "EVENTOS", "ESTADOS_REAL",
                   "RF_CERRADOS", "LUGAR_POR_ESTADO", "LUGARES"):
        posiciones = [m.start() for m in re.finditer(rf"^const {nombre}\b", HTML, re.M)]
        assert len(posiciones) == 1, f"{nombre} debe definirse una sola vez"
        assert ini < posiciones[0] < fin, f"{nombre} debe estar dentro del bloque de configuración"


def test_descargas_comparten_el_mismo_asistente():
    """Los 4 PDF cargan el logo y manejan errores con una sola función; los 4 Excel se guardan con guardarXLS."""
    assert HTML.count("function generarPDFConLogoSeguro(") == 1
    assert HTML.count("generarPDFConLogoSeguro(") == 5          # definición + 4 informes
    assert HTML.count("function guardarXLS(") == 1
    assert HTML.count("guardarXLS(wb, ") == 5          # definición + 4 informes
    assert HTML.count("XLSX.writeFile(") == 1                    # solo dentro de guardarXLS
