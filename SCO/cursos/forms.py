from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from usuarios.forms import EstiloBootstrapMixin
from usuarios.models import Rol, Usuario

from .models import Clase, Curso, Inscripcion, Modulo


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
