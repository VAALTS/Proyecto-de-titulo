"""Actividades y calificaciones del profesor (RF-11)."""
from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from cursos.views_profesor import curso_propio, cursos_del_profesor, pagina_curso, volver_al_curso
from usuarios.views import profesor_required

from .forms import ActividadForm, CalificacionesForm, porcentaje
from .models import Actividad


def actividad_propia(request, pk):
    """Solo las actividades de los cursos activos del profesor; el resto responde 404."""
    return get_object_or_404(Actividad.objects.select_related('clase__modulo__curso'), pk=pk,
                             clase__modulo__curso__profesor=request.user, clase__modulo__curso__activo=True)


# ---------- Actividades ----------

@profesor_required
@require_POST
def actividad_crear_view(request, pk):
    curso = curso_propio(request, pk)
    form = ActividadForm(curso, request.POST, auto_id='actividad_%s')
    if not form.is_valid():
        return pagina_curso(request, curso, form, 'modalActividad', 'Crear actividad')
    actividad = form.save()
    messages.success(request, f'Se creó la actividad «{actividad.titulo}» ({porcentaje(actividad.ponderacion)} %).')
    return volver_al_curso(curso, 'actividades')


@profesor_required
@require_POST
def actividad_editar_view(request, pk):
    actividad = actividad_propia(request, pk)
    curso = actividad.curso
    form = ActividadForm(curso, request.POST, instance=actividad, auto_id='actividad_%s')
    if not form.is_valid():
        return pagina_curso(request, curso, form, 'modalActividad', 'Editar actividad')
    form.save()
    messages.success(request, f'Se guardaron los cambios de «{actividad.titulo}».')
    return volver_al_curso(curso, 'actividades')


@profesor_required
@require_POST
def actividad_visibilidad_view(request, pk):
    actividad = actividad_propia(request, pk)
    actividad.visible = not actividad.visible
    actividad.save(update_fields=['visible'])
    estado = 'visible para los alumnos' if actividad.visible else 'oculta para los alumnos'
    messages.success(request, f'«{actividad.titulo}» quedó {estado}.')
    return volver_al_curso(actividad.curso, 'actividades')


@profesor_required
@require_POST
def actividad_eliminar_view(request, pk):
    actividad = actividad_propia(request, pk)
    try:
        actividad.delete()
    except ProtectedError:
        messages.error(request, f'«{actividad.titulo}» ya tiene calificaciones. Bórrelas en la planilla de notas '
                                f'para poder eliminarla.')
    else:
        messages.success(request, f'Se eliminó la actividad «{actividad.titulo}».')
    return volver_al_curso(actividad.curso, 'actividades')


# ---------- Calificaciones ----------

@profesor_required
def actividad_calificar_view(request, pk):
    """Planilla de notas de una actividad: nota de 1,0 a 7,0 y observación por alumno."""
    actividad = actividad_propia(request, pk)
    curso = actividad.curso
    inscripciones = curso.inscripciones.filter(activa=True).select_related('alumno').order_by(
        'alumno__apellido_paterno', 'alumno__primer_nombre')
    form = CalificacionesForm(actividad, inscripciones, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        calificadas = form.save(request.user)
        messages.success(request, f'Se guardaron las notas de «{actividad.titulo}»: {calificadas} de '
                                  f'{len(form.inscripciones)} alumnos calificados.')
        return volver_al_curso(curso, 'calificaciones')
    return render(request, 'evaluaciones/calificar.html', {'actividad': actividad, 'curso': curso, 'form': form})


@profesor_required
def profesor_evaluaciones_view(request):
    """Gestión de Evaluaciones (RF-09): las actividades de todos sus cursos y cuántas faltan por calificar."""
    cursos = cursos_del_profesor(request.user)
    actividades = (Actividad.objects.filter(clase__modulo__curso__in=cursos).select_related('clase__modulo__curso')
                   .annotate(calificadas=Count('calificaciones', filter=Q(calificaciones__inscripcion__activa=True))))
    curso_elegido = request.GET.get('curso', '')
    if curso_elegido.isdigit():
        actividades = actividades.filter(clase__modulo__curso_id=int(curso_elegido))
    inscritos = {curso.pk: curso.inscritos for curso in cursos}
    actividades = list(actividades.order_by('fecha_limite'))
    for actividad in actividades:
        actividad.inscritos = inscritos[actividad.clase.modulo.curso_id]
    return render(request, 'evaluaciones/evaluaciones.html', {
        'cursos': cursos, 'actividades': actividades, 'curso_elegido': curso_elegido,
    })
