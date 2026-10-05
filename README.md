# Adapt Academy Web

Plataforma web de capacitaciones online con roles de administrador, profesor y alumno.
Construida con Django 5.2, Bootstrap 5 y MySQL.

## Puesta en marcha

Requisitos: Python 3.12 y MySQL 8.0 con el servicio en ejecución (`net start MySQL80` desde una terminal
de administrador si no está configurado para iniciar con Windows).

1. Crear el entorno virtual e instalar las dependencias (desde la raíz del repositorio):

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copiar `.env.example` como `.env`, generar una `SECRET_KEY` propia (el comando está en el mismo archivo)
   y escribir en `DB_PASSWORD` la contraseña del usuario `root` de MySQL.

3. Crear en MySQL una base de datos vacía llamada `adapt_academy`, por ejemplo desde MySQL Workbench:

   ```sql
   CREATE DATABASE adapt_academy CHARACTER SET utf8mb4;
   ```

4. Crear las tablas y la cuenta de administrador:

   ```
   cd SCO
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. Levantar el servidor con `python manage.py runserver` e ingresar en http://127.0.0.1:8000/ con el correo del administrador.

## Pruebas

```
cd SCO
python manage.py test
```

## Estructura

- `SCO/Main/`: configuración del proyecto Django.
- `SCO/usuarios/`: modelo de usuario (correo como identificador y campo `rol`), inicio de sesión y panel del administrador.
