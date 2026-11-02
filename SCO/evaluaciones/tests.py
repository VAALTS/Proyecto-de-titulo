import os
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cursos.models import Clase, Curso, Inscripcion, Modulo
from usuarios.models import Rol, Usuario

from .calculos import promedio_ponderado
from .models import Actividad, Alternativa, Calificacion, Entrega, Pregunta


def crear_usuario(email, rut, nombre, rol):
    return Usuario.objects.create_user(email, 'clave-segura-123', rut=rut, primer_nombre=nombre,
                                       apellido_paterno='Pérez', rol=rol)


class PromedioPonderadoTests(TestCase):

    def test_pondera_cada_nota_y_redondea_a_un_decimal(self):
        # 6,0 × 40 % + 4,5 × 60 % = 5,1
        self.assertEqual(promedio_ponderado([(Decimal('6.0'), 40), (Decimal('4.5'), 60)]),
                         (Decimal('5.1'), Decimal('100')))
        # 4,25 se redondea hacia arriba: 4,3
        self.assertEqual(promedio_ponderado([(Decimal('4.0'), 50), (Decimal('4.5'), 50)])[0], Decimal('4.3'))

    def test_con_menos_del_100_por_ciento_es_parcial_sobre_lo_evaluado(self):
        self.assertEqual(promedio_ponderado([(Decimal('6.0'), 30)]), (Decimal('6.0'), Decimal('30')))

    def test_sin_notas_no_hay_promedio(self):
        self.assertEqual(promedio_ponderado([]), (None, Decimal('0')))


class EvaluacionesTestCase(TestCase):

    def setUp(self):
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.ana = crear_usuario('ana@ejemplo.cl', '22222222-2', 'Ana', Rol.ALUMNO)
        self.luis = crear_usuario('luis@ejemplo.cl', '33333333-3', 'Luis', Rol.ALUMNO)
        self.curso = Curso.objects.create(nombre='Liderazgo', profesor=self.profesor)
        self.ins_ana = Inscripcion.objects.create(alumno=self.ana, curso=self.curso)
        self.ins_luis = Inscripcion.objects.create(alumno=self.luis, curso=self.curso)
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')
        self.clase = Clase.objects.create(modulo=modulo, titulo='Introducción', fecha=timezone.localdate(),
                                          hora_inicio='09:00', hora_fin='10:30')
        self.client.force_login(self.profesor)

    def datos_actividad(self, **cambios):
        return {'clase': self.clase.pk, 'titulo': 'Informe', 'tipo': 'archivo', 'ponderacion': '40',
                'fecha_limite': '2026-11-20T23:59', 'descripcion': '', **cambios}

    def crear_actividad(self, titulo='Informe', ponderacion='40'):
        return Actividad.objects.create(clase=self.clase, titulo=titulo, ponderacion=Decimal(ponderacion),
                                        fecha_limite=timezone.now() + timedelta(days=7))

    def calificar(self, actividad, ana='', luis='', obs_ana='', obs_luis=''):
        return self.client.post(reverse('actividad_calificar', args=[actividad.pk]), {
            f'nota_{self.ins_ana.pk}': ana, f'observacion_{self.ins_ana.pk}': obs_ana,
            f'nota_{self.ins_luis.pk}': luis, f'observacion_{self.ins_luis.pk}': obs_luis,
        })


class ActividadTests(EvaluacionesTestCase):
    """RF-11: cada actividad exige su ponderación, y las de un curso suman como máximo 100 %."""

    def test_crear_una_actividad_con_su_ponderacion(self):
        respuesta = self.client.post(reverse('actividad_crear', args=[self.curso.pk]), self.datos_actividad())

        self.assertRedirects(respuesta, f"{reverse('profesor_curso', args=[self.curso.pk])}#actividades",
                             fetch_redirect_response=False)
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.clase, actividad.ponderacion, actividad.curso),
                         (self.clase, Decimal('40'), self.curso))

    def test_la_ponderacion_es_obligatoria_y_entre_0_y_100(self):
        for ponderacion in ['', '0', '-5', '120']:
            with self.subTest(ponderacion=ponderacion):
                respuesta = self.client.post(reverse('actividad_crear', args=[self.curso.pk]),
                                             self.datos_actividad(ponderacion=ponderacion))
                self.assertContains(respuesta, '"modalActividad"')
        self.assertFalse(Actividad.objects.exists())

    def test_las_ponderaciones_del_curso_no_pasan_de_100(self):
        self.crear_actividad('Prueba 1', '70')

        respuesta = self.client.post(reverse('actividad_crear', args=[self.curso.pk]),
                                     self.datos_actividad(ponderacion='40'))

        self.assertContains(respuesta, 'Puede asignar como máximo 30 %')
        self.client.post(reverse('actividad_crear', args=[self.curso.pk]), self.datos_actividad(ponderacion='30'))
        self.assertEqual(Actividad.objects.count(), 2)

    def test_al_editar_no_se_cuenta_su_propia_ponderacion(self):
        actividad = self.crear_actividad('Prueba 1', '100')

        self.client.post(reverse('actividad_editar', args=[actividad.pk]),
                         self.datos_actividad(titulo='Prueba única', ponderacion='100'))

        actividad.refresh_from_db()
        self.assertEqual(actividad.titulo, 'Prueba única')

    def test_solo_se_eligen_clases_del_mismo_curso(self):
        otro = Curso.objects.create(nombre='Otro', profesor=self.profesor)
        clase_ajena = Clase.objects.create(modulo=Modulo.objects.create(curso=otro, nombre='M'), titulo='Ajena',
                                           fecha=timezone.localdate(), hora_inicio='09:00', hora_fin='10:00')

        self.client.post(reverse('actividad_crear', args=[self.curso.pk]), self.datos_actividad(clase=clase_ajena.pk))

        self.assertFalse(Actividad.objects.exists())

    def test_una_actividad_con_notas_no_se_elimina(self):
        actividad = self.crear_actividad()
        self.calificar(actividad, ana='6,0')

        self.client.post(reverse('actividad_eliminar', args=[actividad.pk]))
        self.assertTrue(Actividad.objects.exists())

        self.calificar(actividad)
        self.client.post(reverse('actividad_eliminar', args=[actividad.pk]))
        self.assertFalse(Actividad.objects.exists())

    def test_otro_profesor_no_accede(self):
        actividad = self.crear_actividad()
        self.client.force_login(crear_usuario('marta@ejemplo.cl', '44444444-4', 'Marta', Rol.PROFESOR))

        self.assertEqual(self.client.get(reverse('actividad_calificar', args=[actividad.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('actividad_crear', args=[self.curso.pk]),
                                          self.datos_actividad()).status_code, 404)
        self.assertEqual(self.client.get(reverse('profesor_evaluaciones')).context['actividades'], [])


class CalificacionTests(EvaluacionesTestCase):
    """RF-11: notas de 1,0 a 7,0, únicas por alumno y actividad, y el promedio ponderado del curso."""

    def test_guardar_notas_con_coma_o_punto_y_observacion(self):
        actividad = self.crear_actividad()

        respuesta = self.calificar(actividad, ana='6,5', luis='4.0', obs_luis='Faltó la conclusión')

        self.assertRedirects(respuesta, f"{reverse('profesor_curso', args=[self.curso.pk])}#calificaciones",
                             fetch_redirect_response=False)
        notas = {c.inscripcion.alumno.primer_nombre: (c.nota, c.observacion, c.registrada_por)
                 for c in Calificacion.objects.select_related('inscripcion__alumno')}
        self.assertEqual(notas, {'Ana': (Decimal('6.5'), '', self.profesor),
                                 'Luis': (Decimal('4.0'), 'Faltó la conclusión', self.profesor)})

    def test_solo_acepta_notas_de_1_a_7_con_un_decimal(self):
        actividad = self.crear_actividad()
        for nota, error in [('0,9', 'La nota mínima es 1,0'), ('7,1', 'La nota máxima es 7,0'),
                            ('5,55', 'Use un solo decimal'), ('cinco', 'Ingrese una nota válida')]:
            with self.subTest(nota=nota):
                self.assertContains(self.calificar(actividad, ana=nota), error)
        self.assertFalse(Calificacion.objects.exists())

    def test_la_base_de_datos_rechaza_notas_fuera_de_escala_y_duplicadas(self):
        actividad = self.crear_actividad()
        Calificacion.objects.create(actividad=actividad, inscripcion=self.ins_ana, registrada_por=self.profesor,
                                    nota=Decimal('5.0'))
        with self.assertRaises(IntegrityError):
            Calificacion.objects.create(actividad=actividad, inscripcion=self.ins_ana, registrada_por=self.profesor,
                                        nota=Decimal('6.0'))

    def test_corregir_y_borrar_una_nota(self):
        actividad = self.crear_actividad()
        self.calificar(actividad, ana='5,0', luis='6,0')
        self.calificar(actividad, ana='5,5', luis='')

        self.assertEqual(list(Calificacion.objects.values_list('inscripcion__alumno__primer_nombre', 'nota')),
                         [('Ana', Decimal('5.5'))])

    def test_una_observacion_sin_nota_no_se_guarda(self):
        actividad = self.crear_actividad()

        self.assertContains(self.calificar(actividad, obs_ana='Muy bien'), 'Ingrese la nota para guardar')

    def test_la_planilla_del_curso_muestra_el_promedio_ponderado(self):
        informe = self.crear_actividad('Informe', '40')
        prueba = self.crear_actividad('Prueba', '60')
        self.calificar(informe, ana='6,0', luis='3,0')
        self.calificar(prueba, ana='4,5')

        respuesta = self.client.get(reverse('profesor_curso', args=[self.curso.pk]))

        filas = {f['inscripcion'].alumno.primer_nombre: (f['promedio'], f['evaluado'])
                 for f in respuesta.context['filas_notas']}
        self.assertEqual(filas, {'Ana': (Decimal('5.1'), Decimal('100')), 'Luis': (Decimal('3.0'), Decimal('40'))})
        self.assertContains(respuesta, 'parcial (40 %)')

    def test_gestion_de_evaluaciones_muestra_lo_pendiente(self):
        actividad = self.crear_actividad()
        self.calificar(actividad, ana='6,0')

        respuesta = self.client.get(reverse('profesor_evaluaciones'))

        self.assertEqual([(a.titulo, a.calificadas, a.inscritos) for a in respuesta.context['actividades']],
                         [('Informe', 1, 2)])
        self.assertContains(respuesta, '1 de 2')
        self.assertContains(self.client.get(reverse('profesor_inicio')), f'href="{reverse("profesor_evaluaciones")}"')


class FormularioTests(EvaluacionesTestCase):
    """Constructor de formularios en línea: preguntas de alternativas y de desarrollo."""

    def setUp(self):
        super().setUp()
        self.actividad = Actividad.objects.create(clase=self.clase, titulo='Control', ponderacion=Decimal('20'),
                                                  tipo=Actividad.Tipo.FORMULARIO,
                                                  fecha_limite=timezone.now() + timedelta(days=7))

    def crear_pregunta(self, **cambios):
        datos = {'enunciado': '¿Cuánto es 2 + 2?', 'tipo': 'alternativas', 'puntaje': '2',
                 'alternativa': ['3', '4', ''], 'correcta': '1', **cambios}
        return self.client.post(reverse('pregunta_crear', args=[self.actividad.pk]), datos)

    def test_crear_una_pregunta_de_alternativas(self):
        respuesta = self.crear_pregunta()

        self.assertRedirects(respuesta, reverse('actividad_formulario', args=[self.actividad.pk]),
                             fetch_redirect_response=False)
        pregunta = self.actividad.preguntas.get()
        self.assertEqual(list(pregunta.alternativas.values_list('texto', 'es_correcta')),
                         [('3', False), ('4', True)])

    def test_la_fila_vacia_no_desplaza_la_alternativa_correcta(self):
        self.crear_pregunta(alternativa=['', 'Sí', 'No'], correcta='2')

        self.assertEqual(Alternativa.objects.get(es_correcta=True).texto, 'No')

    def test_crear_una_pregunta_de_desarrollo_ignora_las_alternativas(self):
        self.crear_pregunta(tipo='desarrollo', alternativa=['x', 'y'], correcta='0')

        self.assertFalse(self.actividad.preguntas.get().alternativas.exists())

    def test_las_alternativas_exigen_dos_opciones_y_una_correcta(self):
        casos = [({'alternativa': ['Sola', ''], 'correcta': '0'}, 'Agregue al menos 2 alternativas'),
                 ({'alternativa': ['A', 'B'], 'correcta': ''}, 'Marque cuál es la alternativa correcta'),
                 ({'alternativa': ['A', 'B', ''], 'correcta': '2'}, 'Marque cuál es la alternativa correcta')]
        for cambios, error in casos:
            with self.subTest(error=error):
                respuesta = self.crear_pregunta(**cambios)
                self.assertContains(respuesta, error)
                self.assertEqual(respuesta.context['modal_abierto']['titulo'], 'Agregar pregunta')
        self.assertFalse(self.actividad.preguntas.exists())

    def test_el_enunciado_y_un_puntaje_positivo_son_obligatorios(self):
        for cambios in [{'enunciado': ''}, {'puntaje': '0'}, {'puntaje': ''}]:
            with self.subTest(cambios=cambios):
                self.assertEqual(self.crear_pregunta(**cambios).status_code, 200)
        self.assertFalse(self.actividad.preguntas.exists())

    def test_editar_reemplaza_las_alternativas(self):
        self.crear_pregunta()
        pregunta = self.actividad.preguntas.get()

        self.client.post(reverse('pregunta_editar', args=[pregunta.pk]),
                         {'enunciado': 'Otra', 'tipo': 'alternativas', 'puntaje': '3',
                          'alternativa': ['Uno', 'Dos', 'Tres'], 'correcta': '2'})

        pregunta.refresh_from_db()
        self.assertEqual((pregunta.enunciado, pregunta.puntaje), ('Otra', Decimal('3.0')))
        self.assertEqual(pregunta.alternativas.get(es_correcta=True).texto, 'Tres')
        self.assertEqual(pregunta.alternativas.count(), 3)

    def test_las_preguntas_se_ordenan_y_se_eliminan(self):
        for enunciado in ['Uno', 'Dos']:
            self.crear_pregunta(enunciado=enunciado)
        dos = Pregunta.objects.get(enunciado='Dos')

        self.client.post(reverse('pregunta_mover', args=[dos.pk, 'subir']))
        self.assertEqual(list(self.actividad.preguntas.values_list('enunciado', flat=True)), ['Dos', 'Uno'])

        self.client.post(reverse('pregunta_eliminar', args=[dos.pk]))
        self.assertEqual(list(self.actividad.preguntas.values_list('enunciado', flat=True)), ['Uno'])
        self.assertEqual(self.client.post(reverse('pregunta_mover', args=[dos.pk, 'subir'])).status_code, 404)

    def test_la_pagina_muestra_el_puntaje_total_y_pide_doble_verificacion(self):
        self.crear_pregunta(puntaje='2')
        self.crear_pregunta(puntaje='3.5', tipo='desarrollo')

        respuesta = self.client.get(reverse('actividad_formulario', args=[self.actividad.pk]))

        self.assertContains(respuesta, '5,5')
        self.assertRegex(respuesta.content.decode(), r'id="formPregunta"[^>]*data-confirmar=')
        self.assertRegex(respuesta.content.decode(), r'action="[^"]*/eliminar/"[^>]*data-confirmar=')

    def test_el_curso_enlaza_a_las_preguntas_solo_en_formularios(self):
        self.crear_actividad('Informe', '10')
        self.crear_pregunta()

        respuesta = self.client.get(reverse('profesor_curso', args=[self.curso.pk]))

        self.assertContains(respuesta, 'Preguntas (1)')
        self.assertContains(respuesta, reverse('actividad_formulario', args=[self.actividad.pk]))
        archivo = Actividad.objects.get(titulo='Informe')
        self.assertEqual(self.client.get(reverse('actividad_formulario', args=[archivo.pk])).status_code, 404)

    def test_una_actividad_con_preguntas_no_deja_de_ser_formulario(self):
        self.crear_pregunta()

        respuesta = self.client.post(reverse('actividad_editar', args=[self.actividad.pk]),
                                     self.datos_actividad(tipo='archivo', ponderacion='20'))

        self.assertContains(respuesta, 'Elimínelas antes de cambiar el tipo')
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.tipo, 'formulario')

    def test_otro_profesor_no_accede(self):
        self.crear_pregunta()
        pregunta = self.actividad.preguntas.get()
        self.client.force_login(crear_usuario('marta@ejemplo.cl', '44444444-4', 'Marta', Rol.PROFESOR))

        self.assertEqual(self.client.get(reverse('actividad_formulario', args=[self.actividad.pk])).status_code, 404)
        self.assertEqual(self.crear_pregunta().status_code, 404)
        self.assertEqual(self.client.post(reverse('pregunta_eliminar', args=[pregunta.pk])).status_code, 404)
        self.assertTrue(Pregunta.objects.filter(pk=pregunta.pk).exists())


class CalificacionesAlumnoTests(EvaluacionesTestCase):
    """RF-15: notas agrupadas por curso y promedio ponderado, tal como en la planilla del profesor."""

    def setUp(self):
        super().setUp()
        self.informe = self.crear_actividad('Informe', '40')
        self.prueba = self.crear_actividad('Prueba', '60')
        self.client.force_login(self.ana)

    def notas(self, actividad, inscripcion, nota, observacion=''):
        return Calificacion.objects.create(actividad=actividad, inscripcion=inscripcion, nota=Decimal(nota),
                                           registrada_por=self.profesor, observacion=observacion)

    def resumen(self):
        return self.client.get(reverse('alumno_calificaciones')).context['cursos']

    def test_muestra_cada_nota_con_su_observacion_y_el_promedio_ponderado(self):
        self.notas(self.informe, self.ins_ana, '6.0', 'Buen análisis')
        self.notas(self.prueba, self.ins_ana, '4.5')

        respuesta = self.client.get(reverse('alumno_calificaciones'))

        self.assertContains(respuesta, 'Liderazgo')
        self.assertContains(respuesta, 'Buen análisis')
        self.assertContains(respuesta, '<div class="fs-4 fw-bold">5,1</div>', html=True)
        self.assertNotContains(respuesta, 'parcial (')

    def test_con_notas_pendientes_el_promedio_es_parcial(self):
        self.notas(self.informe, self.ins_ana, '6.0')

        respuesta = self.client.get(reverse('alumno_calificaciones'))

        self.assertEqual(respuesta.context['cursos'][0]['promedio'], Decimal('6.0'))
        self.assertContains(respuesta, 'parcial (40 % evaluado)')
        self.assertContains(respuesta, 'Prueba')

    def test_sin_notas_no_hay_promedio(self):
        self.assertIsNone(self.resumen()[0]['promedio'])

    def test_el_promedio_cambia_apenas_el_profesor_corrige_una_nota(self):
        calificacion = self.notas(self.informe, self.ins_ana, '3.0')
        self.assertEqual(self.resumen()[0]['promedio'], Decimal('3.0'))

        calificacion.nota = Decimal('5.0')
        calificacion.save()

        self.assertEqual(self.resumen()[0]['promedio'], Decimal('5.0'))

    def test_la_actividad_oculta_solo_aparece_si_tiene_nota_y_el_promedio_coincide_con_el_del_profesor(self):
        Actividad.objects.filter(pk=self.prueba.pk).update(visible=False)
        self.notas(self.informe, self.ins_ana, '6.0')
        self.assertEqual([fila['actividad'] for fila in self.resumen()[0]['filas']], [self.informe])

        self.notas(self.prueba, self.ins_ana, '3.0')
        resumen = self.resumen()[0]
        self.assertEqual([fila['actividad'] for fila in resumen['filas']], [self.informe, self.prueba])

        self.client.force_login(self.profesor)
        planilla = self.client.get(reverse('profesor_curso', args=[self.curso.pk])).context['filas_notas']
        fila_ana = next(fila for fila in planilla if fila['inscripcion'] == self.ins_ana)
        self.assertEqual((resumen['promedio'], resumen['evaluado']), (fila_ana['promedio'], fila_ana['evaluado']))

    def test_no_ve_las_notas_de_otros_alumnos(self):
        self.notas(self.informe, self.ins_luis, '2.0', 'Comentario para Luis')

        respuesta = self.client.get(reverse('alumno_calificaciones'))

        self.assertIsNone(respuesta.context['cursos'][0]['promedio'])
        self.assertNotContains(respuesta, 'Comentario para Luis')

    def test_agrupa_por_curso_en_orden_y_sin_retirados_ni_eliminados(self):
        excel = Curso.objects.create(nombre='Excel', profesor=self.profesor)
        modulo = Modulo.objects.create(curso=excel, nombre='Tablas')
        clase = Clase.objects.create(modulo=modulo, titulo='Fórmulas', fecha=timezone.localdate(),
                                     hora_inicio='09:00', hora_fin='10:30')
        tarea = Actividad.objects.create(clase=clase, titulo='Tarea', ponderacion=Decimal('100'),
                                         fecha_limite=timezone.now())
        ins_excel = Inscripcion.objects.create(alumno=self.ana, curso=excel)
        self.notas(tarea, ins_excel, '7.0')
        self.notas(self.informe, self.ins_ana, '5.0')
        retirado = Curso.objects.create(nombre='Retirado', profesor=self.profesor)
        Inscripcion.objects.create(alumno=self.ana, curso=retirado, activa=False)
        eliminado = Curso.objects.create(nombre='Eliminado', profesor=self.profesor)
        Inscripcion.objects.create(alumno=self.ana, curso=eliminado)
        eliminado.eliminar()

        resumen = self.resumen()

        self.assertEqual([(r['curso'].nombre, r['promedio']) for r in resumen],
                         [('Excel', Decimal('7.0')), ('Liderazgo', Decimal('5.0'))])

    def test_curso_sin_actividades_y_alumno_sin_cursos_muestran_un_aviso(self):
        Calificacion.objects.all().delete()
        Actividad.objects.all().delete()
        self.assertContains(self.client.get(reverse('alumno_calificaciones')), 'Este curso aún no tiene actividades')

        self.ins_ana.activa = False
        self.ins_ana.save()
        self.assertContains(self.client.get(reverse('alumno_calificaciones')), 'Aún no estás inscrito')

    def test_el_menu_enlaza_a_las_calificaciones_y_otro_rol_no_entra(self):
        respuesta = self.client.get(reverse('alumno_inicio'))
        self.assertContains(respuesta, f'href="{reverse("alumno_calificaciones")}"')
        self.assertNotContains(respuesta, 'Próximamente')

        self.client.force_login(self.profesor)
        self.assertEqual(self.client.get(reverse('alumno_calificaciones')).status_code, 302)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='adapt_media_'))
class EntregaTests(EvaluacionesTestCase):
    """RF-16: el alumno entrega un archivo hasta la fecha límite y el profesor lo descarga desde la planilla."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.actividad = self.crear_actividad()
        self.url = reverse('alumno_actividad', args=[self.actividad.pk])
        self.client.force_login(self.ana)

    def entregar(self, nombre='informe.pdf', contenido=b'%PDF-1.4 prueba'):
        return self.client.post(self.url, {'archivo': SimpleUploadedFile(nombre, contenido)})

    def vencer(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(fecha_limite=timezone.now() - timedelta(minutes=1))

    def calificar_a_ana(self, nota='6.0', observacion=''):
        return Calificacion.objects.create(actividad=self.actividad, inscripcion=self.ins_ana, nota=Decimal(nota),
                                           registrada_por=self.profesor, observacion=observacion)

    def test_la_pagina_del_curso_lista_las_actividades_visibles_con_su_estado(self):
        oculta = self.crear_actividad('Oculta', '10')
        Actividad.objects.filter(pk=oculta.pk).update(visible=False)
        vencida = self.crear_actividad('Vencida', '10')
        Actividad.objects.filter(pk=vencida.pk).update(fecha_limite=timezone.now() - timedelta(days=1))

        respuesta = self.client.get(reverse('alumno_curso', args=[self.curso.pk]))

        self.assertEqual([a.titulo for a in respuesta.context['actividades']], ['Vencida', 'Informe'])
        self.assertContains(respuesta, f'href="{self.url}"')
        self.assertContains(respuesta, 'Sin entrega')
        self.assertContains(respuesta, 'Pendiente')
        self.assertNotContains(respuesta, 'Oculta')

    def test_el_estado_cambia_al_entregar_y_al_calificar(self):
        self.entregar()
        pagina = reverse('alumno_curso', args=[self.curso.pk])
        self.assertContains(self.client.get(pagina), 'Entregada')

        self.calificar_a_ana('6.5')

        respuesta = self.client.get(pagina)
        self.assertContains(respuesta, 'Calificada')
        self.assertContains(respuesta, '6,5')

    def test_la_actividad_muestra_las_instrucciones_y_la_nota(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(descripcion='Lee el capítulo 1')
        self.calificar_a_ana('3.5', 'Faltó la conclusión')

        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, 'Lee el capítulo 1')
        self.assertContains(respuesta, 'Faltó la conclusión')
        self.assertContains(respuesta, '<div class="fs-4 fw-bold text-danger">3,5</div>', html=True)

    def test_entregar_un_archivo(self):
        respuesta = self.entregar()

        self.assertRedirects(respuesta, self.url, fetch_redirect_response=False)
        entrega = Entrega.objects.get()
        self.assertEqual((entrega.actividad, entrega.inscripcion, entrega.nombre_archivo),
                         (self.actividad, self.ins_ana, 'informe.pdf'))
        self.assertTrue(os.path.exists(entrega.archivo.path))
        pagina = self.client.get(self.url)
        self.assertContains(pagina, 'Tu entrega se guardó')
        self.assertContains(pagina, 'Reemplazar entrega')

    def test_reemplazar_la_entrega_borra_el_archivo_anterior(self):
        self.entregar('primero.pdf')
        anterior = Entrega.objects.get()
        Entrega.objects.filter(pk=anterior.pk).update(fecha_entrega=timezone.now() - timedelta(days=1))

        self.entregar('segundo.pdf')

        entrega = Entrega.objects.get()
        self.assertEqual(entrega.nombre_archivo, 'segundo.pdf')
        self.assertGreater(entrega.fecha_entrega, timezone.now() - timedelta(minutes=1))
        self.assertFalse(os.path.exists(anterior.archivo.path))
        self.assertTrue(os.path.exists(entrega.archivo.path))

    def test_despues_de_la_fecha_limite_no_se_entrega_ni_se_reemplaza(self):
        self.entregar('primero.pdf')
        self.vencer()

        respuesta = self.entregar('segundo.pdf')

        self.assertRedirects(respuesta, self.url, fetch_redirect_response=False)
        self.assertEqual(Entrega.objects.get().nombre_archivo, 'primero.pdf')
        pagina = self.client.get(self.url)
        self.assertContains(pagina, 'ya no recibe entregas')
        self.assertContains(pagina, 'El plazo de entrega ya terminó')
        self.assertNotContains(pagina, 'type="file"')

    def test_despues_de_la_fecha_limite_sin_entrega_se_informa(self):
        self.vencer()

        self.entregar()

        self.assertFalse(Entrega.objects.exists())
        self.assertContains(self.client.get(self.url), 'No registras una entrega')

    def test_una_actividad_calificada_no_acepta_cambios_en_la_entrega(self):
        self.entregar('primero.pdf')
        self.calificar_a_ana()

        self.entregar('segundo.pdf')

        self.assertEqual(Entrega.objects.get().nombre_archivo, 'primero.pdf')
        self.assertContains(self.client.get(self.url), 'ya fue calificada')

    def test_rechaza_formatos_no_permitidos_y_archivos_muy_pesados(self):
        self.assertContains(self.entregar('virus.exe'), 'exe')
        with mock.patch('cursos.forms.TAMANO_MAXIMO_MB', 0.001):
            self.assertContains(self.entregar(contenido=b'x' * 2048), 'pesa más de')
        self.assertFalse(Entrega.objects.exists())

    def test_sin_archivo_lo_pide_y_no_toca_la_entrega_anterior(self):
        self.entregar()
        fecha = Entrega.objects.get().fecha_entrega

        respuesta = self.client.post(self.url, {})

        self.assertContains(respuesta, 'Selecciona el archivo')
        self.assertEqual(Entrega.objects.get().fecha_entrega, fecha)

    def test_un_formulario_en_linea_no_recibe_archivos(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(tipo=Actividad.Tipo.FORMULARIO)

        self.entregar()

        self.assertFalse(Entrega.objects.exists())

    def test_una_actividad_oculta_o_ajena_responde_404(self):
        Actividad.objects.filter(pk=self.actividad.pk).update(visible=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.entregar().status_code, 404)

        Actividad.objects.filter(pk=self.actividad.pk).update(visible=True)
        self.ins_ana.activa = False
        self.ins_ana.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.entregar().status_code, 404)

        ajeno = Curso.objects.create(nombre='Ajeno', profesor=self.profesor)
        modulo = Modulo.objects.create(curso=ajeno, nombre='Tablas')
        clase = Clase.objects.create(modulo=modulo, titulo='Fórmulas', fecha=timezone.localdate(),
                                     hora_inicio='09:00', hora_fin='10:30')
        otra = Actividad.objects.create(clase=clase, titulo='Tarea', ponderacion=Decimal('10'),
                                        fecha_limite=timezone.now() + timedelta(days=1))
        self.assertEqual(self.client.get(reverse('alumno_actividad', args=[otra.pk])).status_code, 404)
        self.assertFalse(Entrega.objects.exists())

    def test_solo_el_alumno_y_su_profesor_descargan_la_entrega(self):
        self.entregar()
        descargar = reverse('entrega_descargar', args=[Entrega.objects.get().pk])

        respuesta = self.client.get(descargar)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('informe.pdf', respuesta['Content-Disposition'])
        self.client.force_login(self.profesor)
        self.assertEqual(self.client.get(descargar).status_code, 200)

        admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        otro_profesor = crear_usuario('marta@ejemplo.cl', '44444444-4', 'Marta', Rol.PROFESOR)
        for usuario in [self.luis, otro_profesor, admin]:
            self.client.force_login(usuario)
            with self.subTest(usuario=usuario.email):
                self.assertEqual(self.client.get(descargar).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(descargar).status_code, 302)

    def test_ocultar_la_actividad_o_retirar_al_alumno_le_quita_la_descarga(self):
        self.entregar()
        descargar = reverse('entrega_descargar', args=[Entrega.objects.get().pk])

        Actividad.objects.filter(pk=self.actividad.pk).update(visible=False)
        self.assertEqual(self.client.get(descargar).status_code, 404)
        Actividad.objects.filter(pk=self.actividad.pk).update(visible=True)
        self.ins_ana.activa = False
        self.ins_ana.save()
        self.assertEqual(self.client.get(descargar).status_code, 404)

        self.client.force_login(self.profesor)
        self.assertEqual(self.client.get(descargar).status_code, 200)

    def test_la_planilla_del_profesor_muestra_quien_entrego(self):
        self.entregar()
        entrega = Entrega.objects.get()
        self.client.force_login(self.profesor)

        respuesta = self.client.get(reverse('actividad_calificar', args=[self.actividad.pk]))

        self.assertContains(respuesta, f'href="{reverse("entrega_descargar", args=[entrega.pk])}"', count=1)
        self.assertContains(respuesta, 'Sin entrega', count=1)

    def test_una_actividad_con_entregas_no_se_elimina_ni_cambia_de_tipo(self):
        self.entregar()
        self.client.force_login(self.profesor)

        respuesta = self.client.post(reverse('actividad_eliminar', args=[self.actividad.pk]), follow=True)
        self.assertContains(respuesta, 'ya tiene entregas de alumnos')
        self.assertTrue(Actividad.objects.filter(pk=self.actividad.pk).exists())

        respuesta = self.client.post(reverse('actividad_editar', args=[self.actividad.pk]),
                                     self.datos_actividad(tipo='formulario'))
        self.assertContains(respuesta, 'no se puede cambiar el tipo')
        self.actividad.refresh_from_db()
        self.assertEqual(self.actividad.tipo, Actividad.Tipo.ARCHIVO)

    def test_la_base_de_datos_rechaza_dos_entregas_del_mismo_alumno(self):
        Entrega.objects.create(actividad=self.actividad, inscripcion=self.ins_ana)

        with self.assertRaises(IntegrityError):
            Entrega.objects.create(actividad=self.actividad, inscripcion=self.ins_ana)

    def test_otro_rol_no_entra(self):
        self.client.force_login(self.profesor)

        self.assertEqual(self.client.get(self.url).status_code, 302)
