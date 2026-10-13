# Dashboard SUBDERE Coquimbo (URS)
- `docs/index.html`: dashboard de un solo archivo (GitHub Pages). Lee JSON privados de Google Drive con el token del usuario.
- `scripts/agente_actualizacion.py`: scrapea SUBDERE en Línea (Playwright, navegador visible/Xvfb) y sube JSON a Drive. Corre en GitHub Actions 3 veces/día.
- Acceso: permisos de Drive (lector/editor). Admin: apinto.cornejo@gmail.com. Gestión con `scripts/acceso_dashboard.py`.
## Reglas
- Todo texto dinámico en plantillas HTML va con `accesoEsc(...)`; argumentos de onclick con `accesoEsc(JSON.stringify(x))`.
- Nunca commitear token.json, client_secret.json, data_raw/, para_subir_a_drive/.
- Antes de publicar: `node --check` de los scripts inline y pruebas en navegador (Playwright).
- Respuestas y textos de UI en español (Chile).

## Dónde cambiar listas (docs/index.html)
- Bloque `CONFIGURACIÓN DEL DASHBOARD` (al inicio del script): `PROFESIONALES`, `EVENTOS`, `ESTADOS_REAL`, `TODAS_LAS_COMUNAS`,
  `ABREVIACIONES_ESTADO`, `LUGAR_POR_ESTADO`, `RF_CERRADOS`, etc. Editar solo ahí; `pytest` verifica que no se dupliquen.
- Las reglas de profesional por programa están en `scripts/reglas_profesionales.py` (agente) — mantener `PROFESIONALES` coherente.
- Los IDs de archivos de Drive (`*_FILE_ID`) los reescriben `scripts/crear_archivos_drive.py` y similares: no moverlos de lugar.
## Pendiente de ordenar
- Código duplicado de descarga PDF/XLS por pestaña (Resumen, GR 2026, Rendiciones): unificar en una función común con pruebas antes de tocarlo.
