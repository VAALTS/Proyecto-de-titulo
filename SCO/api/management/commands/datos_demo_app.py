"""Crea datos de ejemplo para probar la aplicación móvil en un computador de desarrollo.

Uso (con DEBUG=True):
    python manage.py datos_demo_app

Crea un profesor, dos alumnos y un curso con horario, material, una actividad con notas y un tema de foro.
Si los datos ya existen, no los duplica. Las cuentas usan la contraseña indicada abajo.
"""
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cursos.models import BloqueHorario, Clase, Curso, Inscripcion, Material, MensajeForo, Modulo, TemaForo
from evaluaciones.models import Actividad, Calificacion
from usuarios.models import Rol, Usuario

CLAVE_DEMO = 'DemoApp2026'

PDF_MINIMO = (b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj '
              b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>'
              b'endobj 4 0 obj<</Length 52>>stream\nBT /F1 18 Tf 30 70 Td (Apuntes de ejemplo) Tj ET\nendstream endobj '
              b'5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF')


class Command(BaseCommand):
    help = 'Crea datos de ejemplo para probar la aplicación móvil (solo en desarrollo).'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Este comando es solo para desarrollo (DEBUG=True).')

        def cuenta(email, rut, nombre, apellido, rol):
            usuario, creado = Usuario.objects.get_or_create(email=email, defaults={
                'rut': rut, 'primer_nombre': nombre, 'apellido_paterno': apellido, 'rol': rol})
            if creado:
                usuario.set_password(CLAVE_DEMO)
                usuario.save()
            return usuario

        profesor = cuenta('profesor.demo@adapt.cl', '15678432-1', 'Daniela', 'Rojas', Rol.PROFESOR)
        alumna = cuenta('alumna.demo@adapt.cl', '21345678-9', 'Camila', 'Fuentes', Rol.ALUMNO)
        alumno = cuenta('alumno.demo@adapt.cl', '20111222-3', 'Benjamín', 'Soto', Rol.ALUMNO)

        curso, creado = Curso.objects.get_or_create(nombre='Prevención de riesgos (demo app)', profesor=profesor,
                                                    defaults={'descripcion': 'Curso de ejemplo para la app.'})
        if not creado:
            self.stdout.write('Los datos de ejemplo ya existían.')
            return
        for persona in (alumna, alumno):
            Inscripcion.objects.create(alumno=persona, curso=curso)
        BloqueHorario.objects.create(curso=curso, dia_semana=1, hora_inicio=time(9), hora_fin=time(10, 30), sala='Sala 204')
        BloqueHorario.objects.create(curso=curso, dia_semana=4, hora_inicio=time(15), hora_fin=time(16, 30), sala='Online')

        modulo = Modulo.objects.create(curso=curso, nombre='Unidad 1 · Fundamentos')
        hoy = timezone.localdate()
        clase = Clase.objects.create(modulo=modulo, titulo='Introducción', fecha=hoy, hora_inicio=time(9),
                                     hora_fin=time(10, 30))
        carpeta = Material.objects.create(clase=clase, subido_por=profesor, titulo='Unidad 1', tipo=Material.Tipo.CARPETA)
        apuntes = Material(clase=clase, subido_por=profesor, titulo='Apuntes: conceptos básicos',
                           tipo=Material.Tipo.ARCHIVO, carpeta=carpeta)
        apuntes.archivo.save('apuntes-unidad-1.pdf', ContentFile(PDF_MINIMO), save=True)
        Material.objects.create(clase=clase, subido_por=profesor, titulo='Ley 16.744 (BCN)', tipo=Material.Tipo.ENLACE,
                                url='https://www.bcn.cl/leychile/navegar?idNorma=28650', carpeta=carpeta)
        Material.objects.create(clase=clase, subido_por=profesor, titulo='Guía aún no publicada',
                                tipo=Material.Tipo.ENLACE, url='https://www.ejemplo.cl', visible=False)

        control = Actividad.objects.create(clase=clase, titulo='Control 1', ponderacion=Decimal('30'),
                                           fecha_limite=timezone.now() - timedelta(days=3))
        Actividad.objects.create(clase=clase, titulo='Tarea: matriz de riesgos', ponderacion=Decimal('30'),
                                 fecha_limite=timezone.now() + timedelta(days=2))
        Actividad.objects.create(clase=clase, titulo='Prueba final', ponderacion=Decimal('40'),
                                 tipo=Actividad.Tipo.FORMULARIO, fecha_limite=timezone.now() + timedelta(days=9))
        for persona, nota in ((alumna, '5.8'), (alumno, '4.6')):
            Calificacion.objects.create(actividad=control, inscripcion=curso.inscripciones.get(alumno=persona),
                                        nota=Decimal(nota), registrada_por=profesor)

        tema = TemaForo.objects.create(curso=curso, autor=profesor, titulo='Dudas para el Control 2')
        MensajeForo.objects.create(tema=tema, autor=profesor, contenido='Dejen aquí sus preguntas sobre la Unidad 1.')
        MensajeForo.objects.create(tema=tema, autor=alumno, contenido='¿Entra la matriz de riesgos?')

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Cuentas de prueba (contraseña {CLAVE_DEMO}): profesor.demo@adapt.cl, alumna.demo@adapt.cl, '
            f'alumno.demo@adapt.cl'))
