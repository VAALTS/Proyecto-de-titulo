from django.contrib import admin

from .models import Actividad, Calificacion


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'clase', 'tipo', 'ponderacion', 'fecha_limite', 'visible')
    list_filter = ('tipo', 'visible', 'clase__modulo__curso')


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ('inscripcion', 'actividad', 'nota', 'fecha_registro')
    list_filter = ('actividad__clase__modulo__curso',)
