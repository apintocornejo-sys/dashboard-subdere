"""Agrega a .github/workflows/actualizacion-automatica.yml el aviso por issue cuando el agente falla.
Uso (desde la raíz del repo):  python3 scripts/aplicar_workflow_aviso.py"""
p = ".github/workflows/actualizacion-automatica.yml"
y = open(p, encoding="utf-8").read()
if "issues: write" in y:
    print("Ya estaba aplicado."); raise SystemExit
y = y.replace("concurrency:", "permissions:\n  contents: write\n  issues: write\n\nconcurrency:", 1)
y = y.rstrip("\n") + """

      - name: Avisar con un issue de GitHub si el agente falló
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh issue create --title "⚠️ Falló la actualización automática ($(date +%F))" \\
            --body "El agente terminó con error. Revisa el log: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}. Causa frecuente: token de Google vencido (renovar el secreto GOOGLE_TOKEN_JSON) o cambio en SUBDERE en Línea." || true
"""
open(p, "w", encoding="utf-8").write(y)
print("Workflow actualizado.")
