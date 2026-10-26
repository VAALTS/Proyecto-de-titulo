from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .cuentas import asignar_clave_temporal
from .forms import AlumnoForm, CambioContrasenaForm, LoginForm
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


# ---------- Gestión de alumnos (RF-04) ----------

def buscar_alumnos(texto):
    """Cada palabra buscada debe aparecer en el nombre, los apellidos, el correo o el RUT."""
    alumnos = Usuario.objects.filter(rol=Rol.ALUMNO)
    for palabra in texto.split():
        alumnos = alumnos.filter(
            Q(primer_nombre__icontains=palabra) | Q(segundo_nombre__icontains=palabra)
            | Q(apellido_paterno__icontains=palabra) | Q(apellido_materno__icontains=palabra)
            | Q(email__icontains=palabra) | Q(rut__icontains=palabra.replace('.', ''))
        )
    return alumnos.order_by('apellido_paterno', 'apellido_materno', 'primer_nombre')


def pagina_alumnos(request, form_registro=None, form_edicion=None, alumno_editado=None):
    # Si un formulario vuelve con errores, la página se abre con su modal desplegado
    busqueda = (request.POST.get('q') or request.GET.get('q', '')).strip()
    return render(request, 'administrador/alumnos.html', {
        'alumnos': buscar_alumnos(busqueda),
        'q': busqueda,
        'form_registro': form_registro or AlumnoForm(auto_id='registro_%s'),
        'form_edicion': form_edicion or AlumnoForm(auto_id='edicion_%s'),
        'alumno_editado': alumno_editado,
        'abrir_modal': 'modalRegistro' if form_registro else 'modalEdicion' if form_edicion else '',
    })


def volver_a_alumnos(request):
    # Conserva la búsqueda que el administrador tenía en pantalla
    url = reverse('gestion_alumnos')
    busqueda = request.POST.get('q', '').strip()
    return redirect(f'{url}?{urlencode({"q": busqueda})}' if busqueda else url)


@admin_required
def gestion_alumnos_view(request):
    return pagina_alumnos(request)


@admin_required
@require_POST
def alumno_registrar_view(request):
    form = AlumnoForm(request.POST, auto_id='registro_%s')
    if not form.is_valid():
        return pagina_alumnos(request, form_registro=form)

    alumno = form.save(commit=False)
    alumno.rol = Rol.ALUMNO
    try:
        asignar_clave_temporal(alumno, request)
    except OSError:
        form.add_error(None, MENSAJE_ERROR_CORREO)
        return pagina_alumnos(request, form_registro=form)

    messages.success(request, f'Se registró a {alumno.get_short_name()} y se envió su contraseña temporal '
                              f'a {alumno.email}.')
    return volver_a_alumnos(request)


@admin_required
@require_POST
def alumno_editar_view(request, pk):
    alumno = get_object_or_404(Usuario, pk=pk, rol=Rol.ALUMNO)
    form = AlumnoForm(request.POST, instance=alumno, auto_id='edicion_%s')
    if not form.is_valid():
        # El formulario ya copió los datos inválidos a `alumno`; se muestra el registro guardado
        return pagina_alumnos(request, form_edicion=form, alumno_editado=Usuario.objects.get(pk=pk))

    form.save()
    messages.success(request, f'Se guardaron los cambios de {alumno.get_short_name()}.')
    return volver_a_alumnos(request)


@admin_required
@require_POST
def alumno_estado_view(request, pk):
    # Desactivar en vez de borrar: el alumno ya no puede ingresar, pero su historial se conserva
    alumno = get_object_or_404(Usuario, pk=pk, rol=Rol.ALUMNO)
    alumno.is_active = not alumno.is_active
    alumno.save(update_fields=['is_active'])
    estado = 'reactivó' if alumno.is_active else 'desactivó'
    messages.success(request, f'Se {estado} la cuenta de {alumno.get_short_name()}.')
    return volver_a_alumnos(request)


@admin_required
@require_POST
def alumno_reenviar_clave_view(request, pk):
    alumno = get_object_or_404(Usuario, pk=pk, rol=Rol.ALUMNO, is_active=True)
    try:
        asignar_clave_temporal(alumno, request)
    except OSError:
        messages.error(request, MENSAJE_ERROR_CORREO)
    else:
        messages.success(request, f'Se envió una nueva contraseña temporal a {alumno.email}.')
    return volver_a_alumnos(request)


# ---------- Gestión de profesores y cursos (RF-05 y RF-06) ----------

@admin_required
def gestion_profesores_view(request):
    return render(request, 'administrador/profesores.html')


@admin_required
def gestion_cursos_view(request):
    return render(request, 'administrador/cursos.html')
