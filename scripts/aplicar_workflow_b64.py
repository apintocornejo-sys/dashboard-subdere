"""Hace que el workflow lea los secretos que existen en GitHub (GOOGLE_*_B64, en Base64).
Uso (desde la raíz del repo):  python3 scripts/aplicar_workflow_b64.py"""
p = ".github/workflows/actualizacion-automatica.yml"
y = open(p, encoding="utf-8").read()
viejo = """          GOOGLE_CLIENT_SECRET_JSON: ${{ secrets.GOOGLE_CLIENT_SECRET_JSON }}
          GOOGLE_TOKEN_JSON: ${{ secrets.GOOGLE_TOKEN_JSON }}
        run: |
          echo "$GOOGLE_CLIENT_SECRET_JSON" > client_secret.json
          echo "$GOOGLE_TOKEN_JSON" > token.json
"""
nuevo = """          GOOGLE_CLIENT_SECRET_B64: ${{ secrets.GOOGLE_CLIENT_SECRET_B64 }}
          GOOGLE_TOKEN_B64: ${{ secrets.GOOGLE_TOKEN_B64 }}
        run: |
          echo "$GOOGLE_CLIENT_SECRET_B64" | base64 -d > client_secret.json
          echo "$GOOGLE_TOKEN_B64" | base64 -d > token.json
          python3 -c "import json; json.load(open('client_secret.json')); json.load(open('token.json')); print('JSON válido ✓')"
"""
if "GOOGLE_TOKEN_B64" in y:
    print("Ya estaba aplicado.")
elif viejo not in y:
    print("No encontré el bloque esperado; no cambié nada."); raise SystemExit(1)
else:
    y = y.replace(viejo, nuevo).replace("renovar el secreto GOOGLE_TOKEN_JSON", "renovar el secreto GOOGLE_TOKEN_B64")
    open(p, "w", encoding="utf-8").write(y)
    print("Workflow ajustado a los secretos _B64.")
