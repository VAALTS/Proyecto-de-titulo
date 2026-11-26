"""Avisos al teléfono cuando pasa algo en un curso, se haga desde la web o desde la aplicación móvil.

- Material o actividad nuevos (o que el profesor vuelve visibles): a los alumnos del curso.
- Encuesta nueva: a los alumnos del curso.
- Nota nueva o modificada: al alumno.
- Mensaje en el foro: a quienes participan del curso, menos a quien escribió.
- Asistencia registrada o corregida: al alumno.
- Entrega nueva o reemplazada: al profesor del curso.
- Clase nueva, cambiada o cancelada, y cambios en el horario semanal: a los alumnos del curso.
- Inscripción en un curso: al alumno y al profesor. Curso asignado: al profesor.
"""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from cursos.models import Asistencia, BloqueHorario, Clase, Curso, Encuesta, Inscripcion, Material, MensajeForo
from evaluaciones.models import Actividad, Calificacion, Entrega

from .push import notificar


def alumnos_del_curso(curso_id):
    return list(Inscripcion.objects.filter(curso_id=curso_id, activa=True).values_list('alumno_id', flat=True))


def guardar_estado_anterior(instancia, *campos):
    """Antes de guardar, recuerda cómo estaba, para saber si algo cambió."""
    instancia._antes = None
    if instancia.pk:
        instancia._antes = type(instancia).objects.filter(pk=instancia.pk).values(*campos).first()


@receiver(pre_save, sender=Material)
def material_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'visible')


@receiver(post_save, sender=Material)
def material_publicado(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    recien_visible = created or (antes is not None and not antes['visible'])
    if not recien_visible or instance.tipo == Material.Tipo.CARPETA:
        return
    if not instance.visible_para_alumnos():
        return
    curso = instance.clase.modulo.curso
    notificar(alumnos_del_curso(curso.pk), f'Nuevo material en {curso.nombre}', instance.titulo,
                   etiqueta=f'material-{instance.pk}')


@receiver(pre_save, sender=Actividad)
def actividad_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'visible')


@receiver(post_save, sender=Actividad)
def actividad_publicada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    recien_visible = created or (antes is not None and not antes['visible'])
    if not recien_visible or not instance.visible:
        return
    curso = instance.clase.modulo.curso
    limite = timezone.localtime(instance.fecha_limite)
    notificar(alumnos_del_curso(curso.pk), f'Nueva actividad en {curso.nombre}',
                   f'{instance.titulo} · entrega el {limite:%d/%m a las %H:%M}', etiqueta=f'actividad-{instance.pk}')


@receiver(post_save, sender=Encuesta)
def encuesta_publicada(sender, instance, created, **kwargs):
    if created and instance.visible:
        notificar(alumnos_del_curso(instance.curso_id), f'Nueva encuesta en {instance.curso.nombre}',
                       instance.pregunta, etiqueta=f'encuesta-{instance.pk}')


@receiver(pre_save, sender=Calificacion)
def nota_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'nota')


@receiver(post_save, sender=Calificacion)
def nota_registrada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    if not created and antes is not None and antes['nota'] == instance.nota:
        return
    actividad = instance.actividad
    nota = str(instance.nota).replace('.', ',')
    notificar([instance.inscripcion.alumno_id], f'Nueva nota en {actividad.curso.nombre}',
                   f'{actividad.titulo}: {nota}', etiqueta=f'nota-{instance.pk}')


@receiver(post_save, sender=MensajeForo)
def mensaje_en_el_foro(sender, instance, created, **kwargs):
    if not created:
        return
    tema = instance.tema
    # El primer mensaje es el que abre el tema: se avisa como tema nuevo
    nuevo = not tema.mensajes.exclude(pk=instance.pk).exists()
    personas = set(alumnos_del_curso(tema.curso_id)) | {tema.curso.profesor_id}
    personas.discard(instance.autor_id)
    titulo = f'Nuevo tema en el foro de {tema.curso.nombre}' if nuevo else f'{instance.autor.get_short_name()} comentó en «{tema.titulo}»'
    notificar(personas, titulo, instance.contenido[:140], etiqueta=f'foro-{tema.pk}')


@receiver(pre_save, sender=Asistencia)
def asistencia_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'presente')


@receiver(post_save, sender=Asistencia)
def asistencia_registrada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    if not created and antes is not None and antes['presente'] == instance.presente:
        return
    clase = instance.clase
    estado = 'presente' if instance.presente else 'ausente'
    notificar([instance.inscripcion.alumno_id], f'Asistencia: {estado}',
              f'Quedaste {estado} en la clase «{clase.titulo}» de {clase.modulo.curso.nombre} '
              f'del {clase.fecha:%d/%m}.', etiqueta=f'asistencia-{instance.pk}')


@receiver(post_save, sender=Entrega)
def entrega_recibida(sender, instance, created, **kwargs):
    actividad = instance.actividad
    curso = actividad.clase.modulo.curso
    alumno = instance.inscripcion.alumno.get_short_name()
    accion = 'entregó' if created else 'actualizó su entrega de'
    notificar([curso.profesor_id], f'Nueva entrega en {curso.nombre}', f'{alumno} {accion} «{actividad.titulo}».',
              etiqueta=f'entregas-{actividad.pk}')


# ---------- clases y horario ----------

@receiver(pre_save, sender=Clase)
def clase_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'fecha', 'hora_inicio', 'hora_fin')


@receiver(post_save, sender=Clase)
def clase_programada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    cambio = antes is not None and (antes['fecha'], antes['hora_inicio'], antes['hora_fin']) != (
        instance.fecha, instance.hora_inicio, instance.hora_fin)
    if not created and not cambio:
        return
    curso = instance.modulo.curso
    cuando = f'el {instance.fecha:%d/%m} de {instance.hora_inicio:%H:%M} a {instance.hora_fin:%H:%M}'
    if created:
        notificar(alumnos_del_curso(curso.pk), f'Nueva clase en {curso.nombre}', f'«{instance.titulo}» {cuando}.',
                  etiqueta=f'clase-{instance.pk}')
    else:
        notificar(alumnos_del_curso(curso.pk), f'Cambió una clase de {curso.nombre}',
                  f'«{instance.titulo}» ahora es {cuando}.', etiqueta=f'clase-{instance.pk}')


@receiver(post_delete, sender=Clase)
def clase_cancelada(sender, instance, **kwargs):
    curso = instance.modulo.curso
    notificar(alumnos_del_curso(curso.pk), f'Se canceló una clase de {curso.nombre}',
              f'«{instance.titulo}» del {instance.fecha:%d/%m} ya no se realizará.')


DIAS = ['', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']


@receiver(post_save, sender=BloqueHorario)
def horario_actualizado(sender, instance, created, **kwargs):
    curso = instance.curso
    lugar = f' en {instance.sala}' if instance.sala else ''
    notificar(alumnos_del_curso(curso.pk), f'Horario {"nuevo" if created else "actualizado"} en {curso.nombre}',
              f'Los {DIAS[instance.dia_semana]} de {instance.hora_inicio:%H:%M} a {instance.hora_fin:%H:%M}{lugar}.',
              etiqueta=f'horario-{curso.pk}')


@receiver(post_delete, sender=BloqueHorario)
def horario_eliminado(sender, instance, **kwargs):
    curso = Curso.objects.filter(pk=instance.curso_id).first()
    if curso:
        notificar(alumnos_del_curso(curso.pk), f'Cambió el horario de {curso.nombre}',
                  f'Ya no hay clases los {DIAS[instance.dia_semana]} a las {instance.hora_inicio:%H:%M}.',
                  etiqueta=f'horario-{curso.pk}')


# ---------- cursos e inscripciones ----------

@receiver(pre_save, sender=Inscripcion)
def inscripcion_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'activa')


@receiver(post_save, sender=Inscripcion)
def alumno_inscrito(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    reactivada = antes is not None and not antes['activa'] and instance.activa
    if not instance.activa or not (created or reactivada):
        return
    curso = instance.curso
    notificar([instance.alumno_id], 'Te inscribieron en un curso',
              f'Ya puedes ver {curso.nombre} en la app (profesor: {curso.profesor.get_short_name()}).',
              etiqueta=f'curso-{curso.pk}')
    notificar([curso.profesor_id], f'Nuevo alumno en {curso.nombre}',
              f'Se inscribió {instance.alumno.get_short_name()}.', etiqueta=f'inscritos-{curso.pk}')


@receiver(pre_save, sender=Curso)
def curso_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'profesor_id')


@receiver(post_save, sender=Curso)
def curso_asignado(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    if created or (antes is not None and antes['profesor_id'] != instance.profesor_id):
        notificar([instance.profesor_id], 'Te asignaron un curso',
                  f'Ahora estás a cargo de {instance.nombre}.', etiqueta=f'curso-{instance.pk}')
