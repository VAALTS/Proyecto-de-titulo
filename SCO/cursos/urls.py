from django.urls import path

from . import views, views_profesor

urlpatterns = [
    # Menú y cursos del profesor (RF-09 y RF-10)
    path('profesor/', views_profesor.profesor_inicio_view, name='profesor_inicio'),
    path('profesor/cursos/', views_profesor.profesor_cursos_view, name='profesor_cursos'),

    # Gestión de cursos del administrador (RF-06)
    path('panel/cursos/', views.gestion_cursos_view, name='gestion_cursos'),
    path('panel/cursos/crear/', views.curso_crear_view, name='curso_crear'),
    path('panel/cursos/<int:pk>/', views.curso_detalle_view, name='curso_detalle'),
    path('panel/cursos/<int:pk>/editar/', views.curso_editar_view, name='curso_editar'),
    path('panel/cursos/<int:pk>/eliminar/', views.curso_eliminar_view, name='curso_eliminar'),
    path('panel/cursos/<int:pk>/restaurar/', views.curso_restaurar_view, name='curso_restaurar'),

    # Asignación de alumnos a cursos (RF-07)
    path('panel/cursos/<int:pk>/inscribir/', views.curso_inscribir_view, name='curso_inscribir'),
    path('panel/cursos/<int:pk>/inscripciones/<int:inscripcion_pk>/retirar/', views.curso_retirar_view,
         name='curso_retirar'),
]
