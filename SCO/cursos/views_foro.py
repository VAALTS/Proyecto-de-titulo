"""Foro de cada curso (RF-16): lo usan el profesor del curso y sus alumnos inscritos."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from usuarios.models import Rol
from usuarios.views import profesor_required

from .forms import MensajeForoForm, TemaForoForm
from .models import Curso, MensajeForo, TemaForo


def puede_usar_foro(usuario, curso):
    if not curso.activo:
        return False
    if usuario.rol == Rol.PROFESOR:
        return curso.profesor_id == usuario.pk
    return curso.inscripciones.filter(alumno=usuario, activa=True).exists()


def curso_del_foro(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    if not puede_usar_foro(request.user, curso):
        raise Http404
    return curso


def tema_del_foro(request, pk):
    tema = get_object_or_404(TemaForo.objects.select_related('curso'), pk=pk)
    if not puede_usar_foro(request.user, tema.curso):
        raise Http404
    return tema


def direccion_del_foro(usuario, curso):
    """El foro es una pestaña de la página del curso, que es distinta para cada rol."""
    pagina = 'profesor_curso' if usuario.rol == Rol.PROFESOR else 'alumno_curso'
    return f"{reverse(pagina, args=[curso.pk])}#foro"


@login_required
def foro_tema_crear_view(request, pk):
    curso = curso_del_foro(request, pk)
    form = TemaForoForm(request.POST or None, instance=TemaForo(curso=curso, autor=request.user))
    if request.method == 'POST' and form.is_valid():
        tema = form.save()
        messages.success(request, f'Se publicó el tema «{tema.titulo}».')
        return redirect('foro_tema', pk=tema.pk)
    return render(request, 'cursos/foro_tema_nuevo.html', {
        'curso': curso, 'form': form, 'volver': direccion_del_foro(request.user, curso),
    })


@login_required
def foro_tema_view(request, pk):
    """Mensajes de un tema, del más antiguo al más nuevo, y el formulario para responder."""
    tema = tema_del_foro(request, pk)
    form = MensajeForoForm(request.POST or None, instance=MensajeForo(tema=tema, autor=request.user))
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Se publicó tu mensaje.')
        return redirect('foro_tema', pk=tema.pk)
    return render(request, 'cursos/foro_tema.html', {
        'tema': tema,
        'curso': tema.curso,
        'mensajes': tema.mensajes.select_related('autor'),
        'form': form,
        'volver': direccion_del_foro(request.user, tema.curso),
    })


@profesor_required
@require_POST
def foro_tema_eliminar_view(request, pk):
    tema = get_object_or_404(TemaForo.objects.select_related('curso'), pk=pk, curso__profesor=request.user,
                             curso__activo=True)
    tema.delete()
    messages.success(request, f'Se eliminó el tema «{tema.titulo}» con todos sus mensajes.')
    return redirect(direccion_del_foro(request.user, tema.curso))


@profesor_required
@require_POST
def foro_mensaje_eliminar_view(request, pk):
    mensaje = get_object_or_404(MensajeForo.objects.select_related('tema'), pk=pk,
                                tema__curso__profesor=request.user, tema__curso__activo=True)
    if mensaje == mensaje.tema.mensajes.first():
        messages.error(request, 'El primer mensaje abre el tema. Para quitarlo, elimine el tema completo.')
    else:
        mensaje.delete()
        messages.success(request, 'Se eliminó el mensaje.')
    return redirect('foro_tema', pk=mensaje.tema_id)
