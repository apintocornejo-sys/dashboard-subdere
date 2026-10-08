# Acceso protegido al dashboard — guía de instalación y administración

El dashboard ahora pide **iniciar sesión con Google**. Los archivos de datos pasan a ser **privados** en Drive y solo los lee
quien tenga permiso. Autorizar a alguien = darle permiso en Drive. La seguridad la aplica Google, no la página.

## A. Instalación (una sola vez, en este orden)

1. **Revisa el repositorio de GitHub** (si tiene datos o credenciales, el resto no sirve):
   `python3 scripts/acceso_dashboard.py repo`  →  si lista archivos: `python3 scripts/acceso_dashboard.py repo --corregir`
   y luego `git add -A && git commit -m "Sacar datos del repositorio" && git push`.
   Si aparecen credenciales (`client_secret.json`, `token.json`), renuévalas en Google Cloud Console.
2. **Instala los archivos:** `unzip -o subdere_acceso_protegido.zip -d ~/Documents/dashboard-subdere/`
3. **Crea los archivos que faltan (privados) y re-aplica los ID:** `python3 scripts/crear_archivos_drive.py`
4. **Publica el dashboard nuevo:** `git add -A && git commit -m "Acceso protegido con Google" && git push` (espera 1-2 min).
   En este punto la página ya pide iniciar sesión, pero los archivos todavía son públicos: sirve para probar sin riesgo.
5. **Prueba tú primero** (ventana normal): abre el sitio → "Continuar con Google" → deberías entrar y ver "Editor" junto a tu correo.
6. **Autoriza al equipo** (una vez por persona):
   `python3 scripts/acceso_dashboard.py autorizar persona@subdere.gov.cl`                (solo ver)
   `python3 scripts/acceso_dashboard.py autorizar persona@subdere.gov.cl --rol editor`   (ver + cargar Datos adicionales y visitas)
   Si tu aplicación de Google está en estado **Prueba** (Cloud Console → Pantalla de consentimiento), agrega también a cada
   persona en **Usuarios de prueba** (máximo 100).
7. **Cierra los archivos públicos:** `python3 scripts/acceso_dashboard.py estado` y luego `python3 scripts/acceso_dashboard.py proteger`.
   Si algún archivo es de OTRA cuenta (p. ej. la institucional), el script lo avisa: ábrelo en Drive con esa cuenta →
   Compartir → Acceso general → **Restringido**, y comparte ese archivo con las personas autorizadas.
8. **Verifica en una ventana de incógnito:** sin sesión no se ve nada · con una cuenta no autorizada dice "Sin acceso" ·
   con una autorizada entra. Repite `estado`: debe decir "Ningún archivo es público".
9. **Limpieza:** en Google Cloud Console elimina la **clave de API** (ya no se usa; los archivos son privados).

El agente y GitHub Actions siguen funcionando igual (son dueños de los archivos).

## B. Día a día

- Autorizar / cambiar rol: `autorizar correo [--rol editor]`  ·  Quitar acceso (inmediato): `quitar correo`
- Ver quién tiene acceso: `listar`  ·  Ver el estado de los archivos: `estado`
- Quien pide acceso desde la pantalla "Sin acceso" te llega por correo (botón "Solicitar acceso").

## C. Volver atrás (emergencia)

1. `python3 scripts/acceso_dashboard.py revertir`  (vuelve a lectura pública)
2. Restaura la versión anterior de `docs/index.html` (`git revert` del commit "Acceso protegido con Google") y publica.

## D. Qué debes saber

- La página (código) sigue siendo pública; **ya no contiene datos**: la instantánea de visitas y los correos de funcionarios salieron del código.
- Google muestra al ingresar "Ver y descargar todos tus archivos de Drive". Es el permiso mínimo que existe para leer archivos compartidos
  por otra cuenta; el dashboard solo lee sus propios archivos. Si la aplicación no está verificada, verán un aviso de "app no verificada".
- Editar datos requiere un segundo permiso (escritura), que se pide solo al pulsar "Habilitar edición con Google".
- La sesión dura 1 hora y se renueva sola; si no puede, aparece "Tu sesión expiró".
- El repositorio conserva el **historial** antiguo aunque quites los archivos (ver paso 1).
