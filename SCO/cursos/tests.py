from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Rol, Usuario

from .models import Curso, Inscripcion


def crear_usuario(email, rut, nombre, rol, **campos):
    return Usuario.objects.create_user(email, 'clave-segura-123', rut=rut, primer_nombre=nombre,
                                       apellido_paterno='Pérez', rol=rol, **campos)


class GestionCursosTests(TestCase):
    """RF-06: crear, consultar, editar y eliminar (borrado lógico) cursos."""

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.client.force_login(self.admin)

    def crear_curso(self, nombre='Prevención de riesgos', **campos):
        return Curso.objects.create(nombre=nombre, profesor=campos.pop('profesor', self.profesor), **campos)

    def test_crear_un_curso_con_profesor_y_lista_de_alumnos_vacia(self):
        respuesta = self.client.post(reverse('curso_crear'), {
            'nombre': 'Liderazgo', 'profesor': self.profesor.pk, 'descripcion': 'Curso de 20 horas'})

        curso = Curso.objects.get(nombre='Liderazgo')
        self.assertRedirects(respuesta, reverse('curso_detalle', args=[curso.pk]), fetch_redirect_response=False)
        self.assertEqual(curso.profesor, self.profesor)
        self.assertTrue(curso.activo)
        self.assertFalse(curso.inscripciones.exists())
        self.assertContains(self.client.get(reverse('curso_detalle', args=[curso.pk])),
                            'Aún no hay alumnos inscritos')

    def test_crear_exige_nombre_y_un_profesor_activo(self):
        inactivo = crear_usuario('marta@ejemplo.cl', '22222222-2', 'Marta', Rol.PROFESOR, is_active=False)
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)

        for datos in [{'nombre': '', 'profesor': self.profesor.pk}, {'nombre': 'X', 'profesor': inactivo.pk},
                      {'nombre': 'X', 'profesor': alumno.pk}]:
            with self.subTest(datos=datos):
                respuesta = self.client.post(reverse('curso_crear'), datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, '"modalCreacion"')
        self.assertFalse(Curso.objects.exists())

    def test_la_lista_busca_por_curso_o_profesor_y_cuenta_los_inscritos(self):
        otro = crear_usuario('marta@ejemplo.cl', '22222222-2', 'Marta', Rol.PROFESOR)
        curso = self.crear_curso('Liderazgo')
        self.crear_curso('Excel avanzado', profesor=otro)
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        Inscripcion.objects.create(alumno=alumno, curso=curso)

        respuesta = self.client.get(reverse('gestion_cursos'))
        self.assertEqual([(c.nombre, c.inscritos) for c in respuesta.context['cursos']],
                         [('Excel avanzado', 0), ('Liderazgo', 1)])

        for busqueda, encontrado, oculto in [('lider', 'Liderazgo', 'Excel'), ('marta', 'Excel', 'Liderazgo')]:
            with self.subTest(busqueda=busqueda):
                respuesta = self.client.get(reverse('gestion_cursos'), {'q': busqueda})
                self.assertContains(respuesta, encontrado)
                self.assertNotContains(respuesta, oculto)

    def test_editar_cambia_nombre_y_profesor(self):
        otro = crear_usuario('marta@ejemplo.cl', '22222222-2', 'Marta', Rol.PROFESOR)
        curso = self.crear_curso()

        self.client.post(reverse('curso_editar', args=[curso.pk]),
                         {'nombre': 'Prevención de riesgos II', 'profesor': otro.pk, 'descripcion': ''})

        curso.refresh_from_db()
        self.assertEqual((curso.nombre, curso.profesor), ('Prevención de riesgos II', otro))

    def test_editar_conserva_al_profesor_actual_aunque_este_desactivado(self):
        curso = self.crear_curso()
        self.profesor.is_active = False
        self.profesor.save()

        self.client.post(reverse('curso_editar', args=[curso.pk]),
                         {'nombre': 'Nuevo nombre', 'profesor': self.profesor.pk, 'descripcion': ''})

        curso.refresh_from_db()
        self.assertEqual(curso.nombre, 'Nuevo nombre')

    def test_eliminar_es_un_borrado_logico_que_conserva_las_inscripciones(self):
        curso = self.crear_curso()
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        Inscripcion.objects.create(alumno=alumno, curso=curso)

        self.assertRedirects(self.client.post(reverse('curso_eliminar', args=[curso.pk])), reverse('gestion_cursos'),
                             fetch_redirect_response=False)

        curso.refresh_from_db()
        self.assertFalse(curso.activo)
        self.assertIsNotNone(curso.eliminado_en)
        self.assertEqual(curso.inscripciones.count(), 1)
        self.assertNotIn(curso, self.client.get(reverse('gestion_cursos')).context['cursos'])
        self.assertIn(curso, self.client.get(reverse('gestion_cursos'), {'eliminados': '1'}).context['cursos'])

    def test_un_curso_eliminado_no_se_edita_pero_se_puede_restaurar(self):
        curso = self.crear_curso()
        curso.eliminar()

        respuesta = self.client.post(reverse('curso_editar', args=[curso.pk]),
                                     {'nombre': 'Otro', 'profesor': self.profesor.pk, 'descripcion': ''})
        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(self.client.get(reverse('curso_detalle', args=[curso.pk])), 'Restaurar curso')

        self.client.post(reverse('curso_restaurar', args=[curso.pk]))
        curso.refresh_from_db()
        self.assertTrue(curso.activo)
        self.assertIsNone(curso.eliminado_en)

    def test_los_cambios_piden_doble_verificacion(self):
        curso = self.crear_curso()

        self.assertRegex(self.client.get(reverse('gestion_cursos')).content.decode(),
                         r'id="formCreacion"[^>]*data-confirmar=')
        detalle = self.client.get(reverse('curso_detalle', args=[curso.pk])).content.decode()
        self.assertRegex(detalle, r'id="formEdicion"[^>]*data-confirmar=')
        self.assertRegex(detalle, r'action="[^"]*/eliminar/"[^>]*data-confirmar=')

    def test_solo_el_administrador_gestiona_cursos(self):
        curso = self.crear_curso()
        self.client.force_login(self.profesor)

        for nombre_url, args in [('gestion_cursos', []), ('curso_detalle', [curso.pk])]:
            with self.subTest(pagina=nombre_url):
                self.assertEqual(self.client.get(reverse(nombre_url, args=args)).status_code, 302)
        self.client.post(reverse('curso_eliminar', args=[curso.pk]))
        curso.refresh_from_db()
        self.assertTrue(curso.activo)

    def test_un_alumno_no_se_inscribe_dos_veces_en_el_mismo_curso(self):
        curso = self.crear_curso()
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        Inscripcion.objects.create(alumno=alumno, curso=curso)

        with self.assertRaises(IntegrityError):
            Inscripcion.objects.create(alumno=alumno, curso=curso)


class InscripcionTests(TestCase):
    """RF-07: inscribir alumnos en un curso con un buscador y reflejarlo en el curso y en el perfil del alumno."""

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.ana = crear_usuario('ana@ejemplo.cl', '22222222-2', 'Ana', Rol.ALUMNO)
        self.luis = crear_usuario('luis@ejemplo.cl', '33333333-3', 'Luis', Rol.ALUMNO)
        self.curso = Curso.objects.create(nombre='Liderazgo', profesor=self.profesor)
        self.client.force_login(self.admin)

    def inscribir(self, *alumnos, curso=None):
        curso = curso or self.curso
        return self.client.post(reverse('curso_inscribir', args=[curso.pk]), {'alumnos': [a.pk for a in alumnos]})

    def test_el_buscador_ofrece_solo_alumnos_activos_no_inscritos(self):
        crear_usuario('eva@ejemplo.cl', '44444444-4', 'Eva', Rol.ALUMNO, is_active=False)
        Inscripcion.objects.create(alumno=self.ana, curso=self.curso)

        opciones = self.client.get(reverse('curso_detalle', args=[self.curso.pk])).context[
            'form_inscripcion'].fields['alumnos'].queryset

        self.assertEqual(list(opciones), [self.luis])

    def test_inscribir_varios_alumnos_a_la_vez(self):
        respuesta = self.inscribir(self.ana, self.luis)

        self.assertRedirects(respuesta, reverse('curso_detalle', args=[self.curso.pk]), fetch_redirect_response=False)
        self.assertEqual(set(self.curso.inscripciones.filter(activa=True).values_list('alumno', flat=True)),
                         {self.ana.pk, self.luis.pk})
        detalle = self.client.get(reverse('curso_detalle', args=[self.curso.pk]))
        self.assertContains(detalle, 'Se inscribieron 2 alumnos')
        self.assertEqual(len(detalle.context['inscripciones']), 2)

    def test_la_inscripcion_se_refleja_en_el_perfil_del_alumno(self):
        self.inscribir(self.ana)

        respuesta = self.client.get(reverse('gestion_alumnos'))

        self.assertContains(respuesta, 'Capacitación inscrita')
        self.assertContains(respuesta, f'href="{reverse("curso_detalle", args=[self.curso.pk])}"')

    def test_rechaza_vacio_inscritos_profesores_e_inactivos(self):
        Inscripcion.objects.create(alumno=self.ana, curso=self.curso)
        inactivo = crear_usuario('eva@ejemplo.cl', '44444444-4', 'Eva', Rol.ALUMNO, is_active=False)

        for alumnos, error in [((), 'Seleccione al menos un alumno'), ((self.ana,), 'ya no está disponible'),
                               ((self.profesor,), 'ya no está disponible'), ((inactivo,), 'ya no está disponible')]:
            with self.subTest(alumnos=alumnos):
                self.assertContains(self.inscribir(*alumnos), error)
        self.assertEqual(Inscripcion.objects.count(), 1)

    def test_retirar_conserva_la_inscripcion_y_se_puede_volver_a_inscribir(self):
        self.inscribir(self.ana)
        inscripcion = Inscripcion.objects.get(alumno=self.ana, curso=self.curso)

        self.client.post(reverse('curso_retirar', args=[self.curso.pk, inscripcion.pk]))
        inscripcion.refresh_from_db()
        self.assertFalse(inscripcion.activa)
        self.assertNotContains(self.client.get(reverse('gestion_alumnos')),
                               f'href="{reverse("curso_detalle", args=[self.curso.pk])}"')

        self.inscribir(self.ana)
        inscripcion.refresh_from_db()
        self.assertTrue(inscripcion.activa)
        self.assertEqual(Inscripcion.objects.filter(alumno=self.ana).count(), 1)

    def test_un_curso_eliminado_no_recibe_inscripciones_ni_aparece_en_el_perfil(self):
        Inscripcion.objects.create(alumno=self.ana, curso=self.curso)
        self.curso.eliminar()

        self.assertEqual(self.inscribir(self.luis).status_code, 404)
        self.assertFalse(Inscripcion.objects.filter(alumno=self.luis).exists())
        self.assertNotContains(self.client.get(reverse('gestion_alumnos')),
                               f'href="{reverse("curso_detalle", args=[self.curso.pk])}"')

    def test_inscribir_y_retirar_piden_doble_verificacion(self):
        Inscripcion.objects.create(alumno=self.ana, curso=self.curso)

        detalle = self.client.get(reverse('curso_detalle', args=[self.curso.pk])).content.decode()

        self.assertRegex(detalle, r'id="formInscripcion"[^>]*data-confirmar=')
        self.assertRegex(detalle, r'action="[^"]*/retirar/"[^>]*data-confirmar=')

    def test_solo_el_administrador_inscribe(self):
        self.client.force_login(self.profesor)

        self.assertEqual(self.inscribir(self.ana).status_code, 302)
        self.assertFalse(Inscripcion.objects.exists())


class MenuProfesorTests(TestCase):
    """RF-09: menú del profesor y la lista de sus cursos."""

    def setUp(self):
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.client.force_login(self.profesor)

    def test_el_menu_tiene_los_cuatro_accesos_del_requerimiento(self):
        respuesta = self.client.get(reverse('profesor_inicio'))

        for titulo in ['Cursos', 'Gestión de Evaluaciones', 'Horario', 'Asistencia por clase']:
            with self.subTest(seccion=titulo):
                self.assertContains(respuesta, f'<h5 class="card-title mt-3">{titulo}</h5>', html=True)
        self.assertContains(respuesta, f'href="{reverse("profesor_cursos")}"')

    def test_al_ingresar_el_profesor_llega_a_su_menu(self):
        self.client.logout()

        respuesta = self.client.post(reverse('login'), {'email': 'pedro@ejemplo.cl', 'password': 'clave-segura-123'},
                                     follow=True)

        self.assertRedirects(respuesta, reverse('profesor_inicio'))
        self.assertTemplateUsed(respuesta, 'profesor/menu.html')

    def test_mis_cursos_muestra_solo_sus_cursos_activos_con_sus_alumnos(self):
        otro = crear_usuario('marta@ejemplo.cl', '22222222-2', 'Marta', Rol.PROFESOR)
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        propio = Curso.objects.create(nombre='Liderazgo', profesor=self.profesor)
        Curso.objects.create(nombre='Curso eliminado', profesor=self.profesor).eliminar()
        Curso.objects.create(nombre='Curso ajeno', profesor=otro)
        Inscripcion.objects.create(alumno=alumno, curso=propio)

        respuesta = self.client.get(reverse('profesor_cursos'))

        self.assertEqual([(c.nombre, c.inscritos) for c in respuesta.context['cursos']], [('Liderazgo', 1)])
        self.assertContains(respuesta, '1 alumno')

    def test_sin_cursos_muestra_un_aviso(self):
        self.assertContains(self.client.get(reverse('profesor_cursos')), 'Aún no tienes cursos a cargo')

    def test_otros_roles_no_entran_a_las_paginas_del_profesor(self):
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')

        for usuario in [alumno, admin]:
            self.client.force_login(usuario)
            for nombre_url in ['profesor_inicio', 'profesor_cursos']:
                with self.subTest(rol=usuario.rol, pagina=nombre_url):
                    self.assertEqual(self.client.get(reverse(nombre_url)).status_code, 302)


class AsignaturasDelProfesorTests(TestCase):
    """RF-05: el perfil del profesor muestra las asignaturas que imparte."""

    def test_el_perfil_lista_solo_sus_cursos_activos(self):
        admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        Curso.objects.create(nombre='Liderazgo', profesor=profesor)
        Curso.objects.create(nombre='Curso antiguo', profesor=profesor).eliminar()
        self.client.force_login(admin)

        respuesta = self.client.get(reverse('gestion_profesores'))

        self.assertContains(respuesta, 'Asignaturas que imparte')
        self.assertContains(respuesta, 'Liderazgo')
        self.assertNotContains(respuesta, 'Curso antiguo')
