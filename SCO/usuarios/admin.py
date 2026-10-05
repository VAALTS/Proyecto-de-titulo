from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ('email',)
    list_display = ('email', 'primer_nombre', 'apellido_paterno', 'rol', 'is_active')
    list_filter = ('rol', 'is_active')
    search_fields = ('email', 'rut', 'primer_nombre', 'apellido_paterno')
    readonly_fields = ('last_login', 'fecha_registro')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Datos personales', {
            'fields': ('rut', 'primer_nombre', 'segundo_nombre', 'apellido_paterno', 'apellido_materno'),
        }),
        ('Permisos', {'fields': ('rol', 'is_active', 'is_staff', 'is_superuser')}),
        ('Fechas', {'fields': ('last_login', 'fecha_registro')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'rut', 'primer_nombre', 'apellido_paterno', 'rol',
                'usable_password', 'password1', 'password2',
            ),
        }),
    )
