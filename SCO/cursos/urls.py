from django.urls import path

from . import views, views_profesor

urlpatterns = [
    # Menú y cursos del profesor (RF-09 y RF-10)
    path('profesor/', views_profesor.profesor_inicio_view, name='profesor_inicio'),
    path('profesor/cursos/', views_profesor.profesor_cursos_view, name='profesor_cursos'),
    path('profesor/cursos/<int:pk>/', views_profesor.profesor_curso_view, name='profesor_curso'),

    # Módulos y clases de un curso (RF-10)
    path('profesor/cursos/<int:pk>/modulos/crear/', views_profesor.modulo_crear_view, name='modulo_crear'),
    path('profesor/modulos/<int:pk>/editar/', views_profesor.modulo_editar_view, name='modulo_editar'),
    path('profesor/modulos/<int:pk>/eliminar/', views_profesor.modulo_eliminar_view, name='modulo_eliminar'),
    path('profesor/modulos/<int:pk>/mover/<str:direccion>/', views_profesor.modulo_mover_view,
         name='modulo_mover'),
    path('profesor/modulos/<int:pk>/clases/crear/', views_profesor.clase_crear_view, name='clase_crear'),
    path('profesor/clases/<int:pk>/editar/', views_profesor.clase_editar_view, name='clase_editar'),
    path('profesor/clases/<int:pk>/eliminar/', views_profesor.clase_eliminar_view, name='clase_eliminar'),

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
