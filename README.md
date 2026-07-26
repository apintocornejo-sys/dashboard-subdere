# Dashboard SUBDERE — Región de Coquimbo (lee en vivo desde Google Drive)

```
subdere_gh/
├── docs/
│   └── index.html            # el dashboard — lee los datos EN VIVO desde Drive
├── para_subir_a_drive/
│   └── proyectos.json        # lo generas cada semana, y lo subes tú a Drive
├── data_raw/                  # respaldo de cada Excel original descargado
└── scripts/
    ├── parse_y_publicar.py    # Excel -> proyectos.json
    └── publicar_semana.sh     # commit + push automático a GitHub
```

## Cómo funciona

`docs/index.html` nunca contiene datos. Cada vez que alguien abre el
dashboard, el navegador pide el archivo directamente a Google Drive vía la
API de Google. Eso significa:

- Tu actualización semanal = reemplazar el archivo en Drive. No hay que
  tocar GitHub para que el dashboard muestre los datos nuevos.
- `publicar_semana.sh` solo se encarga de subir a GitHub el respaldo del
  Excel y cualquier cambio de código (por ejemplo si en el futuro ajustamos
  el diseño) — no mueve el JSON a Drive, eso lo haces tú a mano, tal como
  pediste (actualización manual semanal).

## Configuración inicial (una sola vez, ~5 minutos)

### 1. Crear la API Key de Google Cloud

1. Ve a https://console.cloud.google.com/
2. Crea un proyecto nuevo (o usa uno existente)
3. Ve a "APIs y servicios" → "Biblioteca" → busca "Google Drive API" → Habilitar
4. Ve a "APIs y servicios" → "Credenciales" → "Crear credenciales" → "Clave de API"
5. **Importante — restringe la clave** (para que nadie más la use aunque
   quede visible en el código del dashboard):
   - "Restricciones de aplicación" → "Referentes HTTP (sitios web)" → agrega
     `https://apintocornejo-sys.github.io/*`
   - "Restricciones de API" → selecciona solo "Google Drive API"
6. Copia la clave generada.

### 2. Subir el primer archivo a Drive

1. Corre el parser una vez para generar el archivo inicial:
   ```bash
   cd subdere_gh
   pip3 install pandas lxml html5lib beautifulsoup4
   python3 scripts/parse_y_publicar.py /ruta/al/Listado_Proyectos_XXXXXXXX.xls
   ```
2. Sube `para_subir_a_drive/proyectos.json` a una carpeta en tu Drive.
3. Clic derecho → "Compartir" → "Cualquier persona con el enlace" → rol **Viewer/Lector**.
4. Copia el enlace para obtener el **ID del archivo** — se ve así:
   ```
   https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view
                                    └──────────── este es el ID ───────────┘
   ```

### 3. Conectar el dashboard

Abre `docs/index.html`, busca estas dos líneas cerca del final del archivo
y reemplázalas con tus valores:

```js
const DRIVE_FILE_ID = "PEGA_AQUI_EL_ID_DEL_ARCHIVO_DE_DRIVE";
const DRIVE_API_KEY = "PEGA_AQUI_TU_API_KEY_DE_GOOGLE_CLOUD";
```

Sube ese cambio a GitHub (con `./scripts/publicar_semana.sh` o git normal).
Este paso solo se hace una vez — después nunca más necesitas tocar el HTML.

## Flujo semanal (de ahí en adelante)

1. Descarga el Excel desde SUBDERE en Línea (como siempre).
2. Corre:
   ```bash
   python3 scripts/parse_y_publicar.py /ruta/al/Listado_Proyectos_XXXXXXXX.xls
   ```
3. Ve a Drive, abre el archivo `proyectos.json` que ya subiste, y
   reemplázalo con la nueva versión generada en `para_subir_a_drive/` —
   usa **"Administrar versiones" → "Subir nueva versión"** (no borres y
   subas uno nuevo, porque eso cambiaría el ID del archivo y el dashboard
   dejaría de encontrarlo).
4. Corre el comando único para dejar todo respaldado en GitHub:
   ```bash
   ./scripts/publicar_semana.sh
   ```
5. Listo. El dashboard ya muestra los datos nuevos apenas actualizas Drive
   (paso 3) — no depende de GitHub para eso.

## Notas sobre la API Key pública

La clave queda visible en el código fuente del dashboard (es inevitable en
una app 100% estática sin backend). Por eso el paso de restringirla por
"Referentes HTTP" en el punto 1 es importante: con esa restricción, la
clave solo funciona si la petición viene desde tu dominio de GitHub Pages,
así que aunque alguien la vea, no puede usarla desde otro sitio. Además,
como el archivo de Drive es de solo lectura pública, no hay riesgo de que
alguien modifique o borre tus datos con esa clave.

## Previsualizar localmente antes de configurar Drive

```bash
cd subdere_gh/docs
python3 -m http.server 8000
```
Abre http://localhost:8000 — mostrará el mensaje de error hasta que
configures `DRIVE_FILE_ID` y `DRIVE_API_KEY`.

## Indicadores incluidos

- **Resumen**: KPIs, distribución por estado, por programa, aporte por
  provincia, tipo de acción (top 10), aporte promedio por estado
- **Provincias/Comunas**: tabla jerárquica con N° proyectos, aporte total,
  promedio y %
- **Programas**: distribución y tabla con %
- **Evolución**: aporte y N° de proyectos por año de aprobación
- **Tabla dinámica**: buscador, orden por columna, paginación

Filtros (Provincia, Comuna, Programa, Estado, Año Aprobación) en vivo, sin recargar.
