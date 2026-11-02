"""Eventos del calendario semanal, para el profesor (RF-09) y el alumno (RF-14)."""

COLORES = ['#0d6efd', '#198754', '#6f42c1', '#d63384', '#fd7e14', '#20c997']


def eventos_de_calendario(bloques, url_curso=None):
    """Convierte bloques semanales en eventos repetidos de FullCalendar; cada curso tiene su color.

    `url_curso` recibe un curso y entrega su dirección; sin ella, los bloques no son enlaces.
    FullCalendar numera los días desde el domingo (0), así que dia_semana (lunes = 1) sirve tal cual.
    """
    color_por_curso = {}
    eventos = []
    for bloque in bloques:
        color = color_por_curso.setdefault(bloque.curso_id, COLORES[len(color_por_curso) % len(COLORES)])
        evento = {
            'title': f'{bloque.curso.nombre} · {bloque.sala}' if bloque.sala else bloque.curso.nombre,
            'daysOfWeek': [bloque.dia_semana],
            'startTime': bloque.hora_inicio.strftime('%H:%M'),
            'endTime': bloque.hora_fin.strftime('%H:%M'),
            'color': color,
        }
        if url_curso:
            evento['url'] = url_curso(bloque.curso)
        eventos.append(evento)
    return eventos
