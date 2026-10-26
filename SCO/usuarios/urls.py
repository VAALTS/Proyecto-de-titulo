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
    path('panel/profesores/', views.gestion_profesores_view, name='gestion_profesores'),
    path('panel/cursos/', views.gestion_cursos_view, name='gestion_cursos'),
]