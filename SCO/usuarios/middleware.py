from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import add_never_cache_headers


class SinCacheAutenticadoMiddleware:
    """Evita que el navegador guarde páginas privadas, así el botón "atrás"
    no las muestra después de cerrar sesión (RF-02)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            add_never_cache_headers(response)
        return response


class CambioContrasenaObligatorioMiddleware:
    """Mientras el usuario tenga una contraseña temporal, solo puede ir a su perfil
    a cambiarla o cerrar sesión (RF-04)."""

    RUTAS_PERMITIDAS = ('perfil', 'logout')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and request.user.debe_cambiar_contrasena
                and request.path not in [reverse(ruta) for ruta in self.RUTAS_PERMITIDAS]):
            return redirect('perfil')
        return self.get_response(request)
