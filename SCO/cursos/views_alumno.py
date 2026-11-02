"""Vistas del alumno (fase 4: RF-13 a RF-17)."""
from django.shortcuts import render

from evaluaciones.calculos import calificaciones_del_alumno
from usuarios.views import alumno_required

from .calendario import eventos_de_calendario
from .models import BloqueHorario, Curso

# Accesos del menú del alumno (RF-13)
SECCIONES_ALUMNO = [
    {'titulo': 'Cursos', 'descripcion': 'Revisa el contenido de tus capacitaciones y entrega tus actividades.',
     'icono': 'bi-journal-bookmark-fill', 'color': 'primary', 'url': 'alumno_cursos'},
    {'titulo': 'Horario', 'descripcion': 'Consulta tu calendario semanal de clases.',
     'icono': 'bi-calendar-week-fill', 'color': 'warning', 'url': 'alumno_horario'},
    {'titulo': 'Calificaciones', 'descripcion': 'Revisa tus notas y el promedio de cada curso.',
     'icono': 'bi-clipboard-data-fill', 'color': 'success', 'url': 'alumno_calificaciones'},
]


def cursos_del_alumno(alumno):
    """Cursos activos en que el alumno tiene una inscripción vigente."""
    return (Curso.objects.activos().filter(inscripciones__alumno=alumno, inscripciones__activa=True)
            .select_related('profesor').order_by('nombre'))


@alumno_required
def alumno_inicio_view(request):
    return render(request, 'alumno/menu.html', {'secciones': SECCIONES_ALUMNO})


@alumno_required
def alumno_cursos_view(request):
    return render(request, 'alumno/cursos.html', {'cursos': cursos_del_alumno(request.user)})


@alumno_required
def alumno_horario_view(request):
    """RF-14: calendario semanal con los bloques de los cursos del alumno."""
    bloques = BloqueHorario.objects.filter(curso__in=cursos_del_alumno(request.user)).select_related('curso')
    return render(request, 'alumno/horario.html', {'eventos': eventos_de_calendario(bloques)})


@alumno_required
def alumno_calificaciones_view(request):
    """RF-15: notas agrupadas por curso, con el promedio ponderado calculado en cada consulta."""
    return render(request, 'alumno/calificaciones.html', {'cursos': calificaciones_del_alumno(request.user)})
