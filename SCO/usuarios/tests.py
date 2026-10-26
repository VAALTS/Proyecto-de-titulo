from datetime import timedelta

from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import MENSAJE_CREDENCIALES
from .models import Rol, Usuario


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
