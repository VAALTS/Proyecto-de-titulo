import os
import shutil
import tempfile
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.models import Rol, Usuario

from .models import Clase, Curso, Inscripcion, Material, Modulo


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


class CursoDelProfesorTests(TestCase):
    """RF-10: página del curso con sus módulos, clases y lista de alumnos."""

    CLASE = {'titulo': 'Introducción', 'fecha': '2026-11-02', 'hora_inicio': '09:00', 'hora_fin': '10:30'}

    def setUp(self):
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.curso = Curso.objects.create(nombre='Liderazgo', profesor=self.profesor)
        self.client.force_login(self.profesor)

    def test_mis_cursos_enlaza_a_la_pagina_del_curso(self):
        self.assertContains(self.client.get(reverse('profesor_cursos')),
                            f'href="{reverse("profesor_curso", args=[self.curso.pk])}"')

    def test_la_pagina_muestra_modulos_clases_y_alumnos(self):
        alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        Inscripcion.objects.create(alumno=alumno, curso=self.curso)
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')
        Clase.objects.create(modulo=modulo, titulo='Introducción', fecha='2026-11-02',
                             hora_inicio='09:00', hora_fin='10:30')

        respuesta = self.client.get(reverse('profesor_curso', args=[self.curso.pk]))

        for texto in ['Fundamentos', 'Introducción', '09:00 a 10:30', 'Ana Pérez', '33333333-3']:
            with self.subTest(texto=texto):
                self.assertContains(respuesta, texto)

    def test_los_modulos_nuevos_quedan_al_final_y_se_pueden_reordenar(self):
        for nombre in ['Uno', 'Dos', 'Tres']:
            self.client.post(reverse('modulo_crear', args=[self.curso.pk]), {'nombre': nombre})
        self.assertEqual(list(self.curso.modulos.values_list('nombre', flat=True)), ['Uno', 'Dos', 'Tres'])

        tres = Modulo.objects.get(nombre='Tres')
        self.client.post(reverse('modulo_mover', args=[tres.pk, 'subir']))
        self.client.post(reverse('modulo_mover', args=[Modulo.objects.get(nombre='Uno').pk, 'subir']))

        self.assertEqual(list(self.curso.modulos.values_list('nombre', flat=True)), ['Uno', 'Tres', 'Dos'])
        self.assertEqual(self.client.post(reverse('modulo_mover', args=[tres.pk, 'otra'])).status_code, 404)

    def test_editar_un_modulo(self):
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')

        respuesta = self.client.post(reverse('modulo_editar', args=[modulo.pk]), {'nombre': 'Bases'})

        self.assertRedirects(respuesta, f"{reverse('profesor_curso', args=[self.curso.pk])}#contenido",
                             fetch_redirect_response=False)
        modulo.refresh_from_db()
        self.assertEqual(modulo.nombre, 'Bases')

    def test_crear_y_editar_una_clase(self):
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')

        self.client.post(reverse('clase_crear', args=[modulo.pk]), self.CLASE)
        clase = modulo.clases.get()
        self.client.post(reverse('clase_editar', args=[clase.pk]), {**self.CLASE, 'hora_fin': '11:00'})

        clase.refresh_from_db()
        self.assertEqual((clase.titulo, str(clase.fecha), clase.hora_fin.strftime('%H:%M')),
                         ('Introducción', '2026-11-02', '11:00'))

    def test_una_clase_debe_terminar_despues_de_empezar(self):
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')

        respuesta = self.client.post(reverse('clase_crear', args=[modulo.pk]), {**self.CLASE, 'hora_fin': '08:00'})

        self.assertContains(respuesta, 'La hora de término debe ser posterior a la de inicio.')
        self.assertContains(respuesta, '"modalClase"')
        self.assertContains(respuesta, f'action="{reverse("clase_crear", args=[modulo.pk])}"')
        self.assertFalse(modulo.clases.exists())

    def test_un_modulo_con_clases_no_se_elimina_pero_uno_vacio_si(self):
        con_clases = Modulo.objects.create(curso=self.curso, nombre='Con clases')
        Clase.objects.create(modulo=con_clases, **self.CLASE)
        vacio = Modulo.objects.create(curso=self.curso, nombre='Vacío')

        self.client.post(reverse('modulo_eliminar', args=[con_clases.pk]))
        self.client.post(reverse('modulo_eliminar', args=[vacio.pk]))

        self.assertEqual(list(self.curso.modulos.values_list('nombre', flat=True)), ['Con clases'])
        self.client.post(reverse('clase_eliminar', args=[con_clases.clases.get().pk]))
        self.assertFalse(con_clases.clases.exists())

    def test_los_cambios_piden_doble_verificacion(self):
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')
        Clase.objects.create(modulo=modulo, **self.CLASE)

        pagina = self.client.get(reverse('profesor_curso', args=[self.curso.pk])).content.decode()

        for formulario in ['formModulo', 'formClase']:
            with self.subTest(formulario=formulario):
                self.assertRegex(pagina, rf'id="{formulario}"[^>]*data-confirmar=')
        for accion in ['modulos/\\d+/eliminar/', 'clases/\\d+/eliminar/']:
            with self.subTest(accion=accion):
                self.assertRegex(pagina, rf'action="[^"]*{accion}"[^>]*data-confirmar=')

    def test_no_se_accede_a_cursos_ajenos_ni_eliminados(self):
        otro = crear_usuario('marta@ejemplo.cl', '22222222-2', 'Marta', Rol.PROFESOR)
        ajeno = Curso.objects.create(nombre='Ajeno', profesor=otro)
        modulo_ajeno = Modulo.objects.create(curso=ajeno, nombre='Ajeno')
        eliminado = Curso.objects.create(nombre='Eliminado', profesor=self.profesor)
        eliminado.eliminar()

        for nombre_url, pk in [('profesor_curso', ajeno.pk), ('profesor_curso', eliminado.pk)]:
            with self.subTest(curso=pk):
                self.assertEqual(self.client.get(reverse(nombre_url, args=[pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('modulo_crear', args=[ajeno.pk]), {'nombre': 'X'}).status_code, 404)
        self.assertEqual(self.client.post(reverse('modulo_editar', args=[modulo_ajeno.pk]),
                                          {'nombre': 'X'}).status_code, 404)
        self.assertEqual(self.client.post(reverse('clase_crear', args=[modulo_ajeno.pk]), self.CLASE).status_code, 404)
        modulo_ajeno.refresh_from_db()
        self.assertEqual(modulo_ajeno.nombre, 'Ajeno')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='adapt_media_'))
class MaterialTests(TestCase):
    """RF-10: subir, editar, ocultar y descargar el material de una clase."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.profesor = crear_usuario('pedro@ejemplo.cl', '11111111-1', 'Pedro', Rol.PROFESOR)
        self.alumno = crear_usuario('ana@ejemplo.cl', '33333333-3', 'Ana', Rol.ALUMNO)
        self.curso = Curso.objects.create(nombre='Liderazgo', profesor=self.profesor)
        Inscripcion.objects.create(alumno=self.alumno, curso=self.curso)
        modulo = Modulo.objects.create(curso=self.curso, nombre='Fundamentos')
        self.clase = Clase.objects.create(modulo=modulo, titulo='Introducción', fecha='2026-11-02',
                                          hora_inicio='09:00', hora_fin='10:30')
        self.client.force_login(self.profesor)

    def subir(self, titulo='Guía 1', nombre='guia.pdf', contenido=b'%PDF-1.4 prueba', url=None, **datos):
        url = url or reverse('material_crear', args=[self.clase.pk])
        archivo = SimpleUploadedFile(nombre, contenido, content_type='application/pdf')
        return self.client.post(url, {'tipo': 'archivo', 'titulo': titulo, 'archivo': archivo, **datos})

    def test_subir_un_archivo_y_descargarlo_con_su_nombre_original(self):
        self.subir()

        material = self.clase.materiales.get()
        self.assertEqual((material.tipo, material.subido_por, material.nombre_archivo),
                         ('archivo', self.profesor, 'guia.pdf'))
        respuesta = self.client.get(reverse('material_descargar', args=[material.pk]))
        self.assertEqual(b''.join(respuesta.streaming_content), b'%PDF-1.4 prueba')
        self.assertIn('attachment; filename="guia.pdf"', respuesta['Content-Disposition'])

    def test_agregar_un_enlace_y_una_carpeta_con_contenido(self):
        self.client.post(reverse('material_crear', args=[self.clase.pk]),
                         {'tipo': 'enlace', 'titulo': 'Video', 'url': 'https://www.youtube.com/watch?v=abc'})
        self.client.post(reverse('material_crear', args=[self.clase.pk]), {'tipo': 'carpeta', 'titulo': 'Lecturas'})
        carpeta = self.clase.materiales.get(tipo='carpeta')
        self.subir(titulo='Lectura 1', url=reverse('material_crear_en_carpeta', args=[carpeta.pk]))

        self.assertEqual(carpeta.contenido.get().titulo, 'Lectura 1')
        pagina = self.client.get(reverse('profesor_curso', args=[self.curso.pk]))
        self.assertContains(pagina, 'href="https://www.youtube.com/watch?v=abc" target="_blank"')
        self.assertEqual([m.titulo for m in pagina.context['modulos'][0].clases.all()[0].raiz], ['Lecturas', 'Video'])

    def test_valida_lo_que_pide_cada_tipo_y_las_carpetas_de_un_nivel(self):
        crear = reverse('material_crear', args=[self.clase.pk])
        self.assertContains(self.client.post(crear, {'tipo': 'archivo', 'titulo': 'X'}), 'Seleccione el archivo')
        self.assertContains(self.client.post(crear, {'tipo': 'enlace', 'titulo': 'X'}), 'Ingrese la dirección')
        self.assertContains(self.subir(nombre='virus.exe'), 'extensión')

        carpeta = Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='C', tipo='carpeta')
        respuesta = self.client.post(reverse('material_crear_en_carpeta', args=[carpeta.pk]),
                                     {'tipo': 'carpeta', 'titulo': 'Subcarpeta'})
        self.assertContains(respuesta, '"modalMaterial"')
        self.assertEqual(self.clase.materiales.count(), 1)

    def test_rechaza_archivos_de_mas_de_20_mb(self):
        with mock.patch('cursos.forms.TAMANO_MAXIMO_MB', 0.001):
            self.assertContains(self.subir(contenido=b'x' * 2048), 'pesa más de')
        self.assertFalse(self.clase.materiales.exists())

    def test_reemplazar_el_archivo_borra_el_anterior_y_eliminar_borra_el_actual(self):
        self.subir()
        material = self.clase.materiales.get()
        ruta_anterior = material.archivo.path

        self.client.post(reverse('material_editar', args=[material.pk]),
                         {'titulo': 'Guía 1 corregida', 'archivo': SimpleUploadedFile('guia_v2.pdf', b'v2')})
        material.refresh_from_db()
        self.assertEqual((material.titulo, material.nombre_archivo, material.tipo),
                         ('Guía 1 corregida', 'guia_v2.pdf', 'archivo'))
        self.assertFalse(os.path.exists(ruta_anterior))

        ruta_actual = material.archivo.path
        self.client.post(reverse('material_eliminar', args=[material.pk]))
        self.assertFalse(Material.objects.exists())
        self.assertFalse(os.path.exists(ruta_actual))

    def test_editar_sin_subir_otro_archivo_conserva_el_actual(self):
        self.subir()
        material = self.clase.materiales.get()

        self.client.post(reverse('material_editar', args=[material.pk]), {'titulo': 'Nuevo título'})

        material.refresh_from_db()
        self.assertEqual((material.titulo, material.nombre_archivo), ('Nuevo título', 'guia.pdf'))

    def test_una_carpeta_con_contenido_y_una_clase_con_material_no_se_eliminan(self):
        carpeta = Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='C', tipo='carpeta')
        Material.objects.create(clase=self.clase, carpeta=carpeta, subido_por=self.profesor, titulo='E',
                                tipo='enlace', url='https://ejemplo.cl')

        self.client.post(reverse('material_eliminar', args=[carpeta.pk]))
        self.client.post(reverse('clase_eliminar', args=[self.clase.pk]))

        self.assertEqual(Material.objects.count(), 2)
        self.assertTrue(Clase.objects.filter(pk=self.clase.pk).exists())

    def test_el_alumno_inscrito_descarga_solo_el_material_visible(self):
        self.subir()
        material = self.clase.materiales.get()
        descargar = reverse('material_descargar', args=[material.pk])
        self.client.force_login(self.alumno)
        self.assertEqual(self.client.get(descargar).status_code, 200)

        self.client.force_login(self.profesor)
        self.client.post(reverse('material_visibilidad', args=[material.pk]))
        self.client.force_login(self.alumno)
        self.assertEqual(self.client.get(descargar).status_code, 404)

    def test_un_archivo_dentro_de_una_carpeta_oculta_tampoco_se_descarga(self):
        carpeta = Material.objects.create(clase=self.clase, subido_por=self.profesor, titulo='C', tipo='carpeta',
                                          visible=False)
        self.subir(url=reverse('material_crear_en_carpeta', args=[carpeta.pk]))
        self.client.force_login(self.alumno)

        self.assertEqual(self.client.get(reverse('material_descargar', args=[carpeta.contenido.get().pk])).status_code,
                         404)

    def test_quien_no_es_del_curso_no_descarga_ni_modifica(self):
        self.subir()
        material = self.clase.materiales.get()
        otro_alumno = crear_usuario('luis@ejemplo.cl', '22222222-2', 'Luis', Rol.ALUMNO)
        otro_profesor = crear_usuario('marta@ejemplo.cl', '44444444-4', 'Marta', Rol.PROFESOR)

        for usuario in [otro_alumno, otro_profesor]:
            self.client.force_login(usuario)
            with self.subTest(rol=usuario.rol):
                self.assertEqual(self.client.get(reverse('material_descargar', args=[material.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('material_eliminar', args=[material.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('material_descargar', args=[material.pk])).status_code, 302)
        self.assertTrue(Material.objects.exists())


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
