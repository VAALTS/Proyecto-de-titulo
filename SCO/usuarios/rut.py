from django.core.exceptions import ValidationError


def digito_verificador(cuerpo):
    """Calcula el dígito verificador de un RUT chileno con el algoritmo módulo 11."""
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: '0', 10: 'K'}.get(resto, str(resto))


def normalizar_rut(valor):
    """Valida un RUT escrito con o sin puntos y guion, y lo devuelve como 12345678-9."""
    limpio = valor.replace('.', '').replace('-', '').replace(' ', '').upper()
    cuerpo, dv = limpio[:-1], limpio[-1:]
    if not cuerpo.isdigit() or not 7 <= len(cuerpo) <= 8:
        raise ValidationError('Ingrese un RUT válido, por ejemplo 12.345.678-9.')
    if digito_verificador(cuerpo) != dv:
        raise ValidationError('El dígito verificador del RUT no es correcto.')
    return f'{int(cuerpo)}-{dv}'
