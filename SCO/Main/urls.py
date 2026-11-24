from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from api.app_movil import app_movil

urlpatterns = [
    path('admin/', admin.site.urls),
    # Servicios JSON que usa la aplicación móvil
    path('api/app/', include('api.urls')),
    # La aplicación móvil (PWA), para instalarla desde el celular
    path('app', RedirectView.as_view(url='/app/', permanent=False)),
    re_path(r'^app/(?P<ruta>.*)$', app_movil, name='app_movil'),
    path('', include('usuarios.urls')),
    path('', include('cursos.urls')),
    path('', include('evaluaciones.urls')),
]
