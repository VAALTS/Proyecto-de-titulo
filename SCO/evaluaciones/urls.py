from django.urls import path

from . import views

urlpatterns = [
    # Actividades y calificaciones del profesor (RF-11)
    path('profesor/evaluaciones/', views.profesor_evaluaciones_view, name='profesor_evaluaciones'),
    path('profesor/cursos/<int:pk>/actividades/crear/', views.actividad_crear_view, name='actividad_crear'),
    path('profesor/actividades/<int:pk>/editar/', views.actividad_editar_view, name='actividad_editar'),
    path('profesor/actividades/<int:pk>/visibilidad/', views.actividad_visibilidad_view,
         name='actividad_visibilidad'),
    path('profesor/actividades/<int:pk>/eliminar/', views.actividad_eliminar_view, name='actividad_eliminar'),
    path('profesor/actividades/<int:pk>/calificar/', views.actividad_calificar_view, name='actividad_calificar'),
]
