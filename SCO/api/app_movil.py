"""Publica la aplicación móvil (PWA) en /app/, en la misma dirección que la web y la API.

Así la app se puede instalar desde el navegador del celular (Android e iPhone) y llama a la API
sin problemas de CORS. Los archivos están en la carpeta `app_movil/` de la raíz del repositorio.
"""
from django.conf import settings
from django.views.static import serve


def app_movil(request, ruta=''):
    if not ruta or ruta.endswith('/'):
        ruta += 'index.html'
    respuesta = serve(request, ruta, document_root=settings.APP_MOVIL_DIR)
    if ruta.endswith(('index.html', 'sw.js', 'config.js')):
        # Que el celular siempre revise si hay una versión nueva de la app
        respuesta['Cache-Control'] = 'no-cache'
    return respuesta
