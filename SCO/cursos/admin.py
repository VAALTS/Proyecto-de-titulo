from django.contrib import admin

from .models import Clase, Curso, Inscripcion, Modulo


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'profesor', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'profesor__primer_nombre', 'profesor__apellido_paterno')


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'curso', 'fecha_inscripcion', 'activa')
    list_filter = ('activa', 'curso')


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'curso', 'orden')
    list_filter = ('curso',)


@admin.register(Clase)
class ClaseAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'modulo', 'fecha', 'hora_inicio', 'hora_fin')
    list_filter = ('modulo__curso',)
