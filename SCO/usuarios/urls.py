from django.urls import path
from . import views
from .models import Rol

urlpatterns = [
    # Inicio de sesión
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.perfil_view, name='perfil'),

    # Inicio del alumno (el del profesor está en cursos/urls.py)
    path('alumno/', views.alumno_inicio_view, name='alumno_inicio'),

    # Panel del administrador
    path('panel/', views.admin_menu_view, name='admin_menu'),
]

# Gestión de alumnos y profesores: mismas vistas, cambia el rol (RF-04 y RF-05)
for plural, singular, rol in [('alumnos', 'alumno', Rol.ALUMNO), ('profesores', 'profesor', Rol.PROFESOR)]:
    urlpatterns += [
        path(f'panel/{plural}/', views.gestion_cuentas_view, {'rol': rol}, name=f'gestion_{plural}'),
        path(f'panel/{plural}/registrar/', views.cuenta_registrar_view, {'rol': rol}, name=f'{singular}_registrar'),
        path(f'panel/{plural}/<int:pk>/editar/', views.cuenta_editar_view, {'rol': rol},
             name=f'{singular}_editar'),
        path(f'panel/{plural}/<int:pk>/estado/', views.cuenta_estado_view, {'rol': rol},
             name=f'{singular}_estado'),
        path(f'panel/{plural}/<int:pk>/reenviar-clave/', views.cuenta_reenviar_clave_view, {'rol': rol},
             name=f'{singular}_reenviar_clave'),
    ]
