from django.conf import settings
from django.db import models


class SolicitudContacto(models.Model):
    """Solicitud de ayuda enviada desde la aplicación móvil a los administradores (RF-09 de la app).

    Se permite una por usuario al día, para evitar el spam.
    """

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='solicitudes_contacto')
    mensaje = models.TextField(max_length=2000)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'solicitud de contacto'
        verbose_name_plural = 'solicitudes de contacto'
        ordering = ['-fecha_envio']

    def __str__(self):
        return f'{self.usuario} ({self.fecha_envio:%d/%m/%Y %H:%M})'
