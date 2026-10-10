# Dashboard SUBDERE Coquimbo (URS)
- `docs/index.html`: dashboard de un solo archivo (GitHub Pages). Lee JSON privados de Google Drive con el token del usuario.
- `scripts/agente_actualizacion.py`: scrapea SUBDERE en Línea (Playwright, navegador visible/Xvfb) y sube JSON a Drive. Corre en GitHub Actions 3 veces/día.
- Acceso: permisos de Drive (lector/editor). Admin: apinto.cornejo@gmail.com. Gestión con `scripts/acceso_dashboard.py`.
## Reglas
- Todo texto dinámico en plantillas HTML va con `accesoEsc(...)`; argumentos de onclick con `accesoEsc(JSON.stringify(x))`.
- Nunca commitear token.json, client_secret.json, data_raw/, para_subir_a_drive/.
- Antes de publicar: `node --check` de los scripts inline y pruebas en navegador (Playwright).
- Respuestas y textos de UI en español (Chile).
