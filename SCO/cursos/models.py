import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from usuarios.models import Rol


class CursoQuerySet(models.QuerySet):

    def activos(self):
        return self.filter(activo=True)


class Curso(models.Model):
    """Capacitación impartida por Adapt Academy (RF-06). Curso, capacitación y asignatura son lo mismo."""

    profesor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cursos_a_cargo',
                                 limit_choices_to={'rol': Rol.PROFESOR}, verbose_name='profesor a cargo')
    nombre = models.CharField('nombre del curso', max_length=150)
    descripcion = models.TextField('descripción', blank=True)
    # Borrado lógico: el curso se oculta, pero sus inscripciones, notas y asistencias se conservan
    activo = models.BooleanField(default=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)

    objects = CursoQuerySet.as_manager()

    class Meta:
        verbose_name = 'curso'
        verbose_name_plural = 'cursos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def eliminar(self):
        self.activo = False
        self.eliminado_en = timezone.now()
        self.save(update_fields=['activo', 'eliminado_en'])

    def restaurar(self):
        self.activo = True
        self.eliminado_en = None
        self.save(update_fields=['activo', 'eliminado_en'])


class Modulo(models.Model):
    """Unidad en que el profesor organiza un curso (RF-10)."""

    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name='modulos')
    nombre = models.CharField('nombre del módulo', max_length=150)
    orden = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = 'módulo'
        verbose_name_plural = 'módulos'
        ordering = ['orden', 'pk']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Un módulo nuevo queda al final del curso
        if not self.pk:
            ultimo = self.curso.modulos.aggregate(models.Max('orden'))['orden__max'] or 0
            self.orden = ultimo + 1
        super().save(*args, **kwargs)


class Clase(models.Model):
    """Sesión con fecha de un módulo; en ella se publica material y se registra la asistencia."""

    modulo = models.ForeignKey(Modulo, on_delete=models.PROTECT, related_name='clases')
    titulo = models.CharField('título de la clase', max_length=150)
    fecha = models.DateField()
    hora_inicio = models.TimeField('hora de inicio')
    hora_fin = models.TimeField('hora de término')

    class Meta:
        verbose_name = 'clase'
        verbose_name_plural = 'clases'
        ordering = ['fecha', 'hora_inicio']
        constraints = [
            models.CheckConstraint(condition=models.Q(hora_fin__gt=models.F('hora_inicio')),
                                   name='clase_termina_despues_de_empezar'),
        ]

    def __str__(self):
        return f'{self.titulo} ({self.fecha:%d/%m/%Y})'


def ruta_material(material, nombre_archivo):
    # Una carpeta al azar por archivo evita choques de nombres y conserva el nombre original
    return f'material/curso_{material.clase.modulo.curso_id}/{uuid.uuid4().hex}/{nombre_archivo}'


class Material(models.Model):
    """Recurso que el profesor publica en una clase: un archivo, un enlace o una carpeta (RF-10)."""

    class Tipo(models.TextChoices):
        ARCHIVO = 'archivo', 'Archivo'
        ENLACE = 'enlace', 'Enlace'
        CARPETA = 'carpeta', 'Carpeta'

    clase = models.ForeignKey(Clase, on_delete=models.PROTECT, related_name='materiales')
    # Las carpetas tienen un solo nivel: dentro de una carpeta no puede haber otra
    carpeta = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='contenido',
                                limit_choices_to={'tipo': Tipo.CARPETA})
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='materiales_subidos')
    titulo = models.CharField('título', max_length=150)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    archivo = models.FileField(upload_to=ruta_material, max_length=255, null=True, blank=True)
    url = models.URLField('dirección del enlace', max_length=500, null=True, blank=True)
    # Falso si el profesor lo oculta a los alumnos
    visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'material'
        verbose_name_plural = 'materiales'
        ordering = ['titulo']

    def __str__(self):
        return self.titulo

    @property
    def nombre_archivo(self):
        return os.path.basename(self.archivo.name) if self.archivo else ''

    def visible_para_alumnos(self):
        return self.visible and (self.carpeta is None or self.carpeta.visible)


class Inscripcion(models.Model):
    """Relación entre un alumno y un curso; la lista de alumnos de un curso nace vacía y se llena en el RF-07."""

    alumno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='inscripciones',
                               limit_choices_to={'rol': Rol.ALUMNO})
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name='inscripciones')
    fecha_inscripcion = models.DateField(default=timezone.localdate)
    # Falso si el alumno se retira; la fila se conserva como historial
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'inscripción'
        verbose_name_plural = 'inscripciones'
        constraints = [
            models.UniqueConstraint(fields=['alumno', 'curso'], name='inscripcion_unica_por_curso'),
        ]

    def __str__(self):
        return f'{self.alumno} en {self.curso}'
