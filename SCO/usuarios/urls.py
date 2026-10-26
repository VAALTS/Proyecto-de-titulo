from django.urls import path
from . import views

urlpatterns = [
    # Inicio de sesión
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.perfil_view, name='perfil'),

    # Inicio de profesor y alumno
    path('profesor/', views.profesor_inicio_view, name='profesor_inicio'),
    path('alumno/', views.alumno_inicio_view, name='alumno_inicio'),

    # Panel del administrador
    path('panel/', views.admin_menu_view, name='admin_menu'),
    path('panel/alumnos/', views.gestion_alumnos_view, name='gestion_alumnos'),
    path('panel/alumnos/registrar/', views.alumno_registrar_view, name='alumno_registrar'),
    path('panel/alumnos/<int:pk>/editar/', views.alumno_editar_view, name='alumno_editar'),
    path('panel/alumnos/<int:pk>/estado/', views.alumno_estado_view, name='alumno_estado'),
    path('panel/alumnos/<int:pk>/reenviar-clave/', views.alumno_reenviar_clave_view, name='alumno_reenviar_clave'),
    path('panel/profesores/', views.gestion_profesores_view, name='gestion_profesores'),
    path('panel/cursos/', views.gestion_cursos_view, name='gestion_cursos'),
]