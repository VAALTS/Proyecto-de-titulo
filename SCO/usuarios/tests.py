from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.test import TestCase

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
