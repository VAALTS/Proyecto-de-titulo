"""Promedio ponderado de un alumno en un curso (RF-11 y RF-15)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count

from cursos.models import Inscripcion

from .models import Actividad, Calificacion


def promedio_ponderado(notas_y_ponderaciones):
    """Recibe pares (nota, ponderación) de las actividades calificadas.

    Devuelve (promedio, porcentaje evaluado). Mientras el porcentaje evaluado no llegue a 100,
    el promedio es parcial: se calcula solo sobre lo ya evaluado. Se redondea a un decimal,
    con 0,05 hacia arriba, como en la escala chilena.
    """
    pares = [(Decimal(nota), Decimal(ponderacion)) for nota, ponderacion in notas_y_ponderaciones]
    evaluado = sum((ponderacion for _, ponderacion in pares), Decimal('0'))
    if not evaluado:
        return None, Decimal('0')
    promedio = sum(nota * ponderacion for nota, ponderacion in pares) / evaluado
    return promedio.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP), evaluado


def resumen_del_curso(curso, inscripciones):
    """Actividades del curso y la planilla de notas: cada alumno con su nota por actividad y su promedio."""
    actividades = list(Actividad.objects.filter(clase__modulo__curso=curso).select_related('clase')
                       .annotate(calificadas=Count('calificaciones', distinct=True),
                                 cantidad_preguntas=Count('preguntas', distinct=True))
                       .order_by('fecha_limite', 'titulo'))
    notas = {(c.inscripcion_id, c.actividad_id): c.nota
             for c in Calificacion.objects.filter(actividad__in=actividades)}
    filas = []
    for inscripcion in inscripciones:
        notas_alumno = [notas.get((inscripcion.pk, actividad.pk)) for actividad in actividades]
        promedio, evaluado = promedio_ponderado(
            (nota, actividad.ponderacion) for nota, actividad in zip(notas_alumno, actividades) if nota is not None)
        filas.append({'inscripcion': inscripcion, 'notas': notas_alumno, 'promedio': promedio, 'evaluado': evaluado})
    return {
        'actividades': actividades,
        'filas_notas': filas,
        'ponderacion_asignada': sum((a.ponderacion for a in actividades), Decimal('0')),
    }


def calificaciones_del_alumno(alumno):
    """Notas de un alumno agrupadas por curso, con el promedio de cada uno (RF-15 y RF-17).

    Una actividad oculta aparece solo si ya tiene nota: así el promedio coincide con el de la planilla
    del profesor, que cuenta todas las notas.
    """
    inscripciones = list(Inscripcion.objects.filter(alumno=alumno, activa=True, curso__activo=True)
                         .select_related('curso__profesor').order_by('curso__nombre'))
    actividades_por_curso = {}
    for actividad in (Actividad.objects.filter(clase__modulo__curso__in=[i.curso_id for i in inscripciones])
                      .select_related('clase__modulo').order_by('fecha_limite', 'titulo')):
        actividades_por_curso.setdefault(actividad.clase.modulo.curso_id, []).append(actividad)
    calificaciones = {(c.inscripcion_id, c.actividad_id): c
                      for c in Calificacion.objects.filter(inscripcion__in=inscripciones)}
    resumen = []
    for inscripcion in inscripciones:
        filas = []
        for actividad in actividades_por_curso.get(inscripcion.curso_id, []):
            calificacion = calificaciones.get((inscripcion.pk, actividad.pk))
            if actividad.visible or calificacion:
                filas.append({'actividad': actividad, 'calificacion': calificacion})
        promedio, evaluado = promedio_ponderado(
            (fila['calificacion'].nota, fila['actividad'].ponderacion) for fila in filas if fila['calificacion'])
        resumen.append({'curso': inscripcion.curso, 'filas': filas, 'promedio': promedio, 'evaluado': evaluado})
    return resumen
