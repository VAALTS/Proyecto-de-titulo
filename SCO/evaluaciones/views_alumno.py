"""Actividades del alumno: instrucciones, entrega de archivos y nota (RF-16)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from cursos.models import Inscripcion
from usuarios.views import alumno_required

from .forms import EntregaForm
from .models import Actividad


@alumno_required
def alumno_actividad_view(request, pk):
    """Solo actividades visibles de sus cursos; el resto responde 404."""
    actividad = get_object_or_404(Actividad.objects.select_related('clase__modulo__curso'), pk=pk, visible=True)
    curso = actividad.curso
    inscripcion = get_object_or_404(Inscripcion, curso=curso, alumno=request.user, activa=True, curso__activo=True)
    entrega = inscripcion.entregas.filter(actividad=actividad).first()
    calificacion = inscripcion.calificaciones.filter(actividad=actividad).first()
    # Ya calificada no se cambia: la nota debe corresponder a lo que revisó el profesor
    puede_entregar = actividad.tipo == Actividad.Tipo.ARCHIVO and actividad.abierta and not calificacion

    form = EntregaForm(request.POST, request.FILES) if request.method == 'POST' else EntregaForm()
    if request.method == 'POST':
        if not puede_entregar:
            messages.error(request, 'Esta actividad ya no recibe entregas.')
            return redirect('alumno_actividad', pk=actividad.pk)
        if form.is_valid():
            form.save(actividad, inscripcion)
            messages.success(request, 'Tu entrega se guardó correctamente.')
            return redirect('alumno_actividad', pk=actividad.pk)

    return render(request, 'evaluaciones/actividad_alumno.html', {
        'actividad': actividad,
        'curso': curso,
        'entrega': entrega,
        'calificacion': calificacion,
        'puede_entregar': puede_entregar,
        'form': form,
    })
