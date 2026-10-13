"""Agrega integrity (SRI) y crossorigin a los <script src> de CDN de docs/index.html.
Uso (desde la raíz del repo, con internet):  python3 scripts/agregar_sri.py docs/index.html
Descarga con curl (usa los certificados del sistema). Si un CDN cambia el archivo,
el navegador lo bloquea (esa es la idea)."""
import sys, re, base64, hashlib, subprocess
p = sys.argv[1] if len(sys.argv) > 1 else "docs/index.html"
s = open(p, encoding="utf-8").read()
def f(m):
    tag, url = m.group(0), m.group(1)
    if "integrity=" in tag or "accounts.google.com" in url:
        return tag
    data = subprocess.run(["curl", "-fsSL", "--max-time", "60", url], capture_output=True, check=True).stdout
    h = "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()
    print(url, h)
    return tag.replace("<script ", f'<script integrity="{h}" crossorigin="anonymous" ', 1)
s = re.sub(r'<script[^>]*src="(https://cdn[^"]+)"[^>]*>', f, s)
open(p, "w", encoding="utf-8").write(s)
print("Listo.")
