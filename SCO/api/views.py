"""API JSON para la aplicación móvil de Adapt Academy.

Usa los mismos modelos, reglas y credenciales que la plataforma web: un usuario entra a la app
con el mismo correo y contraseña, y lo que se registra en un lado se ve de inmediato en el otro.
"""
from datetime import datetime, time

from django import forms
from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone

from cursos.models import BloqueHorario, Curso, Inscripcion, Material, MensajeForo, TemaForo
from cursos.views_alumno import cursos_del_alumno
from cursos.views_foro import puede_usar_foro
from cursos.views_profesor import puede_descargar
from evaluaciones.calculos import calificaciones_del_alumno, resumen_del_curso
from evaluaciones.forms import NotaField
from evaluaciones.models import Actividad, Calificacion, Entrega
from notificaciones.models import SolicitudContacto
from usuarios.cuentas import asignar_clave_temporal
from usuarios.forms import LoginForm
from usuarios.models import Rol, Usuario

from .auth import crear_token, endpoint, error, leer_json

MINUTOS_ENTRE_RECUPERACIONES = 15


# ---------- utilidades ----------

def hhmm(hora):
    return hora.strftime('%H:%M')


def nota_json(nota):
    return float(nota) if nota is not None else None


def tamano_legible(archivo):
    try:
        bytes_ = archivo.size
    except (FileNotFoundError, OSError, ValueError):
        return ''
    if bytes_ > 1024 * 1024:
        return f'{bytes_ / 1024 / 1024:.1f} MB'.replace('.', ',')
    return f'{max(1, round(bytes_ / 1024))} KB'


def datos_usuario(usuario):
    return {
        'id': usuario.pk,
        'email': usuario.email,
        'nombre': usuario.get_short_name(),
        'nombre_completo': usuario.get_full_name(),
        'rut': usuario.rut or '',
        'rol': usuario.rol,
        'fecha_registro': usuario.fecha_registro.date().isoformat(),
    }


def datos_curso(curso, bloques, alumnos=None, asistencia=None):
    return {
        'id': curso.pk,
        'nombre': curso.nombre,
        'descripcion': curso.descripcion,
        'profesor': curso.profesor.get_short_name(),
        'profesor_email': curso.profesor.email,
        'bloques': [{'dia': b.dia_semana, 'inicio': hhmm(b.hora_inicio), 'fin': hhmm(b.hora_fin), 'sala': b.sala}
                    for b in bloques],
        'alumnos': alumnos,
        'asistencia': asistencia,
    }


def materiales_del_curso(request, curso, es_profesor):
    """Material de todas las clases del curso, en una sola lista (las carpetas tienen un nivel)."""
    materiales = list(Material.objects.filter(clase__modulo__curso=curso)
                      .select_related('clase__modulo', 'carpeta').order_by('clase__fecha', 'titulo'))
    if not es_profesor:
        materiales = [m for m in materiales if m.visible_para_alumnos()]
        con_contenido = {m.carpeta_id for m in materiales if m.carpeta_id}
        # Una carpeta sin nada visible no le sirve al alumno (igual que en la web)
        materiales = [m for m in materiales if m.tipo != Material.Tipo.CARPETA or m.pk in con_contenido]
    salida = []
    for m in materiales:
        item = {
            'id': f'm{m.pk}', 'pk': m.pk, 'tipo': m.tipo, 'titulo': m.titulo, 'visible': m.visible,
            'carpeta': f'm{m.carpeta_id}' if m.carpeta_id else None,
            'clase': m.clase.titulo, 'modulo': m.clase.modulo.nombre,
        }
        if m.tipo == Material.Tipo.ARCHIVO and m.archivo:
            item.update(archivo_nombre=m.nombre_archivo, tamano=tamano_legible(m.archivo),
                        descarga=reverse('api_material_archivo', args=[m.pk]))
        if m.tipo == Material.Tipo.ENLACE:
            item['url'] = m.url
        salida.append(item)
    return salida


def actividades_del_curso(request, curso, inscripcion, es_profesor):
    """Actividades y evaluaciones. Se responden en la web (RF-03 de la app), por eso llevan su dirección."""
    actividades = Actividad.objects.filter(clase__modulo__curso=curso).select_related('clase')
    if not es_profesor:
        actividades = actividades.filter(visible=True)
    entregadas = set()
    notas = {}
    if inscripcion:
        entregadas = set(Entrega.objects.filter(inscripcion=inscripcion).values_list('actividad_id', flat=True))
        notas = dict(Calificacion.objects.filter(inscripcion=inscripcion).values_list('actividad_id', 'nota'))
    salida = []
    for a in actividades.order_by('fecha_limite'):
        ruta = reverse('actividad_calificar', args=[a.pk]) if es_profesor else reverse('alumno_actividad', args=[a.pk])
        salida.append({
            'id': f'a{a.pk}', 'pk': a.pk, 'tipo': 'actividad', 'titulo': a.titulo, 'visible': a.visible,
            'forma': a.tipo, 'descripcion': a.descripcion, 'ponderacion': float(a.ponderacion),
            'fecha_limite': timezone.localtime(a.fecha_limite).isoformat(), 'abierta': a.abierta,
            'entregada': a.pk in entregadas, 'nota': nota_json(notas.get(a.pk)),
            'url_web': request.build_absolute_uri(ruta), 'carpeta': None,
        })
    return salida


def foros_del_curso(curso, usuario):
    salida = []
    for tema in curso.temas.select_related('autor').prefetch_related('mensajes__autor'):
        mensajes = list(tema.mensajes.all())
        primero = mensajes[0] if mensajes else None
        salida.append({
            'id': f'f{tema.pk}', 'pk': tema.pk, 'tipo': 'foro', 'titulo': tema.titulo, 'visible': True,
            'carpeta': None, 'autor': tema.autor.get_short_name(),
            'texto': primero.contenido if primero else '',
            'fecha': timezone.localtime(tema.fecha_creacion).isoformat(),
            'comentarios': [{
                'autor': m.autor.get_short_name(), 'texto': m.contenido,
                'fecha': timezone.localtime(m.fecha_creacion).isoformat(),
                'profesor': m.autor_id == curso.profesor_id, 'propio': m.autor_id == usuario.pk,
            } for m in mensajes[1:]],
        })
    return salida


def bloques_por_curso(cursos):
    bloques = {}
    for b in BloqueHorario.objects.filter(curso__in=cursos).order_by('dia_semana', 'hora_inicio'):
        bloques.setdefault(b.curso_id, []).append(b)
    return bloques


def porcentaje_asistencia(inscripcion):
    total = inscripcion.asistencias.count()
    if not total:
        return None
    return round(inscripcion.asistencias.filter(presente=True).count() * 100 / total)


# ---------- inicio de sesión ----------

@endpoint(['POST'], publico=True)
def login(request):
    """RF-01: mismas reglas que la web (bloqueo de 5 minutos tras 3 intentos fallidos)."""
    datos = leer_json(request)
    email = str(datos.get('email', '')).strip().lower()
    form = LoginForm(request, data={'email': email, 'password': str(datos.get('password', ''))})
    if not form.is_valid():
        cuenta = Usuario.objects.filter(email=email).first()
        if cuenta and cuenta.esta_bloqueado():
            segundos = max(1, int((cuenta.bloqueado_hasta - timezone.now()).total_seconds()))
            return error('Tu cuenta está bloqueada temporalmente.', 423, segundos=segundos)
        return error('Correo o contraseña incorrecta, inténtelo nuevamente', 401)

    usuario = form.usuario
    if usuario.rol == Rol.ADMINISTRADOR:
        return error('La aplicación es para profesores y alumnos. Los administradores usan la plataforma web.', 403)
    if usuario.debe_cambiar_contrasena:
        return error('Tienes una contraseña temporal. Ingresa primero a la plataforma web para cambiarla.', 403,
                     url_web=request.build_absolute_uri(reverse('login')))
    update_last_login(None, usuario)
    return {'token': crear_token(usuario), 'usuario': datos_usuario(usuario)}


@endpoint(['POST'], publico=True)
def recuperar(request):
    """Envía una contraseña temporal al correo, como cuando el administrador la reenvía (RF-04 de la web).

    La respuesta es la misma exista o no la cuenta, para no revelar qué correos están registrados.
    """
    email = str(leer_json(request).get('email', '')).strip().lower()
    respuesta = {'ok': True, 'mensaje': 'Si el correo está registrado, recibirás una contraseña temporal.'}
    usuario = Usuario.objects.filter(email=email, is_active=True).exclude(rol=Rol.ADMINISTRADOR).first()
    if usuario and cache.add(f'api-recuperar-{usuario.pk}', True, MINUTOS_ENTRE_RECUPERACIONES * 60):
        try:
            asignar_clave_temporal(usuario, request)
        except Exception:
            cache.delete(f'api-recuperar-{usuario.pk}')
            return error('No se pudo enviar el correo. Intenta más tarde.', 503)
    return respuesta


# ---------- datos de la app ----------

@endpoint(['GET'], roles=[Rol.ALUMNO, Rol.PROFESOR])
def datos(request):
    """Todo lo que la app muestra al entrar: cursos, horario, material, actividades, foros y notas."""
    usuario = request.usuario_api
    es_profesor = usuario.rol == Rol.PROFESOR
    salida = {'usuario': datos_usuario(usuario), 'web': request.build_absolute_uri('/'),
              'cursos': [], 'contenido': {}, 'notas': {}}

    if es_profesor:
        cursos = list(Curso.objects.activos().filter(profesor=usuario).select_related('profesor')
                      .annotate(inscritos=Count('inscripciones', filter=Q(inscripciones__activa=True))))
        bloques = bloques_por_curso(cursos)
        for curso in cursos:
            salida['cursos'].append(datos_curso(curso, bloques.get(curso.pk, []), alumnos=curso.inscritos))
            salida['contenido'][curso.pk] = (materiales_del_curso(request, curso, True)
                                             + actividades_del_curso(request, curso, None, True)
                                             + foros_del_curso(curso, usuario))
            inscripciones = curso.inscripciones.filter(activa=True).select_related('alumno').order_by(
                'alumno__apellido_paterno', 'alumno__primer_nombre')
            resumen = resumen_del_curso(curso, inscripciones)
            salida['notas'][curso.pk] = {
                'evaluaciones': [{'id': a.pk, 'nombre': a.titulo, 'ponderacion': float(a.ponderacion)}
                                 for a in resumen['actividades']],
                'alumnos': [{'id': f['inscripcion'].alumno_id, 'nombre': f['inscripcion'].alumno.get_short_name()}
                            for f in resumen['filas_notas']],
                'notas': {f['inscripcion'].alumno_id: {a.pk: nota_json(n) for a, n in
                                                       zip(resumen['actividades'], f['notas'])}
                          for f in resumen['filas_notas']},
            }
        return salida

    cursos = list(cursos_del_alumno(usuario))
    inscripciones = {i.curso_id: i for i in Inscripcion.objects.filter(alumno=usuario, activa=True,
                                                                       curso__in=cursos)}
    bloques = bloques_por_curso(cursos)
    for curso in cursos:
        inscripcion = inscripciones[curso.pk]
        salida['cursos'].append(datos_curso(curso, bloques.get(curso.pk, []),
                                            asistencia=porcentaje_asistencia(inscripcion)))
        salida['contenido'][curso.pk] = (materiales_del_curso(request, curso, False)
                                         + actividades_del_curso(request, curso, inscripcion, False)
                                         + foros_del_curso(curso, usuario))
    for resumen in calificaciones_del_alumno(usuario):
        salida['notas'][resumen['curso'].pk] = {
            'evaluaciones': [{'id': f['actividad'].pk, 'nombre': f['actividad'].titulo,
                              'ponderacion': float(f['actividad'].ponderacion)} for f in resumen['filas']],
            'alumnos': [{'id': usuario.pk, 'nombre': usuario.get_short_name()}],
            'notas': {usuario.pk: {f['actividad'].pk: nota_json(f['calificacion'].nota if f['calificacion'] else None)
                                   for f in resumen['filas']}},
            'promedio': nota_json(resumen['promedio']),
        }
    return salida


@endpoint(['GET'], roles=[Rol.ALUMNO, Rol.PROFESOR])
def material_archivo(request, pk):
    """Descarga de un archivo de material, con los mismos permisos que la web (404 a quien no puede verlo)."""
    material = Material.objects.select_related('clase__modulo__curso', 'carpeta').filter(
        pk=pk, tipo=Material.Tipo.ARCHIVO).first()
    if not material or not material.archivo or not puede_descargar(request.usuario_api, material):
        return error('Archivo no encontrado.', 404)
    try:
        return FileResponse(material.archivo.open('rb'), as_attachment=True, filename=material.nombre_archivo)
    except FileNotFoundError:
        return error('Archivo no encontrado.', 404)


# ---------- foro ----------

@endpoint(['POST'], roles=[Rol.ALUMNO, Rol.PROFESOR])
def foro_mensaje(request, pk):
    tema = TemaForo.objects.select_related('curso').filter(pk=pk).first()
    if not tema or not puede_usar_foro(request.usuario_api, tema.curso):
        return error('Tema no encontrado.', 404)
    contenido = str(leer_json(request).get('contenido', '')).strip()
    if not contenido:
        return error('Escribe un comentario.')
    if len(contenido) > 5000:
        return error('El comentario no puede superar los 5.000 caracteres.')
    mensaje = MensajeForo.objects.create(tema=tema, autor=request.usuario_api, contenido=contenido)
    return {'ok': True, 'id': mensaje.pk}


# ---------- profesor: material y notas ----------

def material_del_profesor(request, pk):
    return Material.objects.select_related('clase__modulo__curso').filter(
        pk=pk, clase__modulo__curso__profesor=request.usuario_api, clase__modulo__curso__activo=True).first()


@endpoint(['POST'], roles=[Rol.PROFESOR])
def material_visibilidad(request, pk):
    """RF-12: ocultar o mostrar un material a los alumnos."""
    material = material_del_profesor(request, pk)
    if not material:
        return error('Material no encontrado.', 404)
    datos_ = leer_json(request)
    material.visible = bool(datos_['visible']) if 'visible' in datos_ else not material.visible
    material.save(update_fields=['visible'])
    return {'ok': True, 'visible': material.visible}


@endpoint(['DELETE'], roles=[Rol.PROFESOR])
def material_eliminar(request, pk):
    """RF-12: eliminar un material. Una carpeta con contenido no se puede eliminar (igual que en la web)."""
    material = material_del_profesor(request, pk)
    if not material:
        return error('Material no encontrado.', 404)
    archivo = material.archivo
    try:
        material.delete()
    except ProtectedError:
        return error(f'La carpeta «{material.titulo}» tiene contenido. Elimina primero lo que contiene.', 409)
    if archivo:
        archivo.delete(save=False)
    return {'ok': True}


@endpoint(['POST'], roles=[Rol.PROFESOR])
def guardar_notas(request, pk):
    """Notas de una actividad: {"actividad": id, "notas": {"<id alumno>": "5,5" o null}}."""
    datos_ = leer_json(request)
    actividad = Actividad.objects.filter(pk=datos_.get('actividad'), clase__modulo__curso_id=pk,
                                         clase__modulo__curso__profesor=request.usuario_api,
                                         clase__modulo__curso__activo=True).first()
    if not actividad:
        return error('Evaluación no encontrada.', 404)
    inscripciones = {i.alumno_id: i for i in actividad.curso.inscripciones.filter(activa=True)}
    campo = NotaField()
    cambios = []
    for alumno_id, valor in (datos_.get('notas') or {}).items():
        inscripcion = inscripciones.get(int(alumno_id)) if str(alumno_id).isdigit() else None
        if inscripcion is None:
            return error('Uno de los alumnos no está inscrito en este curso.')
        try:
            nota = campo.clean(None if valor is None else str(valor))
        except forms.ValidationError:
            return error('Las notas deben estar entre 1,0 y 7,0, con un decimal.')
        cambios.append((inscripcion, nota))
    with transaction.atomic():
        for inscripcion, nota in cambios:
            if nota is None:
                Calificacion.objects.filter(actividad=actividad, inscripcion=inscripcion).delete()
            else:
                Calificacion.objects.update_or_create(actividad=actividad, inscripcion=inscripcion, defaults={
                    'nota': nota, 'registrada_por': request.usuario_api})
    return {'ok': True, 'guardadas': len(cambios)}


# ---------- contacto con administradores ----------

@endpoint(['POST'], roles=[Rol.ALUMNO, Rol.PROFESOR])
def contacto(request):
    """RF-09 de la app: una solicitud al día, que llega por correo a los administradores."""
    usuario = request.usuario_api
    inicio_del_dia = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    if usuario.solicitudes_contacto.filter(fecha_envio__gte=inicio_del_dia).exists():
        return error('Ya enviaste una solicitud hoy. Podrás enviar otra mañana.', 429)
    datos_ = leer_json(request)
    texto = str(datos_.get('mensaje', '')).strip()
    if not texto:
        return error('Describe brevemente el problema.')
    motivo = str(datos_.get('motivo', '')).strip()[:40]
    mensaje = f'[{motivo}] {texto}' if motivo else texto
    with transaction.atomic():
        SolicitudContacto.objects.create(usuario=usuario, mensaje=mensaje[:2000])
        administradores = list(Usuario.objects.filter(rol=Rol.ADMINISTRADOR, is_active=True)
                               .values_list('email', flat=True))
        if administradores:
            send_mail(
                subject=f'[App Adapt Academy] Solicitud de {usuario.get_short_name()}' + (f': {motivo}' if motivo else ''),
                message=f'{usuario.get_full_name()} ({usuario.email}, {usuario.get_rol_display()}) escribió desde la '
                        f'aplicación móvil:\n\n{texto}',
                from_email=None, recipient_list=administradores)
    return {'ok': True}
