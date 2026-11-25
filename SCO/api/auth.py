"""Autenticación por token y CORS para la aplicación móvil.

La app no usa la cookie de sesión de la web: tras iniciar sesión recibe un token firmado
que envía en cada petición con el encabezado `Authorization: Bearer <token>`.
El token incluye una huella de la contraseña, así que cambiarla invalida los tokens anteriores.
"""
import json
from functools import wraps

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt

from usuarios.models import Usuario

SAL_TOKEN = 'api.app-movil.token'
DURACION_TOKEN = 60 * 60 * 24 * 7  # 7 días


def crear_token(usuario, rol=None):
    """Token del usuario con el perfil con que entra (alumno o profesor, si tiene los dos)."""
    return signing.dumps({'id': usuario.pk, 'h': usuario.get_session_auth_hash()[:16], 'r': rol or usuario.rol},
                         salt=SAL_TOKEN)


def usuario_del_token(token):
    try:
        datos = signing.loads(token, salt=SAL_TOKEN, max_age=DURACION_TOKEN)
    except signing.BadSignature:
        return None
    usuario = Usuario.objects.filter(pk=datos.get('id'), is_active=True).first()
    if usuario is None or not constant_time_compare(usuario.get_session_auth_hash()[:16], datos.get('h', '')):
        return None
    rol = datos.get('r', usuario.rol)
    if rol not in usuario.roles():
        return None
    # Perfil activo en la app. Solo cambia el objeto en memoria (las reglas de permisos de la web leen
    # `usuario.rol`); este objeto nunca se guarda con save(), así que el rol de la base no cambia.
    usuario.rol_guardado = usuario.rol
    usuario.rol = rol
    return usuario


def error(mensaje, status=400, **extra):
    return JsonResponse(dict({'error': mensaje}, **extra), status=status)


def leer_json(request):
    try:
        return json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return {}


def origenes_permitidos():
    """Direcciones desde las que se puede usar la API (variable APP_ORIGINS del .env, separadas por coma)."""
    return getattr(settings, 'APP_ORIGINS', [])


def agregar_cors(request, response):
    origen = request.headers.get('Origin')
    permitidos = origenes_permitidos()
    if origen and ('*' in permitidos or origen in permitidos):
        response['Access-Control-Allow-Origin'] = origen
        response['Vary'] = 'Origin'
        response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Max-Age'] = '86400'
    return response


def endpoint(metodos, roles=None, publico=False):
    """Vista JSON de la API: CORS, métodos permitidos y, salvo que sea pública, token válido y rol."""

    def decorador(vista):
        @csrf_exempt
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if request.method == 'OPTIONS':
                return agregar_cors(request, HttpResponse(status=204))
            if request.method not in metodos:
                return agregar_cors(request, error('Método no permitido', 405))
            if not publico:
                encabezado = request.headers.get('Authorization', '')
                usuario = usuario_del_token(encabezado[7:]) if encabezado.startswith('Bearer ') else None
                if usuario is None:
                    return agregar_cors(request, error('Tu sesión expiró. Vuelve a iniciar sesión.', 401))
                if roles and usuario.rol not in roles:
                    return agregar_cors(request, error('No tienes permiso para esta acción.', 403))
                request.usuario_api = usuario
            respuesta = vista(request, *args, **kwargs)
            if isinstance(respuesta, dict):
                respuesta = JsonResponse(respuesta)
            return agregar_cors(request, respuesta)

        return envoltura

    return decorador
