from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from usuarios.views import admin_required

from .forms import CursoForm, InscripcionForm
from .models import Curso, Inscripcion

# ---------- Gestión de cursos (RF-06) ----------


def buscar_cursos(texto, con_eliminados):
    """Cada palabra buscada debe aparecer en el nombre del curso o del profesor a cargo."""
    cursos = Curso.objects.select_related('profesor').annotate(
        inscritos=Count('inscripciones', filter=Q(inscripciones__activa=True)))
    if not con_eliminados:
        cursos = cursos.activos()
    for palabra in texto.split():
        cursos = cursos.filter(
            Q(nombre__icontains=palabra) | Q(profesor__primer_nombre__icontains=palabra)
            | Q(profesor__apellido_paterno__icontains=palabra) | Q(profesor__apellido_materno__icontains=palabra)
        )
    return cursos.order_by('-activo', 'nombre')


def pagina_cursos(request, form_creacion=None):
    datos = request.POST if request.method == 'POST' else request.GET
    busqueda = datos.get('q', '').strip()
    con_eliminados = datos.get('eliminados') == '1'
    return render(request, 'cursos/lista.html', {
        'cursos': buscar_cursos(busqueda, con_eliminados),
        'q': busqueda,
        'con_eliminados': con_eliminados,
        'form_creacion': form_creacion or CursoForm(auto_id='creacion_%s'),
        'abrir_modal': 'modalCreacion' if form_creacion else '',
    })


def pagina_detalle(request, curso, form_edicion=None, form_inscripcion=None):
    return render(request, 'cursos/detalle.html', {
        'curso': curso,
        'inscripciones': curso.inscripciones.filter(activa=True).select_related('alumno').order_by(
            'alumno__apellido_paterno', 'alumno__primer_nombre'),
        'form_edicion': form_edicion or CursoForm(instance=curso, auto_id='edicion_%s'),
        'form_inscripcion': form_inscripcion or InscripcionForm(curso, auto_id='inscripcion_%s'),
        'abrir_modal': 'modalEdicion' if form_edicion else '',
    })


@admin_required
def gestion_cursos_view(request):
    return pagina_cursos(request)


@admin_required
@require_POST
def curso_crear_view(request):
    form = CursoForm(request.POST, auto_id='creacion_%s')
    if not form.is_valid():
        return pagina_cursos(request, form_creacion=form)

    curso = form.save()
    messages.success(request, f'Se creó el curso «{curso.nombre}». Su lista de alumnos está vacía por ahora.')
    return redirect('curso_detalle', pk=curso.pk)


@admin_required
def curso_detalle_view(request, pk):
    # Un curso eliminado se puede consultar (y restaurar), pero no modificar
    return pagina_detalle(request, get_object_or_404(Curso, pk=pk))


@admin_required
@require_POST
def curso_editar_view(request, pk):
    curso = get_object_or_404(Curso, pk=pk, activo=True)
    form = CursoForm(request.POST, instance=curso, auto_id='edicion_%s')
    if not form.is_valid():
        # El formulario ya copió los datos inválidos a `curso`; se muestra el registro guardado
        return pagina_detalle(request, Curso.objects.get(pk=pk), form_edicion=form)

    form.save()
    messages.success(request, f'Se guardaron los cambios del curso «{curso.nombre}».')
    return redirect('curso_detalle', pk=curso.pk)


@admin_required
@require_POST
def curso_eliminar_view(request, pk):
    curso = get_object_or_404(Curso, pk=pk, activo=True)
    curso.eliminar()
    messages.success(request, f'Se eliminó el curso «{curso.nombre}». Sus alumnos inscritos y su historial '
                              f'se conservan; puede restaurarlo desde «Mostrar eliminados».')
    return redirect('gestion_cursos')


@admin_required
@require_POST
def curso_restaurar_view(request, pk):
    curso = get_object_or_404(Curso, pk=pk, activo=False)
    curso.restaurar()
    messages.success(request, f'Se restauró el curso «{curso.nombre}».')
    return redirect('curso_detalle', pk=curso.pk)


# ---------- Asignación de alumnos a cursos (RF-07) ----------

@admin_required
@require_POST
def curso_inscribir_view(request, pk):
    # Un curso eliminado no recibe nuevas inscripciones
    curso = get_object_or_404(Curso, pk=pk, activo=True)
    form = InscripcionForm(curso, request.POST, auto_id='inscripcion_%s')
    if not form.is_valid():
        return pagina_detalle(request, curso, form_inscripcion=form)

    alumnos = form.save()
    if len(alumnos) == 1:
        messages.success(request, f'Se inscribió a {alumnos[0].get_short_name()} en «{curso.nombre}».')
    else:
        messages.success(request, f'Se inscribieron {len(alumnos)} alumnos en «{curso.nombre}».')
    return redirect('curso_detalle', pk=curso.pk)


@admin_required
@require_POST
def curso_retirar_view(request, pk, inscripcion_pk):
    # Retirar no borra la inscripción: queda como historial y se puede volver a inscribir
    inscripcion = get_object_or_404(Inscripcion.objects.select_related('alumno', 'curso'), pk=inscripcion_pk,
                                    curso_id=pk, curso__activo=True, activa=True)
    inscripcion.activa = False
    inscripcion.save(update_fields=['activa'])
    messages.success(request, f'Se retiró a {inscripcion.alumno.get_short_name()} de «{inscripcion.curso.nombre}».')
    return redirect('curso_detalle', pk=pk)
