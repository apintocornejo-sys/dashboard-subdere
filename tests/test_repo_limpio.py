"""El repositorio no debe contener credenciales ni datos (están en .gitignore)."""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def test_no_hay_credenciales_versionadas():
    if not shutil.which("git") or not (RAIZ / ".git").exists():
        pytest.skip("no es un repositorio git")
    archivos = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True).stdout.splitlines()
    prohibidos = [a for a in archivos if a.split("/")[-1] in ("token.json", "client_secret.json", ".env")
                  or a.startswith(("para_subir_a_drive/", "data_raw/"))]
    assert not prohibidos, f"Archivos que no deben estar en git: {prohibidos}"
