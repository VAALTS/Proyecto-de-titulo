"""Actividades y calificaciones del profesor (RF-11)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cursos.views_profesor import curso_propio, cursos_del_profesor, pagina_curso, volver_al_curso
from usuarios.models import Rol
from usuarios.views import profesor_required

from .forms import ActividadForm, CalificacionesForm, PreguntaForm, porcentaje
from .models import Actividad, Entrega, Pregunta


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
        if actividad.entregas.exists():
            messages.error(request, f'«{actividad.titulo}» ya tiene entregas de alumnos, así que no se puede '
                                    f'eliminar. Si ya no la usa, ocúltela.')
        else:
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


# ---------- Entregas ----------

def puede_descargar_entrega(usuario, entrega):
    curso = entrega.actividad.curso
    if not curso.activo:
        return False
    if usuario.rol == Rol.PROFESOR:
        return curso.profesor_id == usuario.pk
    # Alumno: la suya, mientras siga inscrito y la actividad esté visible
    return (entrega.inscripcion.alumno_id == usuario.pk and entrega.inscripcion.activa
            and entrega.actividad.visible)


@login_required
def entrega_descargar_view(request, pk):
    """Los archivos no tienen dirección pública: solo los descargan su alumno y el profesor (404 al resto)."""
    entrega = get_object_or_404(Entrega.objects.select_related('actividad__clase__modulo__curso', 'inscripcion'),
                                pk=pk)
    if not puede_descargar_entrega(request.user, entrega) or not entrega.archivo:
        raise Http404
    try:
        return FileResponse(entrega.archivo.open('rb'), as_attachment=True, filename=entrega.nombre_archivo)
    except FileNotFoundError:
        raise Http404


# ---------- Formularios en línea: preguntas de una actividad ----------

def formulario_propio(request, pk):
    actividad = actividad_propia(request, pk)
    if actividad.tipo != Actividad.Tipo.FORMULARIO:
        raise Http404
    return actividad


def pregunta_propia(request, pk):
    pregunta = get_object_or_404(Pregunta.objects.select_related('actividad__clase__modulo__curso'), pk=pk,
                                 actividad__clase__modulo__curso__profesor=request.user,
                                 actividad__clase__modulo__curso__activo=True,
                                 actividad__tipo=Actividad.Tipo.FORMULARIO)
    return pregunta


def pagina_formulario(request, actividad, form=None, titulo_modal=''):
    """Si la pregunta vuelve con errores, se reabre su modal apuntando a la misma dirección."""
    preguntas = list(actividad.preguntas.prefetch_related('alternativas'))
    return render(request, 'evaluaciones/formulario.html', {
        'actividad': actividad,
        'curso': actividad.curso,
        'preguntas': preguntas,
        'puntaje_total': actividad.preguntas.aggregate(total=Sum('puntaje'))['total'] or 0,
        'form': form or PreguntaForm(auto_id='pregunta_%s'),
        # Datos para cargar el modal al editar cada pregunta
        'datos_preguntas': {
            str(pregunta.pk): {
                'enunciado': pregunta.enunciado, 'tipo': pregunta.tipo, 'puntaje': str(pregunta.puntaje),
                'alternativas': [{'texto': a.texto, 'correcta': a.es_correcta} for a in pregunta.alternativas.all()],
            } for pregunta in preguntas
        },
        'modal_abierto': {'accion': request.path, 'titulo': titulo_modal,
                          'alternativas': form.filas_enviadas()} if form else None,
    })


@profesor_required
def actividad_formulario_view(request, pk):
    return pagina_formulario(request, formulario_propio(request, pk))


@profesor_required
@require_POST
def pregunta_crear_view(request, pk):
    actividad = formulario_propio(request, pk)
    form = PreguntaForm(request.POST, instance=Pregunta(actividad=actividad), auto_id='pregunta_%s')
    if not form.is_valid():
        return pagina_formulario(request, actividad, form, 'Agregar pregunta')
    form.save()
    messages.success(request, 'Se agregó la pregunta.')
    return redirect('actividad_formulario', pk=actividad.pk)


@profesor_required
@require_POST
def pregunta_editar_view(request, pk):
    pregunta = pregunta_propia(request, pk)
    form = PreguntaForm(request.POST, instance=pregunta, auto_id='pregunta_%s')
    if not form.is_valid():
        return pagina_formulario(request, Actividad.objects.get(pk=pregunta.actividad_id), form, 'Editar pregunta')
    form.save()
    messages.success(request, 'Se guardaron los cambios de la pregunta.')
    return redirect('actividad_formulario', pk=pregunta.actividad_id)


@profesor_required
@require_POST
def pregunta_eliminar_view(request, pk):
    pregunta = pregunta_propia(request, pk)
    pregunta.delete()
    messages.success(request, 'Se eliminó la pregunta.')
    return redirect('actividad_formulario', pk=pregunta.actividad_id)


@profesor_required
@require_POST
def pregunta_mover_view(request, pk, direccion):
    """Intercambia la posición de la pregunta con la anterior o la siguiente."""
    if direccion not in ('subir', 'bajar'):
        raise Http404
    pregunta = pregunta_propia(request, pk)
    hermanas = pregunta.actividad.preguntas.all()
    vecina = (hermanas.filter(orden__lt=pregunta.orden).order_by('-orden').first() if direccion == 'subir'
              else hermanas.filter(orden__gt=pregunta.orden).order_by('orden').first())
    if vecina:
        with transaction.atomic():
            pregunta.orden, vecina.orden = vecina.orden, pregunta.orden
            pregunta.save(update_fields=['orden'])
            vecina.save(update_fields=['orden'])
    return redirect('actividad_formulario', pk=pregunta.actividad_id)
