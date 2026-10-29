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
