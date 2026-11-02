from django.urls import path

from . import views, views_alumno

urlpatterns = [
    # Actividades y entregas del alumno (RF-16)
    path('alumno/actividades/<int:pk>/', views_alumno.alumno_actividad_view, name='alumno_actividad'),
    # Descarga protegida: la usan el alumno que entregó y el profesor del curso
    path('entregas/<int:pk>/descargar/', views.entrega_descargar_view, name='entrega_descargar'),

    # Actividades y calificaciones del profesor (RF-11)
    path('profesor/evaluaciones/', views.profesor_evaluaciones_view, name='profesor_evaluaciones'),
    path('profesor/cursos/<int:pk>/actividades/crear/', views.actividad_crear_view, name='actividad_crear'),
    path('profesor/actividades/<int:pk>/editar/', views.actividad_editar_view, name='actividad_editar'),
    path('profesor/actividades/<int:pk>/visibilidad/', views.actividad_visibilidad_view,
         name='actividad_visibilidad'),
    path('profesor/actividades/<int:pk>/eliminar/', views.actividad_eliminar_view, name='actividad_eliminar'),
    path('profesor/actividades/<int:pk>/calificar/', views.actividad_calificar_view, name='actividad_calificar'),

    # Formularios en línea: preguntas de una actividad
    path('profesor/actividades/<int:pk>/formulario/', views.actividad_formulario_view, name='actividad_formulario'),
    path('profesor/actividades/<int:pk>/preguntas/crear/', views.pregunta_crear_view, name='pregunta_crear'),
    path('profesor/preguntas/<int:pk>/editar/', views.pregunta_editar_view, name='pregunta_editar'),
    path('profesor/preguntas/<int:pk>/eliminar/', views.pregunta_eliminar_view, name='pregunta_eliminar'),
    path('profesor/preguntas/<int:pk>/mover/<str:direccion>/', views.pregunta_mover_view, name='pregunta_mover'),
]
