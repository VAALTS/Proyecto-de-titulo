from decimal import Decimal

from django import forms
from django.db import transaction
from django.db.models import Sum

from cursos.models import Clase
from usuarios.forms import EstiloBootstrapMixin

from .models import NOTA_MAXIMA, NOTA_MINIMA, Actividad, Alternativa, Calificacion, Pregunta


def porcentaje(valor):
    """Decimal('37.50') → '37,5'; Decimal('70.00') → '70'."""
    return f'{Decimal(valor).normalize():f}'.replace('.', ',')


class ClaseChoiceField(forms.ModelChoiceField):

    def label_from_instance(self, clase):
        return f'{clase.modulo.nombre} · {clase.titulo} ({clase.fecha:%d/%m/%Y})'


class ActividadForm(EstiloBootstrapMixin, forms.ModelForm):
    """RF-11: cada actividad exige su ponderación, y las del curso no pueden sumar más de 100 %."""

    clase = ClaseChoiceField(queryset=Clase.objects.none(), label='Clase', empty_label='Seleccione la clase')

    class Meta:
        model = Actividad
        fields = ['clase', 'titulo', 'tipo', 'ponderacion', 'fecha_limite', 'descripcion']
        labels = {'titulo': 'Título', 'tipo': 'Tipo de actividad', 'ponderacion': 'Ponderación (%)',
                  'fecha_limite': 'Fecha límite', 'descripcion': 'Instrucciones'}
        widgets = {
            'ponderacion': forms.NumberInput(attrs={'min': '0.01', 'max': '100', 'step': '0.01'}),
            'fecha_limite': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {'ponderacion': 'Porcentaje de la nota final del curso.'}

    def __init__(self, curso, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.curso = curso
        self.fields['clase'].queryset = (Clase.objects.filter(modulo__curso=curso).select_related('modulo')
                                         .order_by('modulo__orden', 'fecha', 'hora_inicio'))

    def clean(self):
        datos = super().clean()
        ponderacion = datos.get('ponderacion')
        if ponderacion:
            otras = Actividad.objects.filter(clase__modulo__curso=self.curso).exclude(pk=self.instance.pk)
            asignada = otras.aggregate(total=Sum('ponderacion'))['total'] or Decimal('0')
            if asignada + ponderacion > 100:
                disponible = Decimal('100') - asignada
                self.add_error('ponderacion', f'Las actividades del curso ya suman {porcentaje(asignada)} %. '
                                              f'Puede asignar como máximo {porcentaje(disponible)} %.')
        if (self.instance.pk and datos.get('tipo') == Actividad.Tipo.ARCHIVO
                and self.instance.preguntas.exists()):
            self.add_error('tipo', 'Esta actividad tiene preguntas. Elimínelas antes de cambiar el tipo.')
        return datos


class NotaField(forms.DecimalField):
    """Nota de 1,0 a 7,0 con un decimal; acepta coma o punto."""

    def __init__(self, **kwargs):
        super().__init__(min_value=NOTA_MINIMA, max_value=NOTA_MAXIMA, max_digits=2, decimal_places=1,
                         required=False, **kwargs)
        self.error_messages.update({
            'invalid': 'Ingrese una nota válida, por ejemplo 5,5.',
            'min_value': 'La nota mínima es 1,0.',
            'max_value': 'La nota máxima es 7,0.',
            'max_decimal_places': 'Use un solo decimal.',
            'max_digits': 'Use un solo decimal.',
        })

    def to_python(self, valor):
        if isinstance(valor, str):
            valor = valor.strip().replace(',', '.')
        return super().to_python(valor)


class CalificacionesForm(forms.Form):
    """Planilla de notas de una actividad: una nota y una observación por alumno inscrito."""

    def __init__(self, actividad, inscripciones, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actividad = actividad
        self.inscripciones = list(inscripciones)
        registradas = {c.inscripcion_id: c for c in actividad.calificaciones.all()}
        for inscripcion in self.inscripciones:
            actual = registradas.get(inscripcion.pk)
            self.fields[f'nota_{inscripcion.pk}'] = NotaField(
                initial=actual.nota if actual else None, label=inscripcion.alumno.get_full_name(),
                widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': '1,0 a 7,0',
                                              'class': 'form-control text-center', 'autocomplete': 'off'}))
            self.fields[f'observacion_{inscripcion.pk}'] = forms.CharField(
                required=False, initial=actual.observacion if actual else '', label='Observación',
                widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}))

    def filas(self):
        return [(inscripcion, self[f'nota_{inscripcion.pk}'], self[f'observacion_{inscripcion.pk}'])
                for inscripcion in self.inscripciones]

    def clean(self):
        datos = super().clean()
        for inscripcion in self.inscripciones:
            if datos.get(f'observacion_{inscripcion.pk}') and datos.get(f'nota_{inscripcion.pk}') is None \
                    and f'nota_{inscripcion.pk}' not in self.errors:
                self.add_error(f'nota_{inscripcion.pk}', 'Ingrese la nota para guardar la observación.')
        return datos

    @transaction.atomic
    def save(self, profesor):
        """Guarda las notas ingresadas; si se borra una nota, se elimina esa calificación."""
        calificadas = 0
        for inscripcion in self.inscripciones:
            nota = self.cleaned_data[f'nota_{inscripcion.pk}']
            if nota is None:
                Calificacion.objects.filter(actividad=self.actividad, inscripcion=inscripcion).delete()
                continue
            Calificacion.objects.update_or_create(
                actividad=self.actividad, inscripcion=inscripcion,
                defaults={'nota': nota, 'observacion': self.cleaned_data[f'observacion_{inscripcion.pk}'],
                          'registrada_por': profesor},
            )
            calificadas += 1
        return calificadas


MINIMO_ALTERNATIVAS = 2


class PreguntaForm(EstiloBootstrapMixin, forms.ModelForm):
    """Pregunta de un formulario en línea. Las alternativas llegan como filas repetidas:
    `alternativa` trae cada texto y `correcta` la posición de la fila marcada."""

    class Meta:
        model = Pregunta
        fields = ['enunciado', 'tipo', 'puntaje']
        labels = {'enunciado': 'Enunciado', 'tipo': 'Tipo de pregunta', 'puntaje': 'Puntaje'}
        widgets = {
            'enunciado': forms.Textarea(attrs={'rows': 3}),
            'puntaje': forms.NumberInput(attrs={'min': '0.1', 'step': '0.1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alternativas = []

    def filas_enviadas(self):
        """Lo que escribió el profesor, para volver a mostrarlo si hay errores."""
        if not self.is_bound:
            return []
        marcada = self.data.get('correcta')
        return [{'texto': texto, 'correcta': str(posicion) == marcada}
                for posicion, texto in enumerate(self.data.getlist('alternativa'))]

    def clean(self):
        datos = super().clean()
        if datos.get('tipo') != Pregunta.Tipo.ALTERNATIVAS:
            return datos
        filas = [{'texto': fila['texto'].strip(), 'correcta': fila['correcta']} for fila in self.filas_enviadas()]
        self.alternativas = [fila for fila in filas if fila['texto']]
        if len(self.alternativas) < MINIMO_ALTERNATIVAS:
            self.add_error(None, f'Agregue al menos {MINIMO_ALTERNATIVAS} alternativas.')
        elif any(len(fila['texto']) > 300 for fila in self.alternativas):
            self.add_error(None, 'Cada alternativa puede tener hasta 300 caracteres.')
        elif sum(fila['correcta'] for fila in self.alternativas) != 1:
            self.add_error(None, 'Marque cuál es la alternativa correcta.')
        return datos

    @transaction.atomic
    def save(self, commit=True):
        pregunta = super().save(commit)
        # Las alternativas se reemplazan completas; una pregunta de desarrollo no tiene
        pregunta.alternativas.all().delete()
        if pregunta.tipo == Pregunta.Tipo.ALTERNATIVAS:
            Alternativa.objects.bulk_create(
                Alternativa(pregunta=pregunta, texto=fila['texto'], es_correcta=fila['correcta'])
                for fila in self.alternativas)
        return pregunta
