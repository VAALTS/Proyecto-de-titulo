from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notificaciones'

    def ready(self):
        # Conecta los avisos push a los cambios en cursos, actividades, notas y foros
        from . import signals  # noqa: F401
