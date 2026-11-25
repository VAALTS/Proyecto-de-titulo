from django.contrib import admin

from .models import Dispositivo, SolicitudContacto


@admin.register(SolicitudContacto)
class SolicitudContactoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha_envio')
    search_fields = ('usuario__email', 'mensaje')
    readonly_fields = ('usuario', 'mensaje', 'fecha_envio')


@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha_registro')
    search_fields = ('usuario__email',)
    readonly_fields = ('usuario', 'endpoint', 'p256dh', 'auth', 'fecha_registro')
