from django.contrib import admin

from .models import SolicitudContacto


@admin.register(SolicitudContacto)
class SolicitudContactoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha_envio')
    search_fields = ('usuario__email', 'mensaje')
    readonly_fields = ('usuario', 'mensaje', 'fecha_envio')
