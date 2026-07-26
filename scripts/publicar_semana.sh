#!/bin/bash
# Comando único para publicar la actualización semanal en GitHub.
# No sube nada a Drive (eso lo haces tú manualmente, arrastrando el archivo
# generado en para_subir_a_drive/proyectos.json) — este script solo se
# encarga de dejar el respaldo del Excel y cualquier cambio de código
# subido a GitHub, sin que tengas que escribir comandos de git a mano.

set -e
cd "$(dirname "$0")/.."

FECHA=$(date +%Y-%m-%d)

if [ -z "$(git status --porcelain)" ]; then
  echo "No hay cambios nuevos que subir a GitHub."
  exit 0
fi

git add -A
git commit -m "Actualización semanal $FECHA"
git push

echo ""
echo "Listo. Respaldo y cambios subidos a GitHub ($FECHA)."
echo "Recuerda: si aún no reemplazaste para_subir_a_drive/proyectos.json"
echo "en tu carpeta de Drive, el dashboard seguirá mostrando los datos anteriores."
