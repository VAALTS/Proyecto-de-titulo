from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cursos.models import Curso, Inscripcion

from .cuentas import asignar_clave_temporal
from .forms import CambioContrasenaForm, CuentaForm, LoginForm
from .models import Rol, Usuario

MENSAJE_ERROR_CORREO = ('No se pudo enviar el correo con la contraseña temporal, así que no se guardó ningún cambio. '
                        'Revise la configuración de correo e intente nuevamente.')

INICIO_POR_ROL = {
    Rol.ADMINISTRADOR: 'admin_menu',
    Rol.PROFESOR: 'profesor_inicio',
    Rol.ALUMNO: 'alumno_inicio',
}


def tiene_rol(rol):
    """Solo deja pasar a usuarios con ese rol; al resto lo manda al login."""
    return user_passes_test(lambda u: u.is_authenticated and u.rol == rol, login_url='login')


admin_required = tiene_rol(Rol.ADMINISTRADOR)


# ---------- Inicio de sesión ----------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.usuario)
        siguiente = request.POST.get('next') or request.GET.get('next')
        if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()},
                                                        require_https=request.is_secure()):
            return redirect(siguiente)
        return redirect('home')

    return render(request, 'inicio_de_sesion/login.html', {'form': form})


@login_required
def home_view(request):
    # Cada rol tiene su propia página de inicio
    return redirect(INICIO_POR_ROL[request.user.rol])


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


# ---------- Perfil (cualquier rol) ----------

@login_required
def perfil_view(request):
    form = CambioContrasenaForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        # Sin esto, cambiar la contraseña cerraría la sesión actual
        update_session_auth_hash(request, form.user)
        messages.success(request, 'Tu contraseña se actualizó correctamente.')
        return redirect('perfil')

    return render(request, 'perfil/perfil.html', {'form': form})


# ---------- Inicio de profesor y alumno (sus menús llegan en las fases 3 y 4) ----------

@tiene_rol(Rol.PROFESOR)
def profesor_inicio_view(request):
    return render(request, 'inicio_de_sesion/home.html')


@tiene_rol(Rol.ALUMNO)
def alumno_inicio_view(request):
    return render(request, 'inicio_de_sesion/home.html')


# ---------- Panel del administrador ----------

@admin_required
def admin_menu_view(request):
    return render(request, 'administrador/menu.html')


# ---------- Gestión de alumnos y profesores (RF-04 y RF-05) ----------
# Las dos gestiones funcionan igual; cada vista recibe el rol desde urls.py.

GESTION_CUENTAS = {
    Rol.ALUMNO: {
        'titulo': 'Gestión de alumnos', 'singular': 'alumno', 'plural': 'alumnos',
        'icono': 'bi-people-fill', 'color': 'primary',
        # RF-04: los cursos se muestran en su perfil; la inscripción se hace en la página del curso (RF-07)
        'cursos': {'titulo': 'Capacitación inscrita', 'vacio': 'No está inscrito en ningún curso.',
                   'nota': 'Para inscribirlo o retirarlo, abra el curso en'},
        'urls': {'lista': 'gestion_alumnos', 'registrar': 'alumno_registrar', 'editar': 'alumno_editar',
                 'estado': 'alumno_estado', 'reenviar': 'alumno_reenviar_clave'},
    },
    Rol.PROFESOR: {
        'titulo': 'Gestión de profesores', 'singular': 'profesor', 'plural': 'profesores',
        'icono': 'bi-person-workspace', 'color': 'success',
        # RF-05: los cursos se muestran en su perfil; se asignan al editar el curso (RF-06)
        'cursos': {'titulo': 'Asignaturas que imparte', 'vacio': 'No tiene cursos a cargo.',
                   'nota': 'Para asignar o cambiar cursos, edite el curso en'},
        'urls': {'lista': 'gestion_profesores', 'registrar': 'profesor_registrar', 'editar': 'profesor_editar',
                 'estado': 'profesor_estado', 'reenviar': 'profesor_reenviar_clave'},
    },
}


def buscar_cuentas(rol, texto):
    """Cada palabra buscada debe aparecer en el nombre, los apellidos, el correo o el RUT."""
    cuentas = Usuario.objects.filter(rol=rol)
    for palabra in texto.split():
        cuentas = cuentas.filter(
            Q(primer_nombre__icontains=palabra) | Q(segundo_nombre__icontains=palabra)
            | Q(apellido_paterno__icontains=palabra) | Q(apellido_materno__icontains=palabra)
            | Q(email__icontains=palabra) | Q(rut__icontains=palabra.replace('.', ''))
        )
    return cuentas.order_by('apellido_paterno', 'apellido_materno', 'primer_nombre')


def pagina_cuentas(request, rol, form_registro=None, form_edicion=None, cuenta_editada=None):
    # Si un formulario vuelve con errores, la página se abre con su modal desplegado
    busqueda = (request.POST.get('q') or request.GET.get('q', '')).strip()
    cuentas = buscar_cuentas(rol, busqueda)
    if rol == Rol.PROFESOR:
        cuentas = cuentas.prefetch_related(
            Prefetch('cursos_a_cargo', queryset=Curso.objects.activos(), to_attr='cursos_activos'))
    else:
        inscripciones = Inscripcion.objects.filter(activa=True, curso__activo=True).select_related('curso')
        cuentas = list(cuentas.prefetch_related(
            Prefetch('inscripciones', queryset=inscripciones.order_by('curso__nombre'), to_attr='vigentes')))
        for cuenta in cuentas:
            cuenta.cursos_activos = [inscripcion.curso for inscripcion in cuenta.vigentes]
    return render(request, 'administrador/cuentas.html', {
        'gestion': GESTION_CUENTAS[rol],
        'cuentas': cuentas,
        'q': busqueda,
        'form_registro': form_registro or CuentaForm(auto_id='registro_%s'),
        'form_edicion': form_edicion or CuentaForm(auto_id='edicion_%s'),
        'cuenta_editada': cuenta_editada,
        'abrir_modal': 'modalRegistro' if form_registro else 'modalEdicion' if form_edicion else '',
    })


def volver_a_la_lista(request, rol):
    # Conserva la búsqueda que el administrador tenía en pantalla
    url = reverse(GESTION_CUENTAS[rol]['urls']['lista'])
    busqueda = request.POST.get('q', '').strip()
    return redirect(f'{url}?{urlencode({"q": busqueda})}' if busqueda else url)


@admin_required
def gestion_cuentas_view(request, rol):
    return pagina_cuentas(request, rol)


@admin_required
@require_POST
def cuenta_registrar_view(request, rol):
    form = CuentaForm(request.POST, auto_id='registro_%s')
    if not form.is_valid():
        return pagina_cuentas(request, rol, form_registro=form)

    cuenta = form.save(commit=False)
    cuenta.rol = rol
    try:
        asignar_clave_temporal(cuenta, request)
    except OSError:
        form.add_error(None, MENSAJE_ERROR_CORREO)
        return pagina_cuentas(request, rol, form_registro=form)

    messages.success(request, f'Se registró a {cuenta.get_short_name()} y se envió su contraseña temporal '
                              f'a {cuenta.email}.')
    return volver_a_la_lista(request, rol)


@admin_required
@require_POST
def cuenta_editar_view(request, rol, pk):
    cuenta = get_object_or_404(Usuario, pk=pk, rol=rol)
    form = CuentaForm(request.POST, instance=cuenta, auto_id='edicion_%s')
    if not form.is_valid():
        # El formulario ya copió los datos inválidos a `cuenta`; se muestra el registro guardado
        return pagina_cuentas(request, rol, form_edicion=form, cuenta_editada=Usuario.objects.get(pk=pk))

    form.save()
    messages.success(request, f'Se guardaron los cambios de {cuenta.get_short_name()}.')
    return volver_a_la_lista(request, rol)


@admin_required
@require_POST
def cuenta_estado_view(request, rol, pk):
    # Desactivar en vez de borrar: la persona ya no puede ingresar, pero su historial se conserva
    cuenta = get_object_or_404(Usuario, pk=pk, rol=rol)
    cuenta.is_active = not cuenta.is_active
    cuenta.save(update_fields=['is_active'])
    estado = 'reactivó' if cuenta.is_active else 'desactivó'
    messages.success(request, f'Se {estado} la cuenta de {cuenta.get_short_name()}.')
    return volver_a_la_lista(request, rol)


@admin_required
@require_POST
def cuenta_reenviar_clave_view(request, rol, pk):
    cuenta = get_object_or_404(Usuario, pk=pk, rol=rol, is_active=True)
    try:
        asignar_clave_temporal(cuenta, request)
    except OSError:
        messages.error(request, MENSAJE_ERROR_CORREO)
    else:
        messages.success(request, f'Se envió una nueva contraseña temporal a {cuenta.email}.')
    return volver_a_la_lista(request, rol)
