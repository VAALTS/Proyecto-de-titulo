import json
from datetime import time, timedelta
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cursos.models import BloqueHorario, Clase, Curso, Inscripcion, Material, MensajeForo, Modulo, TemaForo
from evaluaciones.models import Actividad, Calificacion
from notificaciones.models import SolicitudContacto
from usuarios.models import Rol, Usuario

CLAVE = 'clave-segura-123'


def crear_usuario(email, rut, nombre, rol, **campos):
    return Usuario.objects.create_user(email, CLAVE, rut=rut, primer_nombre=nombre, apellido_paterno='Pérez',
                                       rol=rol, **campos)


class ApiTestCase(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', CLAVE, primer_nombre='Admin')
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.alumno = crear_usuario('ana@ejemplo.cl', '22222222-2', 'Ana', Rol.ALUMNO)
        self.otro = crear_usuario('luis@ejemplo.cl', '33333333-3', 'Luis', Rol.ALUMNO)
        self.curso = Curso.objects.create(nombre='Prevención de riesgos', profesor=self.profesor)
        self.inscripcion = Inscripcion.objects.create(alumno=self.alumno, curso=self.curso)
        BloqueHorario.objects.create(curso=self.curso, dia_semana=2, hora_inicio=time(9), hora_fin=time(10, 30),
                                     sala='Sala 1')
        modulo = Modulo.objects.create(curso=self.curso, nombre='Unidad 1')
        self.clase = Clase.objects.create(modulo=modulo, titulo='Clase 1', fecha=timezone.localdate(),
                                          hora_inicio=time(9), hora_fin=time(10))

    def post(self, nombre, datos, token=None, args=None, metodo='post'):
        extra = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return getattr(self.client, metodo)(reverse(nombre, args=args), json.dumps(datos),
                                            content_type='application/json', **extra)

    def get(self, nombre, token, args=None):
        return self.client.get(reverse(nombre, args=args), HTTP_AUTHORIZATION=f'Bearer {token}')

    def token(self, usuario):
        respuesta = self.post('api_login', {'email': usuario.email, 'password': CLAVE})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()['token']


class LoginTests(ApiTestCase):
    """RF-01: mismas credenciales y reglas de bloqueo que la web."""

    def test_entra_con_las_credenciales_de_la_web_sin_distinguir_mayusculas(self):
        respuesta = self.post('api_login', {'email': 'ANA@ejemplo.cl ', 'password': CLAVE})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['usuario']['rol'], 'alumno')
        self.alumno.refresh_from_db()
        self.assertIsNotNone(self.alumno.last_login)

    def test_clave_incorrecta_responde_mensaje_generico(self):
        for email in ['ana@ejemplo.cl', 'nadie@ejemplo.cl']:
            respuesta = self.post('api_login', {'email': email, 'password': 'mala'})
            self.assertEqual(respuesta.status_code, 401)
            self.assertEqual(respuesta.json()['error'], 'Correo o contraseña incorrecta, inténtelo nuevamente')

    def test_tres_intentos_fallidos_bloquean_la_cuenta(self):
        for _ in range(2):
            self.assertEqual(self.post('api_login', {'email': 'ana@ejemplo.cl', 'password': 'mala'}).status_code, 401)
        respuesta = self.post('api_login', {'email': 'ana@ejemplo.cl', 'password': 'mala'})
        self.assertEqual(respuesta.status_code, 423)
        self.assertGreater(respuesta.json()['segundos'], 200)
        # Bloqueada, ni la clave correcta sirve
        self.assertEqual(self.post('api_login', {'email': 'ana@ejemplo.cl', 'password': CLAVE}).status_code, 423)

    def test_administrador_y_clave_temporal_no_entran_a_la_app(self):
        self.assertEqual(self.post('api_login', {'email': 'admin@ejemplo.cl', 'password': CLAVE}).status_code, 403)
        self.alumno.debe_cambiar_contrasena = True
        self.alumno.save()
        respuesta = self.post('api_login', {'email': 'ana@ejemplo.cl', 'password': CLAVE})
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('url_web', respuesta.json())

    def test_token_invalido_o_de_clave_antigua_no_sirve(self):
        token = self.token(self.alumno)
        self.assertEqual(self.get('api_datos', 'basura').status_code, 401)
        self.assertEqual(self.client.get(reverse('api_datos')).status_code, 401)
        self.alumno.set_password('otra-clave-456')
        self.alumno.save()
        self.assertEqual(self.get('api_datos', token).status_code, 401)

    def test_cors_para_la_app(self):
        respuesta = self.client.options(reverse('api_login'), HTTP_ORIGIN='http://localhost:5500')
        self.assertEqual(respuesta.status_code, 204)
        with self.settings(APP_ORIGINS=['https://app.ejemplo.cl']):
            respuesta = self.client.options(reverse('api_login'), HTTP_ORIGIN='http://malo.ejemplo.cl')
            self.assertNotIn('Access-Control-Allow-Origin', respuesta)
            respuesta = self.client.options(reverse('api_login'), HTTP_ORIGIN='https://app.ejemplo.cl')
            self.assertEqual(respuesta['Access-Control-Allow-Origin'], 'https://app.ejemplo.cl')


class RecuperarTests(ApiTestCase):

    def test_envia_clave_temporal_una_vez_cada_15_minutos(self):
        for _ in range(2):
            respuesta = self.post('api_recuperar', {'email': 'ana@ejemplo.cl'})
            self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.debe_cambiar_contrasena)

    def test_no_revela_si_el_correo_existe(self):
        respuesta = self.post('api_recuperar', {'email': 'nadie@ejemplo.cl'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


class DatosTests(ApiTestCase):

    def setUp(self):
        super().setUp()
        self.carpeta = Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='Guías',
                                               tipo=Material.Tipo.CARPETA)
        Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='MDN', tipo=Material.Tipo.ENLACE,
                                url='https://developer.mozilla.org', carpeta=self.carpeta)
        Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='Secreto',
                                tipo=Material.Tipo.ENLACE, url='https://ejemplo.cl', visible=False)
        self.actividad = Actividad.objects.create(clase=self.clase, titulo='Prueba 1', ponderacion=Decimal('40'),
                                                  fecha_limite=timezone.now() + timedelta(days=2))
        Actividad.objects.create(clase=self.clase, titulo='Oculta', ponderacion=Decimal('10'), visible=False,
                                 fecha_limite=timezone.now() + timedelta(days=2))
        Calificacion.objects.create(actividad=self.actividad, inscripcion=self.inscripcion, nota=Decimal('5.5'),
                                    registrada_por=self.profesor)
        self.tema = TemaForo.objects.create(curso=self.curso, autor=self.profesor, titulo='Dudas')
        MensajeForo.objects.create(tema=self.tema, autor=self.profesor, contenido='Pregunten aquí')
        MensajeForo.objects.create(tema=self.tema, autor=self.alumno, contenido='¿Entra la unidad 2?')

    def test_alumno_ve_solo_lo_visible_de_sus_cursos(self):
        datos = self.get('api_datos', self.token(self.alumno)).json()

        self.assertEqual([c['nombre'] for c in datos['cursos']], ['Prevención de riesgos'])
        self.assertEqual(datos['cursos'][0]['bloques'], [{'dia': 2, 'inicio': '09:00', 'fin': '10:30', 'sala': 'Sala 1'}])
        titulos = [m['titulo'] for m in datos['contenido'][str(self.curso.pk)]]
        self.assertEqual(titulos, ['Guías', 'MDN', 'Prueba 1', 'Dudas'])
        foro = datos['contenido'][str(self.curso.pk)][-1]
        self.assertEqual(foro['texto'], 'Pregunten aquí')
        self.assertEqual(foro['comentarios'][0]['texto'], '¿Entra la unidad 2?')
        notas = datos['notas'][str(self.curso.pk)]
        self.assertEqual(notas['notas'][str(self.alumno.pk)][str(self.actividad.pk)], 5.5)
        self.assertEqual(notas['promedio'], 5.5)

    def test_alumno_no_inscrito_no_ve_el_curso(self):
        datos = self.get('api_datos', self.token(self.otro)).json()
        self.assertEqual(datos['cursos'], [])

    def test_profesor_ve_todo_y_la_planilla_de_notas(self):
        datos = self.get('api_datos', self.token(self.profesor)).json()

        self.assertEqual(datos['cursos'][0]['alumnos'], 1)
        titulos = [m['titulo'] for m in datos['contenido'][str(self.curso.pk)]]
        self.assertIn('Secreto', titulos)
        self.assertIn('Oculta', titulos)
        notas = datos['notas'][str(self.curso.pk)]
        self.assertEqual([a['nombre'] for a in notas['alumnos']], ['Ana Pérez'])

    def test_comentar_en_el_foro_solo_del_propio_curso(self):
        respuesta = self.post('api_foro_mensaje', {'contenido': 'Gracias'}, self.token(self.alumno), [self.tema.pk])
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(MensajeForo.objects.filter(contenido='Gracias', autor=self.alumno).exists())
        respuesta = self.post('api_foro_mensaje', {'contenido': 'Hola'}, self.token(self.otro), [self.tema.pk])
        self.assertEqual(respuesta.status_code, 404)

    def test_profesor_guarda_y_borra_notas(self):
        token = self.token(self.profesor)
        respuesta = self.post('api_guardar_notas', {'actividad': self.actividad.pk,
                                                    'notas': {str(self.alumno.pk): '6,2'}}, token, [self.curso.pk])
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Calificacion.objects.get(actividad=self.actividad).nota, Decimal('6.2'))
        for mala in ['7,5', '0', 'abc', '5,55']:
            respuesta = self.post('api_guardar_notas', {'actividad': self.actividad.pk,
                                                        'notas': {str(self.alumno.pk): mala}}, token, [self.curso.pk])
            self.assertEqual(respuesta.status_code, 400, mala)
        self.post('api_guardar_notas', {'actividad': self.actividad.pk, 'notas': {str(self.alumno.pk): None}},
                  token, [self.curso.pk])
        self.assertFalse(Calificacion.objects.exists())

    def test_alumno_no_puede_guardar_notas_ni_tocar_material(self):
        token = self.token(self.alumno)
        respuesta = self.post('api_guardar_notas', {'actividad': self.actividad.pk,
                                                    'notas': {str(self.alumno.pk): '7,0'}}, token, [self.curso.pk])
        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.post('api_material_visibilidad', {}, token, [self.carpeta.pk])
        self.assertEqual(respuesta.status_code, 403)

    def test_profesor_oculta_y_elimina_material(self):
        token = self.token(self.profesor)
        respuesta = self.post('api_material_visibilidad', {'visible': False}, token, [self.carpeta.pk])
        self.assertEqual(respuesta.json()['visible'], False)
        # Una carpeta con contenido no se elimina
        respuesta = self.post('api_material_eliminar', {}, token, [self.carpeta.pk], metodo='delete')
        self.assertEqual(respuesta.status_code, 409)
        enlace = Material.objects.get(titulo='MDN')
        respuesta = self.post('api_material_eliminar', {}, token, [enlace.pk], metodo='delete')
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Material.objects.filter(pk=enlace.pk).exists())


class ContactoTests(ApiTestCase):

    def test_una_solicitud_al_dia_que_llega_a_los_administradores(self):
        token = self.token(self.alumno)
        respuesta = self.post('api_contacto', {'motivo': 'Cursos', 'mensaje': 'No veo mi curso'}, token)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(mail.outbox[0].to, ['admin@ejemplo.cl'])
        self.assertIn('No veo mi curso', mail.outbox[0].body)
        respuesta = self.post('api_contacto', {'mensaje': 'Otra vez'}, token)
        self.assertEqual(respuesta.status_code, 429)
        self.assertEqual(SolicitudContacto.objects.count(), 1)


class AppMovilTests(TestCase):
    """La aplicación móvil se publica en /app/, en la misma dirección que la web y la API."""

    def test_entrega_la_app_y_sus_archivos(self):
        self.assertRedirects(self.client.get('/app'), '/app/', fetch_redirect_response=False)
        respuesta = self.client.get('/app/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b'Adapt Academy', b''.join(respuesta.streaming_content))
        self.assertEqual(self.client.get('/app/config.js')['Cache-Control'], 'no-cache')
        self.assertEqual(self.client.get('/app/manifest.webmanifest').status_code, 200)

    def test_no_entrega_archivos_fuera_de_la_carpeta(self):
        for ruta in ['/app/../.env', '/app/..%2f.env', '/app/no-existe.js']:
            self.assertIn(self.client.get(ruta).status_code, (400, 404), ruta)
