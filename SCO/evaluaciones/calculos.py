"""Promedio ponderado de un alumno en un curso (RF-11, y lo verá el alumno en el RF-15)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count

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
                       .annotate(calificadas=Count('calificaciones')).order_by('fecha_limite', 'titulo'))
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
