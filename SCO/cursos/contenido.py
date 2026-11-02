"""Contenido de un curso ordenado para mostrarlo, al profesor (RF-10) y al alumno (RF-16)."""
from .models import Material


def organizar_material(modulos):
    """Deja en cada clase su material de primer nivel (carpetas primero) y en cada carpeta su contenido."""
    for modulo in modulos:
        for clase in modulo.clases.all():
            materiales = list(clase.materiales.all())
            for material in materiales:
                material.hijos = [hijo for hijo in materiales if hijo.carpeta_id == material.pk]
            clase.raiz = sorted((m for m in materiales if m.carpeta_id is None),
                                key=lambda m: (m.tipo != Material.Tipo.CARPETA, m.titulo.lower()))
    return modulos
