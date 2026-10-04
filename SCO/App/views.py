from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST


def login_view(request):
    # Si ya inició sesión, no tiene sentido mostrar el login
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

    return render(request, 'login.html')


@login_required
def home_view(request):
    return render(request, 'home.html')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
