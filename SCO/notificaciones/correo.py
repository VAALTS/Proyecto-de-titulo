"""Envío de correos con la API HTTPS de Brevo.

Railway bloquea el envío por SMTP (Gmail) en los planes Trial y Hobby; la API de Brevo usa HTTPS,
que sí está permitido. Para usarla, en las variables del hosting:

    EMAIL_BACKEND=notificaciones.correo.BrevoEmailBackend
    BREVO_API_KEY=<clave de API de Brevo>
    DEFAULT_FROM_EMAIL=Adapt Academy <correo-verificado-en-brevo@gmail.com>

El remitente (DEFAULT_FROM_EMAIL) debe estar verificado en Brevo (Configuración → Remitentes).
"""
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

URL_BREVO = 'https://api.brevo.com/v3/smtp/email'


class BrevoEmailBackend(BaseEmailBackend):

    def send_messages(self, email_messages):
        clave = getattr(settings, 'BREVO_API_KEY', '')
        if not clave:
            if not self.fail_silently:
                raise RuntimeError('Falta la variable BREVO_API_KEY para enviar correos con Brevo.')
            return 0
        enviados = 0
        for mensaje in email_messages:
            nombre, correo = parseaddr(mensaje.from_email or settings.DEFAULT_FROM_EMAIL)
            datos = {
                'sender': {'email': correo, 'name': nombre or 'Adapt Academy'},
                'to': [{'email': destino} for destino in mensaje.to],
                'subject': mensaje.subject,
                'textContent': mensaje.body,
            }
            if mensaje.cc:
                datos['cc'] = [{'email': destino} for destino in mensaje.cc]
            if mensaje.bcc:
                datos['bcc'] = [{'email': destino} for destino in mensaje.bcc]
            if mensaje.reply_to:
                datos['replyTo'] = {'email': parseaddr(mensaje.reply_to[0])[1]}
            peticion = urllib.request.Request(
                URL_BREVO, data=json.dumps(datos).encode('utf-8'), method='POST',
                headers={'api-key': clave, 'Content-Type': 'application/json', 'Accept': 'application/json'})
            try:
                with urllib.request.urlopen(peticion, timeout=15) as respuesta:
                    if 200 <= respuesta.status < 300:
                        enviados += 1
            except (urllib.error.URLError, TimeoutError) as error:
                detalle = error.read().decode('utf-8', 'replace') if isinstance(error, urllib.error.HTTPError) else ''
                logger.error('Brevo no pudo enviar el correo a %s: %s %s', mensaje.to, error, detalle)
                if not self.fail_silently:
                    raise
        return enviados
