"""La hora que se publica ("Actualizado: ...") debe ser la de Chile, no la del servidor (UTC en GitHub Actions)."""
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ARCHIVOS = ["agente_actualizacion.py", "parse_y_publicar.py", "rendiciones_financiero.py", "visitas_desde_calendario.py"]


def test_sin_reloj_local_del_servidor():
    for nombre in ARCHIVOS:
        texto = (SCRIPTS / nombre).read_text(encoding="utf-8")
        sin_helper = re.sub(r'datetime\.now\(ZoneInfo\("America/Santiago"\)\)', "", texto)
        assert "datetime.now()" not in sin_helper, f"{nombre}: usa la hora del servidor; usar ahora_chile()"
        assert "date.today()" not in sin_helper, f"{nombre}: date.today() depende de la zona del servidor"
        assert "America/Santiago" in texto, nombre


def test_ahora_chile_es_hora_chilena():
    import importlib.util
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    spec = importlib.util.spec_from_file_location("parse_y_publicar", SCRIPTS / "parse_y_publicar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    esperado = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    assert abs((mod.ahora_chile() - esperado).total_seconds()) < 5
