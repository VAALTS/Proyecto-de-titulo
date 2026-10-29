from django.contrib import admin

from .models import Curso, Inscripcion


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'profesor', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'profesor__primer_nombre', 'profesor__apellido_paterno')


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('alumno', 'curso', 'fecha_inscripcion', 'activa')
    list_filter = ('activa', 'curso')
