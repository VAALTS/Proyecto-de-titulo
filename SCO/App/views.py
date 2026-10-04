from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST


def es_admin(user):
    return user.is_active and user.is_staff


# Solo deja pasar a administradores; al resto lo manda al login
admin_required = user_passes_test(es_admin, login_url='login')


# ---------- Inicio de sesión ----------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'inicio_de_sesion/login.html')


@login_required
def home_view(request):
    # Los administradores van directo a su menú
    if es_admin(request.user):
        return redirect('admin_menu')
    return render(request, 'inicio_de_sesion/home.html')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


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
