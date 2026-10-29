"""Vistas del profesor (fase 3: RF-09 a RF-12)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, ProtectedError, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from usuarios.models import Rol
from usuarios.views import profesor_required

from .forms import ClaseForm, MaterialForm, ModuloForm
from .models import Clase, Curso, Material, Modulo

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


def material_propio(request, pk):
    return get_object_or_404(Material.objects.select_related('clase__modulo__curso'), pk=pk,
                             clase__modulo__curso__profesor=request.user, clase__modulo__curso__activo=True)


def volver_al_curso(curso, seccion='contenido'):
    return redirect(f"{reverse('profesor_curso', args=[curso.pk])}#{seccion}")


@profesor_required
def profesor_inicio_view(request):
    return render(request, 'profesor/menu.html', {'secciones': SECCIONES_PROFESOR})


@profesor_required
def profesor_cursos_view(request):
    return render(request, 'profesor/cursos.html', {'cursos': cursos_del_profesor(request.user)})


# ---------- Página del curso (RF-10) ----------

# Cada modal de la página y su formulario vacío
FORMULARIOS_CURSO = {
    'modalModulo': ('form_modulo', lambda: ModuloForm(auto_id='modulo_%s')),
    'modalClase': ('form_clase', lambda: ClaseForm(auto_id='clase_%s')),
    'modalMaterial': ('form_material', lambda: MaterialForm(auto_id='material_%s')),
}


def organizar_material(modulos):
    """Deja en cada clase su material de primer nivel (carpetas primero) y en cada carpeta su contenido."""
    for modulo in modulos:
        for clase in modulo.clases.all():
            materiales = list(clase.materiales.all())
            for material in materiales:
                material.hijos = [hijo for hijo in materiales if hijo.carpeta_id == material.pk]
            clase.raiz = sorted((m for m in materiales if m.carpeta_id is None),
                                key=lambda m: (m.tipo != Material.Tipo.CARPETA, m.titulo.lower()))
    return modulos


def pagina_curso(request, curso, form=None, id_modal='', titulo_modal=''):
    """Si un formulario vuelve con errores, se reabre su modal apuntando a la misma dirección."""
    modulos = organizar_material(list(curso.modulos.prefetch_related(
        Prefetch('clases__materiales', queryset=Material.objects.order_by('titulo')))))
    contexto = {
        'curso': curso,
        'modulos': modulos,
        'inscripciones': curso.inscripciones.filter(activa=True).select_related('alumno').order_by(
            'alumno__apellido_paterno', 'alumno__primer_nombre'),
        'modal_abierto': {'id': id_modal, 'accion': request.path, 'titulo': titulo_modal} if form else None,
    }
    for modal, (nombre, vacio) in FORMULARIOS_CURSO.items():
        contexto[nombre] = form if modal == id_modal else vacio()
    return render(request, 'profesor/curso.html', contexto)


@profesor_required
def profesor_curso_view(request, pk):
    return pagina_curso(request, curso_propio(request, pk))


@profesor_required
@require_POST
def modulo_crear_view(request, pk):
    curso = curso_propio(request, pk)
    form = ModuloForm(request.POST, instance=Modulo(curso=curso), auto_id='modulo_%s')
    if not form.is_valid():
        return pagina_curso(request, curso, form, 'modalModulo', 'Agregar módulo')
    modulo = form.save()
    messages.success(request, f'Se agregó el módulo «{modulo.nombre}».')
    return volver_al_curso(curso)


@profesor_required
@require_POST
def modulo_editar_view(request, pk):
    modulo = modulo_propio(request, pk)
    form = ModuloForm(request.POST, instance=modulo, auto_id='modulo_%s')
    if not form.is_valid():
        return pagina_curso(request, modulo.curso, form, 'modalModulo', 'Editar módulo')
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
        return pagina_curso(request, modulo.curso, form, 'modalClase', f'Agregar clase a «{modulo.nombre}»')
    clase = form.save()
    messages.success(request, f'Se agregó la clase «{clase.titulo}» a «{modulo.nombre}».')
    return volver_al_curso(modulo.curso)


@profesor_required
@require_POST
def clase_editar_view(request, pk):
    clase = clase_propia(request, pk)
    form = ClaseForm(request.POST, instance=clase, auto_id='clase_%s')
    if not form.is_valid():
        return pagina_curso(request, clase.modulo.curso, form, 'modalClase', 'Editar clase')
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


# ---------- Material de las clases (RF-10) ----------

def guardar_material(request, form, curso, titulo_modal, mensaje):
    if not form.is_valid():
        return pagina_curso(request, curso, form, 'modalMaterial', titulo_modal)
    material = form.save()
    messages.success(request, mensaje.format(titulo=material.titulo))
    return volver_al_curso(curso)


@profesor_required
@require_POST
def material_crear_view(request, pk):
    clase = clase_propia(request, pk)
    material = Material(clase=clase, subido_por=request.user)
    form = MaterialForm(request.POST, request.FILES, instance=material, auto_id='material_%s')
    return guardar_material(request, form, clase.modulo.curso, f'Agregar material a «{clase.titulo}»',
                            'Se agregó «{titulo}».')


@profesor_required
@require_POST
def material_crear_en_carpeta_view(request, pk):
    carpeta = material_propio(request, pk)
    if carpeta.tipo != Material.Tipo.CARPETA:
        raise Http404
    material = Material(clase=carpeta.clase, carpeta=carpeta, subido_por=request.user)
    form = MaterialForm(request.POST, request.FILES, instance=material, auto_id='material_%s')
    return guardar_material(request, form, carpeta.clase.modulo.curso, f'Agregar a la carpeta «{carpeta.titulo}»',
                            'Se agregó «{titulo}» a la carpeta «' + carpeta.titulo + '».')


@profesor_required
@require_POST
def material_editar_view(request, pk):
    material = material_propio(request, pk)
    form = MaterialForm(request.POST, request.FILES, instance=material, auto_id='material_%s')
    return guardar_material(request, form, material.clase.modulo.curso, 'Editar material',
                            'Se guardaron los cambios de «{titulo}».')


@profesor_required
@require_POST
def material_visibilidad_view(request, pk):
    material = material_propio(request, pk)
    material.visible = not material.visible
    material.save(update_fields=['visible'])
    estado = 'visible para los alumnos' if material.visible else 'oculto para los alumnos'
    messages.success(request, f'«{material.titulo}» quedó {estado}.')
    return volver_al_curso(material.clase.modulo.curso)


@profesor_required
@require_POST
def material_eliminar_view(request, pk):
    material = material_propio(request, pk)
    archivo = material.archivo
    try:
        material.delete()
    except ProtectedError:
        messages.error(request, f'La carpeta «{material.titulo}» tiene contenido. Elimine primero lo que contiene.')
    else:
        if archivo:
            archivo.delete(save=False)
        messages.success(request, f'Se eliminó «{material.titulo}».')
    return volver_al_curso(material.clase.modulo.curso)


def puede_descargar(usuario, material):
    curso = material.clase.modulo.curso
    if usuario.rol == Rol.ADMINISTRADOR:
        return True
    if usuario.rol == Rol.PROFESOR:
        return curso.profesor_id == usuario.pk and curso.activo
    # Alumno: inscrito en el curso, y el material (y su carpeta) visibles
    return (curso.activo and material.visible_para_alumnos()
            and curso.inscripciones.filter(alumno=usuario, activa=True).exists())


@login_required
def material_descargar_view(request, pk):
    """Los archivos no tienen dirección pública: se entregan solo a quien tiene permiso (404 al resto)."""
    material = get_object_or_404(Material.objects.select_related('clase__modulo__curso', 'carpeta'), pk=pk,
                                 tipo=Material.Tipo.ARCHIVO)
    if not puede_descargar(request.user, material) or not material.archivo:
        raise Http404
    try:
        return FileResponse(material.archivo.open('rb'), as_attachment=True, filename=material.nombre_archivo)
    except FileNotFoundError:
        raise Http404
