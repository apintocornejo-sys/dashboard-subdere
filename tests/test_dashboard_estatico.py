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
