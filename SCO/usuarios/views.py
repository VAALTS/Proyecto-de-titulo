from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import CambioContrasenaForm, LoginForm
from .models import Rol

INICIO_POR_ROL = {
    Rol.ADMINISTRADOR: 'admin_menu',
    Rol.PROFESOR: 'profesor_inicio',
    Rol.ALUMNO: 'alumno_inicio',
}


def tiene_rol(rol):
    """Solo deja pasar a usuarios con ese rol; al resto lo manda al login."""
    return user_passes_test(lambda u: u.is_authenticated and u.rol == rol, login_url='login')


admin_required = tiene_rol(Rol.ADMINISTRADOR)


# ---------- Inicio de sesión ----------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.usuario)
        siguiente = request.POST.get('next') or request.GET.get('next')
        if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()},
                                                        require_https=request.is_secure()):
            return redirect(siguiente)
        return redirect('home')

    return render(request, 'inicio_de_sesion/login.html', {'form': form})


@login_required
def home_view(request):
    # Cada rol tiene su propia página de inicio
    return redirect(INICIO_POR_ROL[request.user.rol])


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


# ---------- Perfil (cualquier rol) ----------

@login_required
def perfil_view(request):
    form = CambioContrasenaForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        # Sin esto, cambiar la contraseña cerraría la sesión actual
        update_session_auth_hash(request, form.user)
        messages.success(request, 'Tu contraseña se actualizó correctamente.')
        return redirect('perfil')

    return render(request, 'perfil/perfil.html', {'form': form})


# ---------- Inicio de profesor y alumno (sus menús llegan en las fases 3 y 4) ----------

@tiene_rol(Rol.PROFESOR)
def profesor_inicio_view(request):
    return render(request, 'inicio_de_sesion/home.html')


@tiene_rol(Rol.ALUMNO)
def alumno_inicio_view(request):
    return render(request, 'inicio_de_sesion/home.html')


# ---------- Panel del administrador ----------

@admin_required
def admin_menu_view(request):
    return render(request, 'administrador/menu.html')


@admin_required
def gestion_alumnos_view(request):
    return render(request, 'administrador/alumnos.html')


@admin_required
def gestion_profesores_view(request):
    return render(request, 'administrador/profesores.html')


@admin_required
def gestion_cursos_view(request):
    return render(request, 'administrador/cursos.html')
