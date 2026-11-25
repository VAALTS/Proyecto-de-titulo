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


class Dispositivo(models.Model):
    """Teléfono o navegador registrado para recibir notificaciones push (Web Push).

    Corresponde a la tabla Dispositivo del modelo de datos: el "token" es la suscripción del navegador.
    """

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dispositivos')
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'dispositivo'
        verbose_name_plural = 'dispositivos'

    def __str__(self):
        return f'{self.usuario} ({self.fecha_registro:%d/%m/%Y})'


class RecordatorioEnviado(models.Model):
    """Evita mandar dos veces el mismo recordatorio (RF-07 y RF-08 de la app)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recordatorios')
    clave = models.CharField(max_length=120)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'recordatorio enviado'
        verbose_name_plural = 'recordatorios enviados'
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'clave'], name='recordatorio_unico'),
        ]
