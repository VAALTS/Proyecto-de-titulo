"""Vistas del profesor (fase 3: RF-09 a RF-12)."""
from django.db.models import Count, Q
from django.shortcuts import render

from usuarios.views import profesor_required

from .models import Curso

# Accesos del menú del profesor (RF-09). Las secciones sin `url` aún no están construidas
# y se muestran como «Próximamente» para no dejar enlaces rotos.
SECCIONES_PROFESOR = [
    {'titulo': 'Cursos', 'descripcion': 'Revisa tus cursos, su material, sus alumnos y pasa asistencia.',
     'icono': 'bi-journal-bookmark-fill', 'color': 'primary', 'url': 'profesor_cursos'},
    {'titulo': 'Gestión de Evaluaciones', 'descripcion': 'Crea actividades y registra las calificaciones.',
     'icono': 'bi-clipboard-check-fill', 'color': 'success', 'url': None},
    {'titulo': 'Horario', 'descripcion': 'Consulta tu calendario semanal de clases.',
     'icono': 'bi-calendar-week-fill', 'color': 'warning', 'url': None},
    {'titulo': 'Asistencia por clase', 'descripcion': 'Consulta el historial de asistencia de cada clase.',
     'icono': 'bi-person-check-fill', 'color': 'danger', 'url': None},
]


def cursos_del_profesor(profesor):
    """Cursos activos a cargo del profesor, con la cantidad de alumnos inscritos."""
    return (Curso.objects.activos().filter(profesor=profesor)
            .annotate(inscritos=Count('inscripciones', filter=Q(inscripciones__activa=True)))
            .order_by('nombre'))


@profesor_required
def profesor_inicio_view(request):
    return render(request, 'profesor/menu.html', {'secciones': SECCIONES_PROFESOR})


@profesor_required
def profesor_cursos_view(request):
    return render(request, 'profesor/cursos.html', {'cursos': cursos_del_profesor(request.user)})
