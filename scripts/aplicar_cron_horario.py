#!/usr/bin/env python3
"""Hace que la actualización automática corra siempre a las 08:00, 13:00 y 17:00
de Chile, sin importar el cambio de horario verano/invierno.
Uso (desde la carpeta del repo):  python3 scripts/aplicar_cron_horario.py
"""
import re, sys
from pathlib import Path

ruta = Path(".github/workflows/actualizacion-automatica.yml")
t = ruta.read_text(encoding="utf-8")
if "needs: hora" in t:
    print("Ya estaba aplicado."); sys.exit(0)

# 1) cron: ambos husos (verano UTC-3 e invierno UTC-4)
ini = t.index("    # Los horarios de \"cron\"")
fin = t.index("  workflow_dispatch")
nuevo_cron = """    # Los horarios de "cron" de GitHub son siempre en UTC.
    # Se programa en AMBOS husos de Chile (verano UTC-3 e invierno UTC-4) y el
    # trabajo "hora" deja pasar solo las ejecuciones que caen a las 08:00,
    # 13:00 o 17:00 reales de Chile (America/Santiago). Así no hay que tocar
    # nada cuando cambia la hora. Las otras ejecuciones se omiten en segundos.
    # Corre de lunes a viernes; para incluir fines de semana, cambiar "1-5" por "*".
    - cron: '0 11,12,16,17,20,21 * * 1-5'
"""
t = t[:ini] + nuevo_cron + t[fin:]

# 2) trabajo de control + dependencia
control = """jobs:
  hora:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    outputs:
      correr: ${{ steps.chk.outputs.correr }}
    steps:
      - id: chk
        name: Verificar que sea hora de ejecución en Chile
        run: |
          H=$(TZ=America/Santiago date +%H)
          echo "Hora actual en Chile: $H h"
          if [ "${{ github.event_name }}" != "schedule" ]; then
            echo "correr=true" >> "$GITHUB_OUTPUT"   # lanzamiento manual: siempre
          else
            case "$H" in
              08|13|17) echo "correr=true" >> "$GITHUB_OUTPUT" ;;
              *)        echo "correr=false" >> "$GITHUB_OUTPUT"; echo "Fuera de horario, se omite." ;;
            esac
          fi

  actualizar:
    needs: hora
    if: needs.hora.outputs.correr == 'true'
"""
t = t.replace("jobs:\n  actualizar:\n", control, 1)
ruta.write_text(t, encoding="utf-8")
print("Listo: horario a prueba de cambio de hora.")
