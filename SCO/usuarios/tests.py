import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import authenticate
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import MENSAJE_CREDENCIALES
from .models import Rol, Usuario
from .rut import normalizar_rut


class UsuarioTests(TestCase):

    def crear_alumno(self, email='ana@ejemplo.cl', **campos):
        campos.setdefault('rut', '11111111-1')
        campos.setdefault('primer_nombre', 'Ana')
        campos.setdefault('apellido_paterno', 'Pérez')
        return Usuario.objects.create_user(email, 'clave-segura-123', **campos)

    def test_create_user_guarda_el_correo_en_minusculas_y_rol_alumno(self):
        usuario = self.crear_alumno('Ana.Perez@Ejemplo.CL')

        self.assertEqual(usuario.email, 'ana.perez@ejemplo.cl')
        self.assertEqual(usuario.rol, Rol.ALUMNO)

    def test_la_contrasena_se_guarda_cifrada(self):
        usuario = self.crear_alumno()

        self.assertNotEqual(usuario.password, 'clave-segura-123')
        self.assertTrue(usuario.check_password('clave-segura-123'))

    def test_create_superuser_queda_con_rol_administrador_y_no_exige_rut(self):
        admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')

        self.assertEqual(admin.rol, Rol.ADMINISTRADOR)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_se_autentica_con_el_correo_sin_distinguir_mayusculas(self):
        usuario = self.crear_alumno('ana@ejemplo.cl')

        self.assertEqual(authenticate(username='ANA@Ejemplo.cl', password='clave-segura-123'), usuario)
        self.assertIsNone(authenticate(username='ana@ejemplo.cl', password='otra-clave'))

    def test_alumno_sin_rut_es_rechazado_por_la_base_de_datos(self):
        with self.assertRaises(IntegrityError):
            self.crear_alumno(rut=None)


class LoginTests(TestCase):
    """RF-01: inicio de sesión con correo, redirección por rol y bloqueo tras 3 intentos fallidos."""

    CLAVE = 'clave-segura-123'

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', self.CLAVE, primer_nombre='Admin')
        self.profesor = Usuario.objects.create_user('profe@ejemplo.cl', self.CLAVE, rut='22222222-2',
                                                    primer_nombre='Pedro', apellido_paterno='Soto',
                                                    rol=Rol.PROFESOR)
        self.alumno = Usuario.objects.create_user('ana@ejemplo.cl', self.CLAVE, rut='11111111-1',
                                                  primer_nombre='Ana', apellido_paterno='Pérez')

    def ingresar(self, email, clave):
        return self.client.post(reverse('login'), {'email': email, 'password': clave})

    def test_cada_rol_es_redirigido_a_su_inicio(self):
        for usuario, destino in [(self.admin, 'admin_menu'), (self.profesor, 'profesor_inicio'),
                                 (self.alumno, 'alumno_inicio')]:
            with self.subTest(rol=usuario.rol):
                respuesta = self.client.post(reverse('login'), {'email': usuario.email, 'password': self.CLAVE},
                                             follow=True)
                self.assertRedirects(respuesta, reverse(destino))
                self.client.logout()

    def test_credenciales_incorrectas_muestran_el_mensaje_del_requerimiento(self):
        respuesta = self.ingresar('ana@ejemplo.cl', 'mala')

        self.assertContains(respuesta, MENSAJE_CREDENCIALES)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_un_correo_inexistente_muestra_el_mismo_mensaje(self):
        self.assertContains(self.ingresar('nadie@ejemplo.cl', 'mala'), MENSAJE_CREDENCIALES)

    def test_tres_intentos_fallidos_bloquean_la_cuenta(self):
        self.ingresar('ana@ejemplo.cl', 'mala')
        self.ingresar('ana@ejemplo.cl', 'mala')
        respuesta = self.ingresar('ana@ejemplo.cl', 'mala')

        self.assertContains(respuesta, 'bloqueada temporalmente')
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.esta_bloqueado())

    def test_la_cuenta_bloqueada_rechaza_incluso_la_clave_correcta(self):
        self.alumno.bloqueado_hasta = timezone.now() + timedelta(minutes=5)
        self.alumno.save()

        respuesta = self.ingresar('ana@ejemplo.cl', self.CLAVE)

        self.assertContains(respuesta, 'bloqueada temporalmente')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_pasado_el_bloqueo_se_puede_ingresar(self):
        self.alumno.bloqueado_hasta = timezone.now() - timedelta(seconds=1)
        self.alumno.save()

        respuesta = self.ingresar('ana@ejemplo.cl', self.CLAVE)

        self.assertRedirects(respuesta, reverse('home'), fetch_redirect_response=False)
        self.alumno.refresh_from_db()
        self.assertIsNone(self.alumno.bloqueado_hasta)

    def test_un_ingreso_correcto_reinicia_los_intentos_fallidos(self):
        self.ingresar('ana@ejemplo.cl', 'mala')
        self.ingresar('ana@ejemplo.cl', 'mala')
        self.ingresar('ana@ejemplo.cl', self.CLAVE)

        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.intentos_fallidos, 0)

    def test_un_rol_no_entra_a_la_pagina_de_otro(self):
        self.client.force_login(self.alumno)

        self.assertRedirects(self.client.get(reverse('admin_menu')), f"{reverse('login')}?next={reverse('admin_menu')}",
                             fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('profesor_inicio')).status_code, 302)


class LogoutTests(TestCase):
    """RF-02: cierre de sesión desde un menú desplegable presente en todas las páginas."""

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        self.profesor = Usuario.objects.create_user('profe@ejemplo.cl', 'clave-segura-123', rut='22222222-2',
                                                    primer_nombre='Pedro', apellido_paterno='Soto',
                                                    rol=Rol.PROFESOR)
        self.alumno = Usuario.objects.create_user('ana@ejemplo.cl', 'clave-segura-123', rut='11111111-1',
                                                  primer_nombre='Ana', apellido_paterno='Pérez')

    def test_todas_las_paginas_tienen_el_menu_con_cierre_de_sesion(self):
        paginas = [(self.admin, 'admin_menu'), (self.admin, 'gestion_alumnos'), (self.admin, 'gestion_profesores'),
                   (self.admin, 'gestion_cursos'), (self.profesor, 'profesor_inicio'), (self.alumno, 'alumno_inicio')]
        for usuario, pagina in paginas:
            with self.subTest(pagina=pagina):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse(pagina))
                self.assertContains(respuesta, 'data-bs-toggle="dropdown"')
                self.assertContains(respuesta, f'action="{reverse("logout")}"')

    def test_cerrar_sesion_termina_la_sesion_y_vuelve_al_login(self):
        self.client.force_login(self.alumno)

        respuesta = self.client.post(reverse('logout'))

        self.assertRedirects(respuesta, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(reverse('alumno_inicio')).status_code, 302)

    def test_cerrar_sesion_solo_acepta_post(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_las_paginas_privadas_no_quedan_en_cache(self):
        self.client.force_login(self.alumno)

        respuesta = self.client.get(reverse('alumno_inicio'))

        self.assertIn('no-store', respuesta['Cache-Control'])


class MenuAdministradorTests(TestCase):
    """RF-03: menú del administrador con accesos a las tres gestiones."""

    GESTIONES = [('gestion_alumnos', 'Gestión de alumnos'), ('gestion_profesores', 'Gestión de profesores'),
                 ('gestion_cursos', 'Gestión de cursos')]

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        self.client.force_login(self.admin)

    def test_el_menu_tiene_un_boton_por_cada_gestion(self):
        respuesta = self.client.get(reverse('admin_menu'))

        for nombre_url, titulo in self.GESTIONES:
            with self.subTest(gestion=titulo):
                self.assertContains(respuesta, titulo)
                self.assertContains(respuesta, f'href="{reverse(nombre_url)}"')

    def test_cada_boton_lleva_a_su_ventana_y_esta_permite_volver(self):
        for nombre_url, titulo in self.GESTIONES:
            with self.subTest(gestion=titulo):
                respuesta = self.client.get(reverse(nombre_url))
                self.assertContains(respuesta, f'<title>{titulo}</title>', html=True)
                self.assertContains(respuesta, f'href="{reverse("admin_menu")}"')

    def test_profesores_y_alumnos_no_entran_a_las_gestiones(self):
        profesor = Usuario.objects.create_user('profe@ejemplo.cl', 'clave-segura-123', rut='22222222-2',
                                               primer_nombre='Pedro', apellido_paterno='Soto', rol=Rol.PROFESOR)
        self.client.force_login(profesor)

        for nombre_url in ['admin_menu'] + [nombre for nombre, _ in self.GESTIONES]:
            with self.subTest(pagina=nombre_url):
                self.assertEqual(self.client.get(reverse(nombre_url)).status_code, 302)


class RutTests(TestCase):

    def test_normaliza_el_formato(self):
        for escrito in ['12.345.678-5', '12345678-5', '123456785', ' 12.345.678-5 ']:
            with self.subTest(rut=escrito):
                self.assertEqual(normalizar_rut(escrito), '12345678-5')

    def test_acepta_digito_k_y_cero(self):
        self.assertEqual(normalizar_rut('10.000.013-k'), '10000013-K')
        self.assertEqual(normalizar_rut('10.000.004-0'), '10000004-0')

    def test_rechaza_digito_incorrecto_y_formatos_invalidos(self):
        for invalido in ['12.345.678-9', 'abc', '123-4', '']:
            with self.subTest(rut=invalido):
                with self.assertRaises(ValidationError):
                    normalizar_rut(invalido)


class GestionAlumnosTests(TestCase):
    """RF-04: registro con contraseña temporal, listado con búsqueda y edición de alumnos."""

    DATOS = {'rut': '12.345.678-5', 'primer_nombre': 'Ana', 'segundo_nombre': 'María',
             'apellido_paterno': 'Pérez', 'apellido_materno': 'Soto', 'email': 'Ana.Perez@Ejemplo.cl'}

    def setUp(self):
        self.admin = Usuario.objects.create_superuser('admin@ejemplo.cl', 'clave-segura-123', primer_nombre='Admin')
        self.client.force_login(self.admin)

    def crear_alumno(self, email, rut, nombre, apellido):
        return Usuario.objects.create_user(email, 'clave-segura-123', rut=rut, primer_nombre=nombre,
                                           apellido_paterno=apellido)

    def test_registrar_crea_al_alumno_y_le_envia_una_contrasena_temporal(self):
        respuesta = self.client.post(reverse('alumno_registrar'), self.DATOS)

        self.assertRedirects(respuesta, reverse('gestion_alumnos'), fetch_redirect_response=False)
        alumno = Usuario.objects.get(email='ana.perez@ejemplo.cl')
        self.assertEqual((alumno.rol, alumno.rut, alumno.apellido_materno), (Rol.ALUMNO, '12345678-5', 'Soto'))
        self.assertTrue(alumno.debe_cambiar_contrasena)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ana.perez@ejemplo.cl'])
        clave = re.search(r'Contraseña temporal: (\S+)', mail.outbox[0].body).group(1)
        self.assertTrue(alumno.check_password(clave))

    def test_registrar_con_rut_invalido_o_repetido_muestra_el_error_y_no_crea_nada(self):
        self.crear_alumno('otro@ejemplo.cl', '12345678-5', 'Otro', 'Alumno')

        for rut, error in [('12.345.678-9', 'dígito verificador'), ('12345678-5', 'Ya existe una cuenta con este RUT')]:
            with self.subTest(rut=rut):
                respuesta = self.client.post(reverse('alumno_registrar'), {**self.DATOS, 'rut': rut})
                self.assertContains(respuesta, error)
                self.assertContains(respuesta, '"modalRegistro"')
        self.assertFalse(Usuario.objects.filter(email='ana.perez@ejemplo.cl').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_si_falla_el_correo_no_se_crea_la_cuenta(self):
        with mock.patch('usuarios.cuentas.send_mail', side_effect=OSError('sin conexión')):
            respuesta = self.client.post(reverse('alumno_registrar'), self.DATOS)

        self.assertContains(respuesta, 'No se pudo enviar el correo')
        self.assertFalse(Usuario.objects.filter(email='ana.perez@ejemplo.cl').exists())

    def test_la_lista_muestra_solo_alumnos_y_la_busqueda_filtra(self):
        self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')
        self.crear_alumno('luis@ejemplo.cl', '22222222-2', 'Luis', 'Rojas')
        Usuario.objects.create_user('profe@ejemplo.cl', 'clave-segura-123', rut='33333333-3', primer_nombre='Pedro',
                                    apellido_paterno='Soto', rol=Rol.PROFESOR)

        todos = self.client.get(reverse('gestion_alumnos'))
        self.assertContains(todos, 'ana@ejemplo.cl')
        self.assertContains(todos, 'luis@ejemplo.cl')
        self.assertNotContains(todos, 'profe@ejemplo.cl')

        for busqueda in ['ana pérez', 'ANA@', '11.111.111']:
            with self.subTest(busqueda=busqueda):
                respuesta = self.client.get(reverse('gestion_alumnos'), {'q': busqueda})
                self.assertContains(respuesta, 'ana@ejemplo.cl')
                self.assertNotContains(respuesta, 'luis@ejemplo.cl')

    def test_editar_guarda_los_cambios_y_conserva_la_busqueda(self):
        alumno = self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')

        respuesta = self.client.post(reverse('alumno_editar', args=[alumno.pk]), {**self.DATOS, 'q': 'ana'})

        self.assertRedirects(respuesta, f"{reverse('gestion_alumnos')}?q=ana", fetch_redirect_response=False)
        alumno.refresh_from_db()
        self.assertEqual((alumno.rut, alumno.segundo_nombre, alumno.email),
                         ('12345678-5', 'María', 'ana.perez@ejemplo.cl'))
        self.assertTrue(alumno.check_password('clave-segura-123'))

    def test_editar_con_un_correo_ya_usado_no_guarda(self):
        alumno = self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')
        self.crear_alumno('luis@ejemplo.cl', '22222222-2', 'Luis', 'Rojas')

        respuesta = self.client.post(reverse('alumno_editar', args=[alumno.pk]),
                                     {**self.DATOS, 'email': 'LUIS@ejemplo.cl'})

        self.assertContains(respuesta, 'Ya existe una cuenta con este correo')
        self.assertContains(respuesta, '"modalEdicion"')
        alumno.refresh_from_db()
        self.assertEqual(alumno.email, 'ana@ejemplo.cl')

    def test_los_formularios_piden_doble_verificacion(self):
        self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')
        respuesta = self.client.get(reverse('gestion_alumnos')).content.decode()

        for formulario in ['formRegistro', 'formEdicion', 'formReenviar']:
            with self.subTest(formulario=formulario):
                self.assertRegex(respuesta, rf'id="{formulario}"[^>]*data-confirmar=')
        self.assertIn('id="modalConfirmacion"', respuesta)

    def test_desactivar_impide_ingresar_y_reactivar_lo_permite(self):
        alumno = self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')
        ingresar = {'email': 'ana@ejemplo.cl', 'password': 'clave-segura-123'}

        self.client.post(reverse('alumno_estado', args=[alumno.pk]))
        alumno.refresh_from_db()
        self.assertFalse(alumno.is_active)
        self.client.logout()
        self.assertContains(self.client.post(reverse('login'), ingresar), MENSAJE_CREDENCIALES)
        alumno.refresh_from_db()
        self.assertEqual(alumno.intentos_fallidos, 0)

        self.client.force_login(self.admin)
        self.client.post(reverse('alumno_estado', args=[alumno.pk]))
        self.client.logout()
        self.assertEqual(self.client.post(reverse('login'), ingresar).status_code, 302)

    def test_reenviar_cambia_la_contrasena_temporal(self):
        alumno = self.crear_alumno('ana@ejemplo.cl', '11111111-1', 'Ana', 'Pérez')

        self.client.post(reverse('alumno_reenviar_clave', args=[alumno.pk]))

        alumno.refresh_from_db()
        self.assertFalse(alumno.check_password('clave-segura-123'))
        self.assertTrue(alumno.debe_cambiar_contrasena)
        self.assertEqual(mail.outbox[0].to, ['ana@ejemplo.cl'])

    def test_las_acciones_no_aplican_a_profesores_ni_las_usa_otro_rol(self):
        profesor = Usuario.objects.create_user('profe@ejemplo.cl', 'clave-segura-123', rut='33333333-3',
                                               primer_nombre='Pedro', apellido_paterno='Soto', rol=Rol.PROFESOR)
        self.assertEqual(self.client.post(reverse('alumno_estado', args=[profesor.pk])).status_code, 404)

        self.client.force_login(profesor)
        self.assertEqual(self.client.post(reverse('alumno_registrar'), self.DATOS).status_code, 302)
        self.assertFalse(Usuario.objects.filter(email='ana.perez@ejemplo.cl').exists())


class ContrasenaTemporalTests(TestCase):
    """RF-04: quien tiene una contraseña temporal debe cambiarla antes de usar la plataforma."""

    def setUp(self):
        self.alumno = Usuario.objects.create_user('ana@ejemplo.cl', 'clave-temporal-1', rut='11111111-1',
                                                  primer_nombre='Ana', apellido_paterno='Pérez',
                                                  debe_cambiar_contrasena=True)
        self.client.force_login(self.alumno)

    def test_lo_lleva_al_perfil_hasta_que_la_cambie(self):
        self.assertRedirects(self.client.get(reverse('alumno_inicio')), reverse('perfil'))
        self.assertContains(self.client.get(reverse('perfil')), 'contraseña temporal')

        self.client.post(reverse('perfil'), {'old_password': 'clave-temporal-1', 'new_password1': 'Otra-Clave-Larga-456',
                                             'new_password2': 'Otra-Clave-Larga-456'})

        self.alumno.refresh_from_db()
        self.assertFalse(self.alumno.debe_cambiar_contrasena)
        self.assertEqual(self.client.get(reverse('alumno_inicio')).status_code, 200)

    def test_puede_cerrar_sesion_sin_cambiarla(self):
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))


class CambioContrasenaTests(TestCase):
    """RF-08: cambio de contraseña desde el perfil."""

    CLAVE = 'clave-segura-123'
    NUEVA = 'Otra-Clave-Larga-456'

    def setUp(self):
        self.alumno = Usuario.objects.create_user('ana@ejemplo.cl', self.CLAVE, rut='11111111-1',
                                                  primer_nombre='Ana', apellido_paterno='Pérez')
        self.client.force_login(self.alumno)

    def cambiar(self, actual, nueva, confirmacion=None):
        return self.client.post(reverse('perfil'), {'old_password': actual, 'new_password1': nueva,
                                                    'new_password2': confirmacion or nueva})

    def test_el_menu_enlaza_al_perfil_con_el_formulario(self):
        self.assertContains(self.client.get(reverse('alumno_inicio')), f'href="{reverse("perfil")}"')

        respuesta = self.client.get(reverse('perfil'))
        for etiqueta in ['Contraseña actual', 'Nueva contraseña', 'Confirmar nueva contraseña']:
            self.assertContains(respuesta, etiqueta)

    def test_el_perfil_exige_sesion(self):
        self.client.logout()

        self.assertEqual(self.client.get(reverse('perfil')).status_code, 302)

    def test_cambio_correcto_guarda_la_clave_y_mantiene_la_sesion(self):
        respuesta = self.cambiar(self.CLAVE, self.NUEVA)

        self.assertRedirects(respuesta, reverse('perfil'), fetch_redirect_response=False)
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.check_password(self.NUEVA))
        self.assertIn('_auth_user_id', self.client.session)
        self.assertContains(self.client.get(reverse('perfil')), 'se actualizó correctamente')

    def test_rechaza_una_contrasena_actual_incorrecta(self):
        self.assertContains(self.cambiar('equivocada', self.NUEVA), 'La contraseña actual no es correcta.')
        self.alumno.refresh_from_db()
        self.assertTrue(self.alumno.check_password(self.CLAVE))

    def test_rechaza_una_confirmacion_distinta(self):
        self.assertContains(self.cambiar(self.CLAVE, self.NUEVA, 'Otra-Distinta-789'),
                            'Las contraseñas nuevas no coinciden.')

    def test_la_nueva_debe_cumplir_las_politicas_de_seguridad(self):
        for debil in ['corta1', '12345678901', 'password123']:
            with self.subTest(clave=debil):
                self.assertEqual(self.cambiar(self.CLAVE, debil).status_code, 200)
                self.alumno.refresh_from_db()
                self.assertTrue(self.alumno.check_password(self.CLAVE))
