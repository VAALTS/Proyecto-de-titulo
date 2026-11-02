from django.contrib import admin

from .models import Actividad, Alternativa, Calificacion, Entrega, Pregunta, Respuesta


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'clase', 'tipo', 'ponderacion', 'fecha_limite', 'visible')
    list_filter = ('tipo', 'visible', 'clase__modulo__curso')


class AlternativaInline(admin.TabularInline):
    model = Alternativa
    extra = 0


@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ('enunciado', 'actividad', 'tipo', 'puntaje', 'orden')
    list_filter = ('tipo',)
    inlines = [AlternativaInline]


class RespuestaInline(admin.TabularInline):
    model = Respuesta
    extra = 0


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = ('inscripcion', 'actividad', 'fecha_entrega')
    list_filter = ('actividad__clase__modulo__curso',)
    inlines = [RespuestaInline]


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ('inscripcion', 'actividad', 'nota', 'fecha_registro')
    list_filter = ('actividad__clase__modulo__curso',)
