"""Avisos de la aplicación móvil: quedan en la bandeja de la app (la campanita) y llegan como push al teléfono.

Funcionan con las claves VAPID de las variables VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY
(se generan con `python manage.py generar_claves_push`). Sin ellas, no se envía nada.
"""
import json
import logging
import threading

from django.conf import settings
from django.db import connection, transaction
from pywebpush import WebPushException, webpush

from .models import Dispositivo, Notificacion

logger = logging.getLogger(__name__)


def push_activo():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def enviar(usuarios_ids, titulo, cuerpo, url='/app/', etiqueta=None):
    """Envía la notificación a todos los dispositivos de esos usuarios. Devuelve cuántas se entregaron."""
    if not push_activo() or not usuarios_ids:
        return 0
    mensaje = json.dumps({'title': titulo, 'body': cuerpo, 'url': url, 'tag': etiqueta})
    entregadas = 0
    for dispositivo in Dispositivo.objects.filter(usuario_id__in=set(usuarios_ids)):
        try:
            webpush(
                subscription_info={'endpoint': dispositivo.endpoint,
                                   'keys': {'p256dh': dispositivo.p256dh, 'auth': dispositivo.auth}},
                data=mensaje,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{settings.VAPID_EMAIL}'},
                ttl=6 * 60 * 60,
                timeout=10,
            )
            entregadas += 1
        except WebPushException as error:
            # 404 o 410: el teléfono desinstaló la app o quitó el permiso; la suscripción ya no sirve
            if error.response is not None and error.response.status_code in (404, 410):
                dispositivo.delete()
            else:
                logger.warning('No se pudo enviar la notificación push: %s', error)
        except Exception:  # Un teléfono con problemas no debe impedir avisar a los demás
            logger.exception('Error inesperado al enviar una notificación push')
    return entregadas


def guardar_en_bandeja(usuarios_ids, titulo, cuerpo):
    """Deja el aviso en la bandeja de la app de cada usuario (se ve aunque el teléfono no reciba push)."""
    Notificacion.objects.bulk_create(Notificacion(usuario_id=usuario_id, titulo=titulo[:150], cuerpo=cuerpo[:300])
                                     for usuario_id in set(usuarios_ids))


def notificar(usuarios_ids, titulo, cuerpo, url='/app/', etiqueta=None):
    """Guarda el aviso en la bandeja y lo envía al teléfono en segundo plano, sin hacer esperar a quien lo causó."""
    ids = list(set(usuarios_ids))
    if not ids:
        return
    guardar_en_bandeja(ids, titulo, cuerpo)
    if not push_activo():
        return

    def tarea():
        try:
            enviar(ids, titulo, cuerpo, url, etiqueta)
        finally:
            # Este hilo abrió su propia conexión a la base: se cierra al terminar
            if threading.current_thread() is not threading.main_thread():
                connection.close()

    transaction.on_commit(lambda: threading.Thread(target=tarea, daemon=True).start())
