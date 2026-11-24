from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Servicios JSON que usa la aplicación móvil
    path('api/app/', include('api.urls')),
    path('', include('usuarios.urls')),
    path('', include('cursos.urls')),
    path('', include('evaluaciones.urls')),
]
