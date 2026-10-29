"""Vistas del profesor (fase 3: RF-09 a RF-12)."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from usuarios.views import profesor_required

from .forms import ClaseForm, ModuloForm
from .models import Clase, Curso, Modulo

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


# El profesor solo puede tocar lo que pertenece a sus cursos activos; el resto responde 404

def curso_propio(request, pk):
    return get_object_or_404(Curso, pk=pk, profesor=request.user, activo=True)


def modulo_propio(request, pk):
    return get_object_or_404(Modulo.objects.select_related('curso'), pk=pk,
                             curso__profesor=request.user, curso__activo=True)


def clase_propia(request, pk):
    return get_object_or_404(Clase.objects.select_related('modulo__curso'), pk=pk,
                             modulo__curso__profesor=request.user, modulo__curso__activo=True)


def volver_al_curso(curso, seccion='contenido'):
    return redirect(f"{reverse('profesor_curso', args=[curso.pk])}#{seccion}")


@profesor_required
def profesor_inicio_view(request):
    return render(request, 'profesor/menu.html', {'secciones': SECCIONES_PROFESOR})


@profesor_required
def profesor_cursos_view(request):
    return render(request, 'profesor/cursos.html', {'cursos': cursos_del_profesor(request.user)})


# ---------- Página del curso (RF-10) ----------

def pagina_curso(request, curso, form_modulo=None, form_clase=None, titulo_modal=''):
    """Si un formulario vuelve con errores, se reabre su modal apuntando a la misma dirección."""
    form_abierto = form_modulo or form_clase
    return render(request, 'profesor/curso.html', {
        'curso': curso,
        'modulos': curso.modulos.prefetch_related('clases'),
        'inscripciones': curso.inscripciones.filter(activa=True).select_related('alumno').order_by(
            'alumno__apellido_paterno', 'alumno__primer_nombre'),
        'form_modulo': form_modulo or ModuloForm(auto_id='modulo_%s'),
        'form_clase': form_clase or ClaseForm(auto_id='clase_%s'),
        'modal_abierto': {
            'id': 'modalModulo' if form_modulo else 'modalClase',
            'accion': request.path,
            'titulo': titulo_modal,
        } if form_abierto else None,
    })


@profesor_required
def profesor_curso_view(request, pk):
    return pagina_curso(request, curso_propio(request, pk))


@profesor_required
@require_POST
def modulo_crear_view(request, pk):
    curso = curso_propio(request, pk)
    form = ModuloForm(request.POST, instance=Modulo(curso=curso), auto_id='modulo_%s')
    if not form.is_valid():
        return pagina_curso(request, curso, form_modulo=form, titulo_modal='Agregar módulo')
    modulo = form.save()
    messages.success(request, f'Se agregó el módulo «{modulo.nombre}».')
    return volver_al_curso(curso)


@profesor_required
@require_POST
def modulo_editar_view(request, pk):
    modulo = modulo_propio(request, pk)
    form = ModuloForm(request.POST, instance=modulo, auto_id='modulo_%s')
    if not form.is_valid():
        return pagina_curso(request, modulo.curso, form_modulo=form, titulo_modal='Editar módulo')
    form.save()
    messages.success(request, f'Se guardaron los cambios del módulo «{modulo.nombre}».')
    return volver_al_curso(modulo.curso)


@profesor_required
@require_POST
def modulo_eliminar_view(request, pk):
    modulo = modulo_propio(request, pk)
    try:
        modulo.delete()
    except ProtectedError:
        # Las clases tienen asistencia, material o notas: no se borran para no perder ese historial
        messages.error(request, f'El módulo «{modulo.nombre}» tiene clases. Elimine primero sus clases.')
    else:
        messages.success(request, f'Se eliminó el módulo «{modulo.nombre}».')
    return volver_al_curso(modulo.curso)


@profesor_required
@require_POST
def modulo_mover_view(request, pk, direccion):
    """Intercambia la posición del módulo con el anterior o el siguiente."""
    if direccion not in ('subir', 'bajar'):
        raise Http404
    modulo = modulo_propio(request, pk)
    hermanos = modulo.curso.modulos.all()
    vecino = (hermanos.filter(orden__lt=modulo.orden).order_by('-orden').first() if direccion == 'subir'
              else hermanos.filter(orden__gt=modulo.orden).order_by('orden').first())
    if vecino:
        with transaction.atomic():
            modulo.orden, vecino.orden = vecino.orden, modulo.orden
            modulo.save(update_fields=['orden'])
            vecino.save(update_fields=['orden'])
    return volver_al_curso(modulo.curso)


@profesor_required
@require_POST
def clase_crear_view(request, pk):
    modulo = modulo_propio(request, pk)
    form = ClaseForm(request.POST, instance=Clase(modulo=modulo), auto_id='clase_%s')
    if not form.is_valid():
        return pagina_curso(request, modulo.curso, form_clase=form,
                            titulo_modal=f'Agregar clase a «{modulo.nombre}»')
    clase = form.save()
    messages.success(request, f'Se agregó la clase «{clase.titulo}» a «{modulo.nombre}».')
    return volver_al_curso(modulo.curso)


@profesor_required
@require_POST
def clase_editar_view(request, pk):
    clase = clase_propia(request, pk)
    form = ClaseForm(request.POST, instance=clase, auto_id='clase_%s')
    if not form.is_valid():
        return pagina_curso(request, clase.modulo.curso, form_clase=form, titulo_modal='Editar clase')
    form.save()
    messages.success(request, f'Se guardaron los cambios de la clase «{clase.titulo}».')
    return volver_al_curso(clase.modulo.curso)


@profesor_required
@require_POST
def clase_eliminar_view(request, pk):
    clase = clase_propia(request, pk)
    try:
        clase.delete()
    except ProtectedError:
        messages.error(request, f'La clase «{clase.titulo}» ya tiene asistencia, material o calificaciones '
                                f'registradas, así que no se puede eliminar.')
    else:
        messages.success(request, f'Se eliminó la clase «{clase.titulo}».')
    return volver_al_curso(clase.modulo.curso)
