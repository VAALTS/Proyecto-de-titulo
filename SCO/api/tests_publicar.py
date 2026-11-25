"""Pruebas de lo que se agregó para la presentación: publicar desde la app, encuestas, doble perfil,
notificaciones push y recordatorios."""
import json
import shutil
import tempfile
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from cursos.forms import CursoForm, InscripcionForm
from cursos.models import Asistencia, BloqueHorario, Encuesta, Material, MensajeForo, TemaForo, VotoEncuesta
from evaluaciones.models import Actividad, Calificacion
from notificaciones.models import Dispositivo, Notificacion, RecordatorioEnviado
from usuarios.forms import CuentaForm
from usuarios.models import Rol, Usuario

from .tests import CLAVE, ApiTestCase, crear_usuario

PUSH = {'VAPID_PUBLIC_KEY': 'publica', 'VAPID_PRIVATE_KEY': 'privada', 'VAPID_EMAIL': 'x@ejemplo.cl'}


class PublicarDesdeLaAppTests(ApiTestCase):
    """RF-11 de la app: el profesor publica archivos, enlaces, carpetas, foros y encuestas."""

    def setUp(self):
        super().setUp()
        self.token_profesor = self.token(self.profesor)

    def tmp_media(self):
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, ignore_errors=True)
        return carpeta

    def multipart(self, datos, token=None):
        return self.client.post(reverse('api_crear_material', args=[self.curso.pk]), datos,
                                HTTP_AUTHORIZATION=f'Bearer {token or self.token_profesor}')

    def test_datos_del_profesor_traen_las_clases_para_elegir(self):
        datos = self.get('api_datos', self.token_profesor).json()
        self.assertEqual([c['titulo'] for c in datos['clases'][str(self.curso.pk)]], ['Clase 1'])

    def test_publica_un_enlace_y_un_archivo(self):
        respuesta = self.multipart({'tipo': 'enlace', 'titulo': 'MDN', 'url': 'https://developer.mozilla.org',
                                    'clase': self.clase.pk})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        archivo = SimpleUploadedFile('guia.pdf', b'%PDF-1.4 prueba', content_type='application/pdf')
        with self.settings(MEDIA_ROOT=self.tmp_media()):
            respuesta = self.multipart({'tipo': 'archivo', 'titulo': 'Guía', 'clase': self.clase.pk,
                                        'visible': 'false', 'archivo': archivo})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        guia = Material.objects.get(titulo='Guía')
        self.assertFalse(guia.visible)
        self.assertEqual(guia.subido_por, self.profesor)

    def test_aplica_las_reglas_de_la_web(self):
        malo = SimpleUploadedFile('virus.exe', b'MZ', content_type='application/octet-stream')
        respuesta = self.multipart({'tipo': 'archivo', 'titulo': 'X', 'clase': self.clase.pk, 'archivo': malo})
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.multipart({'tipo': 'enlace', 'titulo': 'Sin clase', 'url': 'https://ejemplo.cl'})
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.multipart({'tipo': 'enlace', 'titulo': 'X', 'url': 'https://ejemplo.cl',
                                    'clase': self.clase.pk}, token=self.token(self.alumno))
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Material.objects.exists())

    def test_carpeta_con_materiales_existentes(self):
        enlace = Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='Suelto',
                                         tipo=Material.Tipo.ENLACE, url='https://ejemplo.cl')
        respuesta = self.multipart({'tipo': 'carpeta', 'titulo': 'Unidad 1', 'clase': self.clase.pk,
                                    'items': [enlace.pk]})
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        enlace.refresh_from_db()
        self.assertEqual(enlace.carpeta.titulo, 'Unidad 1')

    def test_foro_nuevo_con_su_primer_mensaje(self):
        respuesta = self.post('api_crear_foro', {'titulo': 'Dudas', 'contenido': 'Pregunten'},
                              self.token_profesor, [self.curso.pk])
        self.assertEqual(respuesta.status_code, 200)
        tema = TemaForo.objects.get(titulo='Dudas')
        self.assertEqual(tema.mensajes.get().contenido, 'Pregunten')
        respuesta = self.post('api_eliminar_foro', {}, self.token_profesor, [tema.pk], metodo='delete')
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(TemaForo.objects.exists())

    def test_encuesta_votos_y_resultados(self):
        respuesta = self.post('api_crear_encuesta', {'titulo': 'Ayudantía', 'pregunta': '¿Qué día?',
                                                     'opciones': ['Martes', 'Jueves', '']},
                              self.token_profesor, [self.curso.pk])
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        encuesta = Encuesta.objects.get()
        jueves = encuesta.opciones.get(texto='Jueves')
        token_alumno = self.token(self.alumno)
        for _ in range(2):  # votar dos veces deja un solo voto
            self.assertEqual(self.post('api_votar_encuesta', {'opcion': jueves.pk}, token_alumno,
                                       [encuesta.pk]).status_code, 200)
        self.assertEqual(VotoEncuesta.objects.count(), 1)
        item = [m for m in self.get('api_datos', token_alumno).json()['contenido'][str(self.curso.pk)]
                if m['tipo'] == 'encuesta'][0]
        self.assertEqual(item['mi_voto'], jueves.pk)
        self.assertEqual([o['votos'] for o in item['opciones']], [0, 1])
        # Un alumno de otro curso no vota; una encuesta oculta no se ve
        self.assertEqual(self.post('api_votar_encuesta', {'opcion': jueves.pk}, self.token(self.otro),
                                   [encuesta.pk]).status_code, 404)
        self.post('api_encuesta_visibilidad', {'visible': False}, self.token_profesor, [encuesta.pk])
        contenido = self.get('api_datos', token_alumno).json()['contenido'][str(self.curso.pk)]
        self.assertFalse([m for m in contenido if m['tipo'] == 'encuesta'])

    def test_encuesta_necesita_dos_opciones(self):
        respuesta = self.post('api_crear_encuesta', {'titulo': 'X', 'pregunta': '¿?', 'opciones': ['Una']},
                              self.token_profesor, [self.curso.pk])
        self.assertEqual(respuesta.status_code, 400)


class DobleRolTests(ApiTestCase):
    """Una cuenta con los dos perfiles cambia entre alumno y profesor; las demás quedan bloqueadas."""

    def test_sin_doble_rol_no_se_cambia(self):
        token = self.token(self.alumno)
        self.assertEqual(self.post('api_cambiar_rol', {'rol': 'profesor'}, token).status_code, 403)
        self.assertEqual(self.get('api_datos', token).json()['usuario']['roles'], ['alumno'])

    def test_con_doble_rol_cambia_de_perfil_sin_tocar_el_rol_guardado(self):
        self.profesor.doble_rol = True
        self.profesor.save()
        self.inscripcion_profesor = self.curso.inscripciones.create(alumno=self.profesor)
        token = self.token(self.profesor)
        respuesta = self.post('api_cambiar_rol', {'rol': 'alumno'}, token)
        self.assertEqual(respuesta.status_code, 200)
        token_alumno = respuesta.json()['token']
        datos = self.get('api_datos', token_alumno).json()
        self.assertEqual(datos['usuario']['rol'], 'alumno')
        self.assertEqual(datos['usuario']['roles'], ['alumno', 'profesor'])
        self.assertIn('promedio', datos['notas'][str(self.curso.pk)])
        self.profesor.refresh_from_db()
        self.assertEqual(self.profesor.rol, Rol.PROFESOR)
        # Si el administrador le quita el doble perfil, el token de alumno deja de servir
        self.profesor.doble_rol = False
        self.profesor.save()
        self.assertEqual(self.get('api_datos', token_alumno).status_code, 401)

    def test_la_web_lo_ofrece_en_cursos_e_inscripciones(self):
        form = CuentaForm(instance=self.alumno)
        self.assertIn('doble_rol', form.fields)
        self.assertNotIn(self.profesor, InscripcionForm(self.curso).fields['alumnos'].queryset)
        self.profesor.doble_rol = True
        self.profesor.save()
        self.otro.doble_rol = True
        self.otro.save()
        self.assertIn(self.profesor, InscripcionForm(self.curso).fields['alumnos'].queryset)
        self.assertIn(self.otro, CursoForm().fields['profesor'].queryset)


@override_settings(**PUSH)
class NotificacionesTests(ApiTestCase):

    def setUp(self):
        super().setUp()
        Dispositivo.objects.create(usuario=self.alumno, endpoint='https://push.ejemplo.cl/1', p256dh='p', auth='a')

    def test_registra_y_quita_el_telefono(self):
        token = self.token(self.otro)
        suscripcion = {'endpoint': 'https://push.ejemplo.cl/2', 'keys': {'p256dh': 'x', 'auth': 'y'}}
        self.assertEqual(self.post('api_dispositivo', suscripcion, token).status_code, 200)
        self.assertTrue(Dispositivo.objects.filter(usuario=self.otro).exists())
        self.post('api_dispositivo', {'endpoint': 'https://push.ejemplo.cl/2'}, token, metodo='delete')
        self.assertFalse(Dispositivo.objects.filter(usuario=self.otro).exists())
        self.assertEqual(self.get('api_datos', token).json()['push'], 'publica')

    @mock.patch('notificaciones.push.webpush')
    def test_avisa_material_nota_y_foro(self, webpush):
        with mock.patch('threading.Thread') as hilo, self.captureOnCommitCallbacks(execute=True):
            hilo.side_effect = lambda target, daemon: mock.Mock(start=target)
            Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='Guía 2',
                                    tipo=Material.Tipo.ENLACE, url='https://ejemplo.cl')
            actividad = Actividad.objects.create(clase=self.clase, titulo='Prueba', ponderacion=Decimal('50'),
                                                 fecha_limite=timezone.now() + timedelta(days=3))
            Calificacion.objects.create(actividad=actividad, inscripcion=self.inscripcion, nota=Decimal('6.5'),
                                        registrada_por=self.profesor)
            tema = TemaForo.objects.create(curso=self.curso, autor=self.profesor, titulo='Dudas')
            MensajeForo.objects.create(tema=tema, autor=self.profesor, contenido='Hola')
        titulos = [json.loads(llamada.kwargs['data'])['title'] for llamada in webpush.call_args_list]
        self.assertEqual(titulos, ['Nuevo material en Prevención de riesgos',
                                   'Nueva actividad en Prevención de riesgos',
                                   'Nueva nota en Prevención de riesgos',
                                   'Nuevo tema en el foro de Prevención de riesgos'])

    @mock.patch('notificaciones.push.webpush')
    def test_material_oculto_no_avisa(self, webpush):
        with self.captureOnCommitCallbacks(execute=True):
            Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='Oculto',
                                    tipo=Material.Tipo.ENLACE, url='https://ejemplo.cl', visible=False)
        webpush.assert_not_called()

    @mock.patch('notificaciones.push.webpush')
    def test_recordatorios_de_entrega_y_de_clase_una_sola_vez(self, webpush):
        ahora = timezone.localtime()
        Actividad.objects.create(clase=self.clase, titulo='Informe', ponderacion=Decimal('30'),
                                 fecha_limite=timezone.now() + timedelta(hours=2))
        inicio = (ahora + timedelta(minutes=20)).replace(second=0, microsecond=0)
        hay_clase = inicio.date() == ahora.date() and ahora.isoweekday() <= 5
        if hay_clase:
            BloqueHorario.objects.create(curso=self.curso, dia_semana=ahora.isoweekday(), hora_inicio=inicio.time(),
                                         hora_fin=time(23, 59))
        for _ in range(2):
            call_command('enviar_recordatorios', stdout=mock.Mock())
        cuerpos = [json.loads(llamada.kwargs['data']) for llamada in webpush.call_args_list]
        self.assertEqual(cuerpos[0]['title'], 'Faltan 3 horas para la entrega')
        self.assertIn('«Informe»', cuerpos[0]['body'])
        # Push: solo el alumno tiene teléfono registrado. Bandeja: también el profesor recibe el de la clase
        self.assertEqual(len(cuerpos), 2 if hay_clase else 1)
        self.assertEqual(RecordatorioEnviado.objects.count(), 3 if hay_clase else 1)


class NotificacionDePruebaTests(ApiTestCase):

    def test_sin_claves_avisa_que_falta_configurar(self):
        respuesta = self.post('api_probar_push', {}, self.token(self.alumno))
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn('VAPID', respuesta.json()['error'])

    @override_settings(**PUSH)
    @mock.patch('notificaciones.push.webpush')
    def test_envia_la_prueba_al_telefono_registrado(self, webpush):
        token = self.token(self.alumno)
        self.assertEqual(self.post('api_probar_push', {}, token).status_code, 400)
        Dispositivo.objects.create(usuario=self.alumno, endpoint='https://push.ejemplo.cl/9', p256dh='p', auth='a')
        respuesta = self.post('api_probar_push', {}, token)
        self.assertEqual(respuesta.json()['entregadas'], 1)
        self.assertEqual(json.loads(webpush.call_args.kwargs['data'])['title'], 'Notificación de prueba')


class BandejaTests(ApiTestCase):
    """La campanita: los avisos quedan guardados aunque el teléfono no tenga push, y se marcan como leídos."""

    def test_asistencia_avisa_al_alumno_y_la_bandeja_se_lee(self):
        asistencia = Asistencia.objects.create(clase=self.clase, inscripcion=self.inscripcion,
                                               registrada_por=self.profesor, presente=True)
        token = self.token(self.alumno)
        bandeja = self.get('api_datos', token).json()['notificaciones']
        self.assertEqual(bandeja['sin_leer'], 1)
        self.assertEqual(bandeja['lista'][0]['titulo'], 'Asistencia: presente')
        self.assertIn('«Clase 1»', bandeja['lista'][0]['cuerpo'])
        # Volver a guardar lo mismo no avisa de nuevo; corregir a ausente sí
        asistencia.save()
        asistencia.presente = False
        asistencia.save()
        self.assertEqual(Notificacion.objects.filter(usuario=self.alumno).count(), 2)
        respuesta = self.post('api_notificaciones_leidas', {}, token)
        self.assertEqual(respuesta.json()['sin_leer'], 0)
        self.assertFalse(Notificacion.objects.filter(leida=False).exists())

    def test_cada_uno_ve_solo_sus_avisos(self):
        Notificacion.objects.create(usuario=self.otro, titulo='Privado', cuerpo='x')
        bandeja = self.get('api_notificaciones', self.token(self.alumno)).json()
        self.assertEqual(bandeja['lista'], [])
        self.post('api_notificaciones_leidas', {}, self.token(self.alumno))
        self.assertFalse(Notificacion.objects.get(titulo='Privado').leida)

    def test_recordatorios_quedan_en_la_bandeja_aunque_no_haya_telefono(self):
        Actividad.objects.create(clase=self.clase, titulo='Informe', ponderacion=Decimal('30'),
                                 fecha_limite=timezone.now() + timedelta(hours=2))
        call_command('enviar_recordatorios', stdout=mock.Mock())
        self.assertTrue(Notificacion.objects.filter(usuario=self.alumno, titulo='Faltan 3 horas para la entrega').exists())


class AsistenciaEnLaAppTests(ApiTestCase):
    """El porcentaje cuenta todas las clases del curso: llega a 100 % cuando el alumno fue a todas."""

    def test_porcentaje_sobre_todas_las_clases_del_curso(self):
        from cursos.models import Clase
        modulo = self.clase.modulo
        hoy = timezone.localdate()
        segunda = Clase.objects.create(modulo=modulo, titulo='Clase 2', fecha=hoy, hora_inicio=time(11), hora_fin=time(12))
        Clase.objects.create(modulo=modulo, titulo='Clase 3', fecha=hoy + timedelta(days=7), hora_inicio=time(9),
                             hora_fin=time(10))
        Clase.objects.create(modulo=modulo, titulo='Clase 4', fecha=hoy + timedelta(days=14), hora_inicio=time(9),
                             hora_fin=time(10))
        Asistencia.objects.create(clase=self.clase, inscripcion=self.inscripcion, registrada_por=self.profesor,
                                  presente=True)
        Asistencia.objects.create(clase=segunda, inscripcion=self.inscripcion, registrada_por=self.profesor,
                                  presente=False)
        curso = self.get('api_datos', self.token(self.alumno)).json()['cursos'][0]
        detalle = curso['asistencia_detalle']
        self.assertEqual(curso['asistencia'], 25)
        self.assertEqual((detalle['total'], detalle['presentes'], detalle['ausentes']), (4, 1, 1))
        self.assertEqual([c['estado'] for c in detalle['clases']], ['presente', 'ausente', 'proxima', 'proxima'])
