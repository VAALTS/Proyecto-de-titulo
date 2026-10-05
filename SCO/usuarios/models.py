from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Rol(models.TextChoices):
    ADMINISTRADOR = 'administrador', 'Administrador'
    PROFESOR = 'profesor', 'Profesor'
    ALUMNO = 'alumno', 'Alumno'


class UsuarioManager(BaseUserManager):

    def create_user(self, email, password=None, **campos):
        if not email:
            raise ValueError('El correo electrónico es obligatorio.')
        usuario = self.model(email=email.strip().lower(), **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, password=None, **campos):
        campos.update(rol=Rol.ADMINISTRADOR, is_staff=True, is_superuser=True)
        return self.create_user(email, password, **campos)

    def get_by_natural_key(self, email):
        # Los correos se guardan en minúsculas, así el login no distingue mayúsculas
        return self.get(email=email.strip().lower())


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Cuenta única para administradores, profesores y alumnos; se ingresa con el correo."""

    email = models.EmailField('correo electrónico', unique=True)
    # Los administradores pueden no tener RUT; para el resto es obligatorio (ver Meta)
    rut = models.CharField('RUT', max_length=12, unique=True, null=True, blank=True)
    primer_nombre = models.CharField('nombre', max_length=50)
    segundo_nombre = models.CharField(max_length=50, blank=True)
    apellido_paterno = models.CharField(max_length=50)
    apellido_materno = models.CharField(max_length=50, blank=True)
    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.ALUMNO)

    is_active = models.BooleanField('activo', default=True)
    # Solo controla el acceso al sitio /admin/ de Django; el rol dentro de la plataforma es `rol`
    is_staff = models.BooleanField('acceso al sitio de administración', default=False)
    fecha_registro = models.DateTimeField(default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['primer_nombre']

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rol=Rol.ADMINISTRADOR) | models.Q(rut__isnull=False),
                name='usuario_rut_obligatorio_salvo_admin',
            ),
        ]

    def __str__(self):
        return self.get_full_name() or self.email

    def clean(self):
        super().clean()
        self.email = self.email.lower()

    def get_full_name(self):
        partes = [self.primer_nombre, self.segundo_nombre, self.apellido_paterno, self.apellido_materno]
        return ' '.join(parte for parte in partes if parte)

    def get_short_name(self):
        return ' '.join(parte for parte in [self.primer_nombre, self.apellido_paterno] if parte)
