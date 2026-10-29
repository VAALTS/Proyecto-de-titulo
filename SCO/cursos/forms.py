from django import forms
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from usuarios.forms import EstiloBootstrapMixin
from usuarios.models import Rol, Usuario

from .models import Asistencia, Clase, Curso, Inscripcion, Material, Modulo


class ProfesorChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, profesor):
        return f'{profesor.get_full_name()} ({profesor.email})'


class CursoForm(EstiloBootstrapMixin, forms.ModelForm):
    """RF-06: nombre del curso, descripción y profesor a cargo."""

    profesor = ProfesorChoiceField(queryset=Usuario.objects.none(), label='Profesor a cargo',
                                   empty_label='Seleccione un profesor')

    class Meta:
        model = Curso
        fields = ['nombre', 'profesor', 'descripcion']
        labels = {'nombre': 'Nombre del curso', 'descripcion': 'Descripción'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo profesores activos; al editar se mantiene el actual aunque su cuenta esté desactivada
        disponibles = Q(rol=Rol.PROFESOR, is_active=True)
        if self.instance.profesor_id:
            disponibles |= Q(pk=self.instance.profesor_id)
        self.fields['profesor'].queryset = Usuario.objects.filter(disponibles).order_by(
            'apellido_paterno', 'primer_nombre')


class AlumnoChoiceField(forms.ModelMultipleChoiceField):

    def label_from_instance(self, alumno):
        # El buscador filtra por este texto: nombre, RUT y correo
        return f'{alumno.get_full_name()} · {alumno.rut} · {alumno.email}'


class InscripcionForm(forms.Form):
    """RF-07: alumnos que se inscriben en un curso, elegidos con un buscador."""

    alumnos = AlumnoChoiceField(
        queryset=Usuario.objects.none(), label='Alumnos',
        error_messages={'required': 'Seleccione al menos un alumno.',
                        'invalid_choice': 'Uno de los alumnos seleccionados ya no está disponible.'},
    )

    def __init__(self, curso, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.curso = curso
        # Alumnos activos que todavía no están inscritos en este curso
        self.fields['alumnos'].queryset = (
            Usuario.objects.filter(rol=Rol.ALUMNO, is_active=True)
            .exclude(inscripciones__curso=curso, inscripciones__activa=True)
            .order_by('apellido_paterno', 'primer_nombre')
        )

    @transaction.atomic
    def save(self):
        for alumno in self.cleaned_data['alumnos']:
            # Si el alumno se había retirado, se reactiva su inscripción anterior en vez de duplicarla
            Inscripcion.objects.update_or_create(
                alumno=alumno, curso=self.curso,
                defaults={'activa': True, 'fecha_inscripcion': timezone.localdate()},
            )
        return self.cleaned_data['alumnos']


class ModuloForm(EstiloBootstrapMixin, forms.ModelForm):
    """RF-10: módulos en que el profesor organiza su curso."""

    class Meta:
        model = Modulo
        fields = ['nombre']
        labels = {'nombre': 'Nombre del módulo'}


class ClaseForm(EstiloBootstrapMixin, forms.ModelForm):
    """RF-10: clases con fecha y horario dentro de un módulo."""

    class Meta:
        model = Clase
        fields = ['titulo', 'fecha', 'hora_inicio', 'hora_fin']
        labels = {'titulo': 'Título de la clase', 'fecha': 'Fecha', 'hora_inicio': 'Hora de inicio',
                  'hora_fin': 'Hora de término'}
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get('hora_inicio'), datos.get('hora_fin')
        if inicio and fin and fin <= inicio:
            self.add_error('hora_fin', 'La hora de término debe ser posterior a la de inicio.')
        return datos


TAMANO_MAXIMO_MB = 20
EXTENSIONES_PERMITIDAS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'jpg', 'jpeg', 'png',
                          'gif', 'zip']


class MaterialForm(EstiloBootstrapMixin, forms.ModelForm):
    """RF-10: archivo, enlace o carpeta de una clase. El tipo no cambia al editar."""

    class Meta:
        model = Material
        fields = ['tipo', 'titulo', 'archivo', 'url']
        labels = {'tipo': 'Tipo de material', 'titulo': 'Título', 'archivo': 'Archivo', 'url': 'Dirección del enlace'}
        widgets = {'archivo': forms.FileInput, 'url': forms.URLInput(attrs={'placeholder': 'https://'})}
        help_texts = {
            'archivo': f'Hasta {TAMANO_MAXIMO_MB} MB. Formatos: {", ".join(EXTENSIONES_PERMITIDAS)}. '
                       'Para videos, agregue un enlace (YouTube, Drive).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['archivo'].validators.append(FileExtensionValidator(EXTENSIONES_PERMITIDAS))
        if self.instance.pk:
            self.fields['tipo'].disabled = True
        elif self.instance.carpeta_id:
            # Las carpetas tienen un solo nivel
            self.fields['tipo'].choices = [opcion for opcion in Material.Tipo.choices
                                           if opcion[0] != Material.Tipo.CARPETA]

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if archivo and archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
            raise forms.ValidationError(f'El archivo pesa más de {TAMANO_MAXIMO_MB} MB.')
        return archivo

    def clean(self):
        datos = super().clean()
        tipo = datos.get('tipo')
        if tipo == Material.Tipo.ARCHIVO:
            if not datos.get('archivo') and 'archivo' not in self.errors:
                self.add_error('archivo', 'Seleccione el archivo que desea subir.')
            datos['url'] = None
        elif tipo == Material.Tipo.ENLACE:
            if not datos.get('url') and 'url' not in self.errors:
                self.add_error('url', 'Ingrese la dirección del enlace.')
            datos['archivo'] = None
        elif tipo == Material.Tipo.CARPETA:
            datos['archivo'] = datos['url'] = None
        return datos

    def save(self, commit=True):
        # Si se reemplazó el archivo, el anterior se borra del disco
        anterior = None
        if self.instance.pk and 'archivo' in self.changed_data:
            anterior = Material.objects.get(pk=self.instance.pk).archivo
        material = super().save(commit)
        if anterior:
            anterior.delete(save=False)
        return material


class AsistenciaForm(forms.Form):
    """RF-12: un campo Presente/Ausente por cada alumno inscrito en el curso de la clase."""

    OPCIONES = [('presente', 'Presente'), ('ausente', 'Ausente')]

    def __init__(self, clase, inscripciones, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clase = clase
        self.inscripciones = list(inscripciones)
        registradas = {a.inscripcion_id: a.presente for a in clase.asistencias.all()}
        for inscripcion in self.inscripciones:
            # Lo ya registrado se muestra marcado; si la clase no tiene registro, todos parten presentes
            presente = registradas.get(inscripcion.pk, True)
            self.fields[self.nombre_campo(inscripcion)] = forms.ChoiceField(
                choices=self.OPCIONES, initial='presente' if presente else 'ausente',
                label=inscripcion.alumno.get_full_name(), widget=forms.RadioSelect,
                error_messages={'required': 'Marque Presente o Ausente.'},
            )

    @staticmethod
    def nombre_campo(inscripcion):
        return f'asistencia_{inscripcion.pk}'

    def filas(self):
        """Cada alumno con su campo, para dibujar la lista en la plantilla."""
        return [(inscripcion, self[self.nombre_campo(inscripcion)]) for inscripcion in self.inscripciones]

    @transaction.atomic
    def save(self, profesor):
        for inscripcion in self.inscripciones:
            Asistencia.objects.update_or_create(
                clase=self.clase, inscripcion=inscripcion,
                defaults={'presente': self.cleaned_data[self.nombre_campo(inscripcion)] == 'presente',
                          'registrada_por': profesor},
            )
