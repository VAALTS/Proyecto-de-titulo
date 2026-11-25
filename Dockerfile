# Imagen para publicar Adapt Academy (web, API y app móvil) en Railway u otro hosting con Docker.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Librerías del sistema que necesita mysqlclient para conectarse a MySQL
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /proyecto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Junta los CSS e imágenes en staticfiles/ (no necesita la base de datos)
RUN SECRET_KEY=solo-para-construir python SCO/manage.py collectstatic --noinput

# Al arrancar:
# 1. aplica las migraciones pendientes;
# 2. crea el administrador inicial si están definidas DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD
#    y DJANGO_SUPERUSER_PRIMER_NOMBRE (si ya existe, sigue de largo);
# 3. deja corriendo en segundo plano los recordatorios al teléfono (revisa cada 2 minutos);
# 4. levanta el servidor en el puerto que asigna Railway.
CMD python SCO/manage.py migrate --noinput \
    && (python SCO/manage.py createsuperuser --noinput 2>/dev/null || true) \
    && (python SCO/manage.py enviar_recordatorios --cada 120 &) \
    && gunicorn Main.wsgi --chdir SCO --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
