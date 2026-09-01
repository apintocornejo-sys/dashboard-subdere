# Agente de actualización automática — SUBDERE Dashboard

Un solo comando que hace todo el flujo semanal: descarga el Excel desde
SUBDERE en Línea, lo procesa, lo sube a Drive (reemplazando el archivo de
siempre), y deja el respaldo en GitHub.

```bash
python3 scripts/agente_actualizacion.py
```

Si por algún motivo la descarga automática desde SUBDERE falla (es la parte
menos probada de las cuatro), puedes descargar el Excel a mano como siempre
y dejar que el agente haga el resto:

```bash
python3 scripts/agente_actualizacion.py --archivo ~/Downloads/Listado_Proyectos_XXXX.xls
```

Cada corrida queda registrada en `agente_log.txt`, útil para revisar qué
pasó si algo falla.

---

## Configuración inicial (una sola vez)

### 1. Instalar dependencias

```bash
cd ~/Documents/dashboard-subdere
pip3 install playwright google-auth google-auth-oauthlib google-api-python-client --break-system-packages
playwright install chromium
```

### 2. Guardar tus credenciales de SUBDERE

Crea un archivo llamado `.env` en la raíz del proyecto (mismo nivel que
`scripts/`, `docs/`, etc.) con este contenido:

```
SUBDERE_USUARIO=tu_usuario
SUBDERE_CLAVE=tu_clave
```

```bash
chmod 600 .env
```

Este archivo nunca se sube a GitHub (ya está en `.gitignore`).

### 3. Crear la credencial OAuth para que el agente pueda escribir en Drive

Esta es una credencial **distinta** a la API Key que ya tienes (esa solo
sirve para leer; esta es para que el agente pueda actualizar el archivo
por ti, sin que tengas que subirlo a mano cada semana).

1. Ve a https://console.cloud.google.com/ → proyecto `habilidad-platform`
   (el mismo que ya usaste)
2. Menú → "Google Auth Platform" → "Clientes" → **"+ Crear cliente"**
3. Tipo de aplicación: **"App de escritorio"** (Desktop app) — distinto al
   que creaste para el dashboard web
4. Nombre: por ejemplo "Agente actualización SUBDERE"
5. Crear → te ofrece **"Descargar JSON"** — descárgalo
6. Renombra ese archivo descargado a `client_secret.json` y muévelo a la
   raíz del proyecto (`~/Documents/dashboard-subdere/client_secret.json`)

No hace falta agregar ningún "Origen autorizado" para este tipo de
credencial — las apps de escritorio funcionan distinto a las apps web.

### 4. Primera ejecución: autorizar el acceso a Drive

La primera vez que corras el agente (ya sea con `--archivo` o completo), se
va a abrir tu navegador pidiéndote iniciar sesión con Google y autorizar el
acceso a Drive — es el mismo tipo de pantalla que ya viste con el dashboard
("Google no verificó esta app", con la opción de continuar como usuario de
prueba, ya que tu correo ya está agregado ahí).

Una vez que autorices, se guarda un archivo `token.json` en el proyecto y
**no se te va a volver a pedir** en las siguientes ejecuciones (a menos que
revoques el acceso manualmente desde tu cuenta de Google).

---

## Qué hace cada paso internamente

1. **Descarga (Playwright)**: abre `subdereenlinea.gov.cl/inversiones`,
   inicia sesión, selecciona el perfil "Funcionario Técnico URS" si
   corresponde, entra a "Presentación Proyectos", carga el listado, y
   descarga el Excel.
2. **Procesamiento**: reutiliza exactamente el mismo `parse_y_publicar.py`
   que ya conoces — limpia los datos, calcula provincias, descarta la fila
   de "Totales".
3. **Drive**: usa la API de Drive con tu autorización (OAuth) para
   reemplazar el contenido del archivo existente (ID
   `1ZRi0TAbjIozOnZ00cbH9O68sX4Ejlds8`), igual que "Subir nueva versión"
   pero sin que tengas que hacer clic en nada.
4. **GitHub**: mismo comportamiento que `publicar_semana.sh` — agrega,
   comitea y sube automáticamente si hay cambios.

## Si algo falla

El script está separado en 4 pasos independientes — si uno falla, te dice
exactamente cuál y por qué en la terminal y en `agente_log.txt`, sin dejar
las cosas a medias. Los tres casos más probables:

- **Falla el paso 1 (descarga)**: probablemente el sitio de SUBDERE cambió
  algún texto de botón o pantalla. Descarga el Excel a mano y usa
  `--archivo` mientras lo revisamos juntos.
- **Falla el paso 3 (Drive)**: revisa que `client_secret.json` exista y
  que hayas completado la autorización la primera vez.
- **Falla el paso 4 (GitHub)**: normalmente es un tema de sesión de git
  expirada — intenta un `git push` manual para ver el error real.
