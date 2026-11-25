"""Avisos al teléfono cuando pasa algo en un curso, se haga desde la web o desde la aplicación móvil.

- Material o actividad nuevos (o que el profesor vuelve visibles): a los alumnos del curso.
- Encuesta nueva: a los alumnos del curso.
- Nota nueva o modificada: al alumno.
- Mensaje en el foro: a quienes participan del curso, menos a quien escribió.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from cursos.models import Encuesta, Inscripcion, Material, MensajeForo
from evaluaciones.models import Actividad, Calificacion

from .push import enviar_despues, push_activo


def alumnos_del_curso(curso_id):
    return list(Inscripcion.objects.filter(curso_id=curso_id, activa=True).values_list('alumno_id', flat=True))


def guardar_estado_anterior(instancia, *campos):
    """Antes de guardar, recuerda cómo estaba, para saber si algo cambió."""
    instancia._antes = None
    if instancia.pk and push_activo():
        instancia._antes = type(instancia).objects.filter(pk=instancia.pk).values(*campos).first()


@receiver(pre_save, sender=Material)
def material_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'visible')


@receiver(post_save, sender=Material)
def material_publicado(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    recien_visible = created or (antes is not None and not antes['visible'])
    if not push_activo() or not recien_visible or instance.tipo == Material.Tipo.CARPETA:
        return
    if not instance.visible_para_alumnos():
        return
    curso = instance.clase.modulo.curso
    enviar_despues(alumnos_del_curso(curso.pk), f'Nuevo material en {curso.nombre}', instance.titulo,
                   etiqueta=f'material-{instance.pk}')


@receiver(pre_save, sender=Actividad)
def actividad_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'visible')


@receiver(post_save, sender=Actividad)
def actividad_publicada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    recien_visible = created or (antes is not None and not antes['visible'])
    if not push_activo() or not recien_visible or not instance.visible:
        return
    curso = instance.clase.modulo.curso
    limite = timezone.localtime(instance.fecha_limite)
    enviar_despues(alumnos_del_curso(curso.pk), f'Nueva actividad en {curso.nombre}',
                   f'{instance.titulo} · entrega el {limite:%d/%m a las %H:%M}', etiqueta=f'actividad-{instance.pk}')


@receiver(post_save, sender=Encuesta)
def encuesta_publicada(sender, instance, created, **kwargs):
    if push_activo() and created and instance.visible:
        enviar_despues(alumnos_del_curso(instance.curso_id), f'Nueva encuesta en {instance.curso.nombre}',
                       instance.pregunta, etiqueta=f'encuesta-{instance.pk}')


@receiver(pre_save, sender=Calificacion)
def nota_antes(sender, instance, **kwargs):
    guardar_estado_anterior(instance, 'nota')


@receiver(post_save, sender=Calificacion)
def nota_registrada(sender, instance, created, **kwargs):
    antes = getattr(instance, '_antes', None)
    if not push_activo() or (not created and antes is not None and antes['nota'] == instance.nota):
        return
    actividad = instance.actividad
    nota = str(instance.nota).replace('.', ',')
    enviar_despues([instance.inscripcion.alumno_id], f'Nueva nota en {actividad.curso.nombre}',
                   f'{actividad.titulo}: {nota}', etiqueta=f'nota-{instance.pk}')


@receiver(post_save, sender=MensajeForo)
def mensaje_en_el_foro(sender, instance, created, **kwargs):
    if not push_activo() or not created:
        return
    tema = instance.tema
    # El primer mensaje es el que abre el tema: se avisa como tema nuevo
    nuevo = not tema.mensajes.exclude(pk=instance.pk).exists()
    personas = set(alumnos_del_curso(tema.curso_id)) | {tema.curso.profesor_id}
    personas.discard(instance.autor_id)
    titulo = f'Nuevo tema en el foro de {tema.curso.nombre}' if nuevo else f'{instance.autor.get_short_name()} comentó en «{tema.titulo}»'
    enviar_despues(personas, titulo, instance.contenido[:140], etiqueta=f'foro-{tema.pk}')
