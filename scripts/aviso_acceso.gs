/**
 * Aviso de acceso al Dashboard SUBDERE Coquimbo.
 * Envía un correo a DESTINO cada vez que un usuario distinto de los excluidos ingresa (o intenta ingresar sin permiso).
 *
 * INSTALACIÓN (una sola vez, con la cuenta carlos.pinto@subdere.gov.cl):
 *  1. script.google.com → Nuevo proyecto → pegar este archivo como Code.gs.
 *  2. Ejecutar la función «autorizar» una vez y aceptar los permisos (enviar correo y conectarse a servicios externos).
 *  3. Implementar → Nueva implementación → tipo «Aplicación web».
 *       Ejecutar como: Yo      ·      Quién tiene acceso: Cualquier usuario
 *  4. Copiar la URL de la aplicación web (termina en /exec) y entregarla para pegarla en el dashboard (URL_AVISO_ACCESO).
 *  Si cambias este código, usa Implementar → Administrar implementaciones → Editar → Nueva versión (la URL se mantiene).
 */
const DESTINO = 'carlos.pinto@subdere.gov.cl';
const EXCLUIR = ['carlos.pinto@subdere.gov.cl', 'apinto.cornejo@gmail.com'];
const CLIENT_ID = '263773563980-qri1cqlqnk4kirtqmv2en0nblmmlqm1u.apps.googleusercontent.com';  // el del dashboard: rechaza tokens de otras apps
const ESPERA_MIN = 30;   // no repite el mismo aviso (mismo usuario y mismo tipo de evento) dentro de este lapso: evita correos por cada recarga

function autorizar() { MailApp.getRemainingDailyQuota(); UrlFetchApp.fetch('https://oauth2.googleapis.com/tokeninfo?access_token=x', { muteHttpExceptions: true }); }

function doGet() { return ContentService.createTextOutput('ok'); }

function doPost(e) {
  try {
    const d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!d.token) return salida('sin_token');
    // El correo NO se toma de lo que diga la página: se verifica con Google a partir del token del usuario.
    const r = UrlFetchApp.fetch('https://oauth2.googleapis.com/tokeninfo?access_token=' + encodeURIComponent(d.token), { muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) return salida('token_invalido');
    const t = JSON.parse(r.getContentText());
    if (t.aud !== CLIENT_ID && t.azp !== CLIENT_ID) return salida('app_distinta');
    const email = String(t.email || '').toLowerCase();
    if (!email) return salida('sin_correo');
    if (EXCLUIR.indexOf(email) >= 0) return salida('excluido');

    const estado = String(d.estado || 'Ingresó al dashboard').slice(0, 120);
    const cache = CacheService.getScriptCache();
    const clave = 'a_' + Utilities.base64EncodeWebSafe(email + '|' + estado).slice(0, 200);
    if (cache.get(clave)) return salida('repetido');
    cache.put(clave, '1', ESPERA_MIN * 60);

    const disp = d.dispositivo || {};
    const hora = Utilities.formatDate(new Date(), 'America/Santiago', "dd-MM-yyyy HH:mm:ss");
    const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const fila = (k, v) => '<tr><td style="padding:4px 12px 4px 0;color:#555"><b>' + k + '</b></td><td style="padding:4px 0">' + esc(v) + '</td></tr>';
    const sinPermiso = /SIN PERMISO/i.test(estado);
    const html = '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">' +
      '<h3 style="color:#23316C;margin:0 0 8px">' + (sinPermiso ? '⚠️ Intento de acceso sin permiso' : '🔔 Nuevo ingreso al Dashboard SUBDERE') + '</h3>' +
      '<table style="border-collapse:collapse">' +
      fila('Usuario', email) + fila('Evento', estado + (d.detalle ? ' · ' + d.detalle : '')) + fila('Fecha y hora (Chile)', hora) +
      fila('Dispositivo', (disp.tipo || '?') + ' · ' + (disp.so || '?') + ' · ' + (disp.navegador || '?')) +
      fila('Pantalla', d.pantalla) + fila('Táctil (puntos)', d.tactil) + fila('Idioma / zona horaria', (d.idioma || '') + ' / ' + (d.zona || '')) +
      fila('User-Agent', d.ua) + '</table>' +
      '<p style="color:#777;font-size:12px;margin-top:12px">Aviso automático. No se repite el mismo aviso del mismo usuario durante ' + ESPERA_MIN + ' minutos.</p></div>';
    MailApp.sendEmail({ to: DESTINO, subject: (sinPermiso ? '[Dashboard SUBDERE] Acceso SIN permiso: ' : '[Dashboard SUBDERE] Ingreso: ') + email, htmlBody: html, name: 'Dashboard SUBDERE' });
    return salida('enviado');
  } catch (err) { return salida('error: ' + err); }
}
function salida(m) { return ContentService.createTextOutput(m); }
