from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cursos.models import Clase, Curso, Inscripcion, Modulo
from usuarios.models import Rol, Usuario

from .calculos import promedio_ponderado
from .models import Actividad, Calificacion


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
