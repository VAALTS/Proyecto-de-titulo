from django.urls import path

from . import views

# Todas bajo /api/app/ (ver Main/urls.py)
urlpatterns = [
    path('login/', views.login, name='api_login'),
    path('recuperar/', views.recuperar, name='api_recuperar'),
    path('datos/', views.datos, name='api_datos'),
    path('material/<int:pk>/archivo/', views.material_archivo, name='api_material_archivo'),
    path('material/<int:pk>/visibilidad/', views.material_visibilidad, name='api_material_visibilidad'),
    path('material/<int:pk>/', views.material_eliminar, name='api_material_eliminar'),
    path('foro/<int:pk>/mensajes/', views.foro_mensaje, name='api_foro_mensaje'),
    path('cursos/<int:pk>/notas/', views.guardar_notas, name='api_guardar_notas'),
    path('contacto/', views.contacto, name='api_contacto'),
    path('rol/', views.cambiar_rol, name='api_cambiar_rol'),
    path('dispositivo/', views.dispositivo, name='api_dispositivo'),
    path('cursos/<int:pk>/material/', views.crear_material, name='api_crear_material'),
    path('cursos/<int:pk>/foros/', views.crear_foro, name='api_crear_foro'),
    path('cursos/<int:pk>/encuestas/', views.crear_encuesta, name='api_crear_encuesta'),
    path('foro/<int:pk>/', views.eliminar_foro, name='api_eliminar_foro'),
    path('encuesta/<int:pk>/visibilidad/', views.encuesta_visibilidad, name='api_encuesta_visibilidad'),
    path('encuesta/<int:pk>/votar/', views.votar_encuesta, name='api_votar_encuesta'),
    path('encuesta/<int:pk>/', views.eliminar_encuesta, name='api_eliminar_encuesta'),
]
