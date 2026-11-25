"""Genera un par de claves VAPID para las notificaciones push.

Uso: python manage.py generar_claves_push
Copia las dos líneas que imprime en las variables del hosting (y en el .env para probar en el computador).
Se generan una sola vez: si se cambian, los teléfonos tienen que volver a activar las notificaciones.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Genera las claves VAPID para las notificaciones push de la aplicación móvil.'

    def handle(self, *args, **options):
        clave = ec.generate_private_key(ec.SECP256R1())
        privada = clave.private_numbers().private_value.to_bytes(32, 'big')
        publica = clave.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
        self.stdout.write(f'VAPID_PUBLIC_KEY={b64url(publica)}')
        self.stdout.write(f'VAPID_PRIVATE_KEY={b64url(privada)}')
