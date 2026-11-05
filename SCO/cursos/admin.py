from django.contrib import admin

from .models import BloqueHorario, Clase, Curso, Inscripcion, MensajeForo, Modulo, TemaForo


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


@admin.register(BloqueHorario)
class BloqueHorarioAdmin(admin.ModelAdmin):
    list_display = ('curso', 'dia_semana', 'hora_inicio', 'hora_fin', 'sala')
    list_filter = ('dia_semana', 'curso')


class MensajeForoInline(admin.TabularInline):
    model = MensajeForo
    extra = 0


@admin.register(TemaForo)
class TemaForoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'curso', 'autor', 'fecha_creacion')
    list_filter = ('curso',)
    inlines = [MensajeForoInline]
