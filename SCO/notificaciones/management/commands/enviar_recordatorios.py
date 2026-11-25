"""Recordatorios automáticos en la bandeja de la app y en el teléfono (RF-07 y RF-08 de la aplicación móvil).

- RF-07: actividad pendiente, cuando falta 1 día, 12 horas, 3 horas y 1 hora para la entrega.
- RF-08: próxima clase, 1 hora, 30 minutos y 5 minutos antes (según el horario semanal del curso).

Uso:
    python manage.py enviar_recordatorios            # revisa una vez
    python manage.py enviar_recordatorios --cada 120 # revisa cada 2 minutos, sin parar (así corre en Railway)

Cada recordatorio se envía una sola vez por persona (tabla RecordatorioEnviado). Si el proceso estuvo detenido,
solo se manda el aviso más cercano, no todos los atrasados.
"""
import logging
import time as reloj
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from cursos.models import BloqueHorario, Inscripcion
from evaluaciones.models import Actividad, Entrega

from ...models import RecordatorioEnviado
from ...push import enviar, guardar_en_bandeja

logger = logging.getLogger(__name__)

AVISOS_ACTIVIDAD = [(timedelta(hours=1), '1 hora'), (timedelta(hours=3), '3 horas'),
                    (timedelta(hours=12), '12 horas'), (timedelta(days=1), '1 día')]
AVISOS_CLASE = [(timedelta(minutes=5), '5 minutos'), (timedelta(minutes=30), '30 minutos'),
                (timedelta(hours=1), '1 hora')]
DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']


def aviso_que_toca(falta, avisos):
    """El aviso más cercano que ya corresponde: si faltan 2 horas, el de "3 horas"."""
    for limite, texto in avisos:
        if falta <= limite:
            return texto
    return None


def marcar(usuario_id, clave):
    """True si este recordatorio todavía no se le había enviado a esa persona."""
    if RecordatorioEnviado.objects.filter(usuario_id=usuario_id, clave=clave).exists():
        return False
    try:
        with transaction.atomic():
            RecordatorioEnviado.objects.create(usuario_id=usuario_id, clave=clave)
        return True
    except IntegrityError:  # Otro proceso lo envió justo al mismo tiempo
        return False


def avisar(usuario_id, titulo, cuerpo, etiqueta):
    """Deja el recordatorio en la bandeja y lo envía al teléfono, si tiene uno registrado."""
    guardar_en_bandeja([usuario_id], titulo, cuerpo)
    enviar([usuario_id], titulo, cuerpo, etiqueta=etiqueta)
    return 1


def recordatorios_de_actividades(ahora):
    enviados = 0
    actividades = (Actividad.objects.filter(visible=True, clase__modulo__curso__activo=True,
                                            fecha_limite__gt=ahora, fecha_limite__lte=ahora + timedelta(days=1))
                   .select_related('clase__modulo__curso'))
    for actividad in actividades:
        texto = aviso_que_toca(actividad.fecha_limite - ahora, AVISOS_ACTIVIDAD)
        curso = actividad.clase.modulo.curso
        entregaron = set(Entrega.objects.filter(actividad=actividad).values_list('inscripcion__alumno_id', flat=True))
        alumnos = (Inscripcion.objects.filter(curso=curso, activa=True)
                   .exclude(alumno_id__in=entregaron).values_list('alumno_id', flat=True))
        fecha = timezone.localtime(actividad.fecha_limite)
        for alumno_id in alumnos:
            if marcar(alumno_id, f'actividad-{actividad.pk}-{texto}'):
                enviados += avisar(
                    alumno_id, f'Falta{"" if texto.startswith("1 ") else "n"} {texto} para la entrega',
                    f'Recuerde que tiene una actividad pendiente «{actividad.titulo}» del curso {curso.nombre} '
                    f'con fecha de entrega el {DIAS[fecha.weekday()]} {fecha:%d/%m a las %H:%M}.',
                    etiqueta=f'actividad-{actividad.pk}')
    return enviados


def recordatorios_de_clases(ahora):
    enviados = 0
    hoy = timezone.localtime(ahora)
    bloques = BloqueHorario.objects.filter(dia_semana=hoy.isoweekday(), curso__activo=True).select_related('curso')
    for bloque in bloques:
        inicio = timezone.make_aware(datetime.combine(hoy.date(), bloque.hora_inicio))
        falta = inicio - ahora
        if falta <= timedelta(0):
            continue
        texto = aviso_que_toca(falta, AVISOS_CLASE)
        if not texto:
            continue
        personas = set(Inscripcion.objects.filter(curso=bloque.curso, activa=True).values_list('alumno_id', flat=True))
        personas.add(bloque.curso.profesor_id)
        lugar = f' ({bloque.sala})' if bloque.sala else ''
        for persona_id in personas:
            if marcar(persona_id, f'clase-{bloque.pk}-{hoy:%Y%m%d}-{texto}'):
                enviados += avisar(
                    persona_id, f'Tu clase comienza en {texto}',
                    f'Recuerde conectarse a la clase de {bloque.curso.nombre} a realizarse a las '
                    f'{bloque.hora_inicio:%H:%M} horas{lugar}.',
                    etiqueta=f'clase-{bloque.pk}')
    return enviados


def revisar():
    ahora = timezone.now()
    return recordatorios_de_actividades(ahora) + recordatorios_de_clases(ahora)


class Command(BaseCommand):
    help = 'Envía los recordatorios de actividades y clases a los teléfonos (RF-07 y RF-08 de la app).'

    def add_arguments(self, parser):
        parser.add_argument('--cada', type=int, default=0,
                            help='Segundos entre revisiones. Sin este valor, revisa una sola vez.')

    def handle(self, *args, cada=0, **options):
        while True:
            try:
                enviados = revisar()
                if enviados or not cada:
                    self.stdout.write(f'Recordatorios enviados: {enviados}')
            except Exception:
                # Un error puntual (por ejemplo, la base reiniciándose) no debe detener los recordatorios
                logger.exception('Error al enviar recordatorios')
            if not cada:
                break
            # Entre revisiones se suelta la conexión, por si la base se reinició mientras tanto
            close_old_connections()
            reloj.sleep(cada)
