# Publicar Adapt Academy en Railway

Un solo servicio publica la **web**, la **API** (`/api/app/`) y la **aplicación móvil** (`/app/`),
conectados a una base **MySQL** de Railway. El `Dockerfile` de la raíz indica cómo instalar y arrancar todo.

```
https://<tu-dominio>.up.railway.app/        → plataforma web
https://<tu-dominio>.up.railway.app/app/    → aplicación móvil (se instala desde el celular)
https://<tu-dominio>.up.railway.app/admin/  → administración de Django
```

## 1. Crear el proyecto

1. Entra a [railway.com](https://railway.com) con tu cuenta de GitHub.
2. **New Project → Deploy from GitHub repo** y elige `Proyecto-de-titulo`.
3. En el servicio creado, abre **Settings → Source** y elige la rama que se publicará (`api-app-movil` o `main`).

## 2. Agregar MySQL

En el proyecto: **+ Create → Database → MySQL**. Railway crea un servicio llamado `MySQL`.

## 3. Variables del servicio web

En el servicio web, abre **Variables → Raw Editor** y pega esto (cambia lo que está entre `< >`):

```
DEBUG=False
SECRET_KEY=<clave larga y aleatoria>
MYSQL_URL=${{MySQL.MYSQL_URL}}
DJANGO_SUPERUSER_EMAIL=<correo del administrador>
DJANGO_SUPERUSER_PASSWORD=<contraseña del administrador>
DJANGO_SUPERUSER_PRIMER_NOMBRE=Administrador
```

Para generar la `SECRET_KEY`, en tu computador ejecuta:

```
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**Contraseñas temporales.** Las cuentas usan sus correos reales y no se configura envío de correos:
cuando el administrador crea una cuenta o usa "Reenviar contraseña", el correo con la contraseña temporal
queda escrito en los registros de Railway (**Deployments → View logs → Deploy Logs**, buscar
`Contraseña temporal`). Railway bloquea el envío por SMTP (Gmail) en los planes Trial y Hobby.

## 4. Disco para los archivos subidos

En el servicio web: **+ Create → Volume** (o clic derecho → *Attach volume*), con la ruta de montaje `/proyecto/media`.
Ahí quedan el material de clases y las entregas; sin el volumen se borran en cada publicación.

## 5. Dirección pública

En el servicio web: **Settings → Networking → Generate Domain**. Railway entrega una dirección
`https://...up.railway.app`. Django la reconoce sola: no hay que agregarla a `ALLOWED_HOSTS`.

## 6. Publicar y revisar

Cada vez que subes cambios a la rama elegida, Railway vuelve a publicar solo. Al arrancar, el servidor:
1. aplica las migraciones;
2. crea el administrador con las variables `DJANGO_SUPERUSER_*` (solo la primera vez);
3. levanta la web con gunicorn.

Revisa los registros en **Deployments → View logs**. Luego entra a la web con el administrador
y registra profesores, alumnos y cursos como siempre.

## Instalar la app en los celulares

- **iPhone:** abre `https://<tu-dominio>/app/` en **Safari** → botón Compartir → **Agregar a pantalla de inicio**.
- **Android:** abre la misma dirección en **Chrome** → menú ⋮ → **Agregar a pantalla principal**, o instala el APK.

## Desarrollo en el computador

Nada cambia: el `.env` sigue funcionando con `DB_NAME`, `DB_USER`, etc. La app también se puede abrir en
`http://localhost:8000/app/` con `python SCO/manage.py runserver`.
