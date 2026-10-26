import math
from datetime import timedelta

from django import forms
from django.contrib.auth import authenticate
from django.utils import timezone

from .models import Usuario

INTENTOS_MAXIMOS = 3
MINUTOS_BLOQUEO = 5

MENSAJE_CREDENCIALES = 'Nombre de usuario o contraseña incorrecto, intente nuevamente'


class LoginForm(forms.Form):
    email = forms.EmailField(label='Correo electrónico')
    password = forms.CharField(label='Contraseña', strip=False, widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.usuario = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')
        if not email or not password:
            raise forms.ValidationError(MENSAJE_CREDENCIALES)

        cuenta = Usuario.objects.filter(email=email.strip().lower()).first()
        if cuenta and cuenta.esta_bloqueado():
            raise forms.ValidationError(self._mensaje_bloqueo(cuenta))

        usuario = authenticate(self.request, username=email, password=password)
        if usuario is None:
            if cuenta:
                self._registrar_fallo(cuenta)
                if cuenta.esta_bloqueado():
                    raise forms.ValidationError(self._mensaje_bloqueo(cuenta))
            raise forms.ValidationError(MENSAJE_CREDENCIALES)

        if usuario.intentos_fallidos or usuario.bloqueado_hasta:
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = None
            usuario.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
        self.usuario = usuario
        return self.cleaned_data

    def _registrar_fallo(self, cuenta):
        cuenta.intentos_fallidos += 1
        if cuenta.intentos_fallidos >= INTENTOS_MAXIMOS:
            cuenta.intentos_fallidos = 0
            cuenta.bloqueado_hasta = timezone.now() + timedelta(minutes=MINUTOS_BLOQUEO)
        cuenta.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

    @staticmethod
    def _mensaje_bloqueo(cuenta):
        minutos = math.ceil((cuenta.bloqueado_hasta - timezone.now()).total_seconds() / 60)
        unidad = 'minuto' if minutos == 1 else 'minutos'
        return (f'La cuenta está bloqueada temporalmente por {INTENTOS_MAXIMOS} intentos fallidos. '
                f'Intente nuevamente en {minutos} {unidad}.')
