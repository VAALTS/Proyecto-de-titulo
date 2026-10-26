"""Contraseñas temporales de las cuentas que crea el administrador (RF-04 y RF-05)."""
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import get_random_string

# Sin caracteres que se confunden al leerlos (0/O, 1/l/I)
CARACTERES_CLAVE = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generar_clave_temporal():
    return get_random_string(10, CARACTERES_CLAVE)


@transaction.atomic
def asignar_clave_temporal(usuario, request):
    """Guarda una contraseña temporal nueva y la envía al correo del usuario.

    Si el correo no se puede enviar, la excepción revierte también el guardado,
    así no queda una cuenta con una contraseña que nadie conoce.
    """
    clave = generar_clave_temporal()
    usuario.set_password(clave)
    usuario.debe_cambiar_contrasena = True
    usuario.save()

    contexto = {'usuario': usuario, 'clave': clave, 'url_login': request.build_absolute_uri(reverse('login'))}
    send_mail(
        subject='Tu cuenta en Adapt Academy',
        message=render_to_string('correos/clave_temporal.txt', contexto),
        from_email=None,
        recipient_list=[usuario.email],
    )
