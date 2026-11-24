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
]
