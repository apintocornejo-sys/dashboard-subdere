"""Prueba (con Node) la lógica de guardado de Datos adicionales: fusión, conflictos e historial."""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "docs" / "index.html").read_text(encoding="utf-8")


def _bloque(inicio):
    i = HTML.index(inicio)
    j = HTML.index("{", i)
    prof = 0
    for k in range(j, len(HTML)):
        prof += (HTML[k] == "{") - (HTML[k] == "}")
        if prof == 0:
            return HTML[i:k + 1]
    raise AssertionError("bloque sin cerrar")


def test_guardado_fusiona_detecta_conflictos_y_no_pierde_datos(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node no está instalado")
    consts = HTML[HTML.index("let snapshotExtra"):HTML.index("async function guardarDatosExtra() {")]
    codigo = consts + _bloque("async function guardarDatosExtra() {") + "\n" + (RAIZ / "tests/js/guardado_extra_prueba.js").read_text(encoding="utf-8")
    f = tmp_path / "t.js"
    f.write_text(codigo, encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr
