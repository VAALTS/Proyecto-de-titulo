import json
from unittest import mock

from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings


class RespuestaFalsa:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(EMAIL_BACKEND='notificaciones.correo.BrevoEmailBackend', BREVO_API_KEY='clave-de-prueba',
                   DEFAULT_FROM_EMAIL='Adapt Academy <envios@ejemplo.cl>')
class BrevoTests(SimpleTestCase):

    @mock.patch('notificaciones.correo.urllib.request.urlopen', return_value=RespuestaFalsa())
    def test_envia_el_correo_por_la_api_de_brevo(self, urlopen):
        enviados = send_mail('Tu cuenta en Adapt Academy', 'Contraseña temporal: abc', None, ['alumno+demo@ejemplo.cl'])
        self.assertEqual(enviados, 1)
        peticion = urlopen.call_args.args[0]
        self.assertEqual(peticion.full_url, 'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(peticion.headers['Api-key'], 'clave-de-prueba')
        datos = json.loads(peticion.data)
        self.assertEqual(datos['sender'], {'email': 'envios@ejemplo.cl', 'name': 'Adapt Academy'})
        self.assertEqual(datos['to'], [{'email': 'alumno+demo@ejemplo.cl'}])
        self.assertIn('Contraseña temporal', datos['textContent'])

    @override_settings(BREVO_API_KEY='')
    def test_sin_clave_avisa_el_error(self):
        with self.assertRaises(RuntimeError):
            send_mail('Asunto', 'Cuerpo', None, ['a@ejemplo.cl'])
