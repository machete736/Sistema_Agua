"""
Tickets para la impresora térmica (EPSON TM-T20, papel de 80 mm).

Un ticket se arma UNA sola vez como una lista de líneas de texto. Con esa
misma lista:
  - la pantalla muestra la vista previa (letra de ancho fijo, 48 columnas), y
  - el botón "Imprimir ticket" la manda a la impresora con QZ Tray.
Así lo que se ve en pantalla es exactamente lo que sale en el papel. Antes
eran dos textos escritos por separado y el impreso no traía los cargos
extra, el código del socio ni el monto en letras.
"""
from decimal import Decimal, InvalidOperation

# Caracteres por línea de la EPSON TM-T20 en papel de 80 mm (letra A).
ANCHO = 48


class Ticket:
    def __init__(self):
        self.lineas = []

    def _agregar(self, texto, alinear='i', negrita=False, grande=False):
        # La letra grande ocupa el doble de ancho: caben la mitad de caracteres.
        ancho = ANCHO // 2 if grande else ANCHO
        for parte in _partir(texto, ancho):
            self.lineas.append({'texto': parte, 'alinear': alinear,
                                'negrita': negrita, 'grande': grande})
        return self

    def centro(self, texto, negrita=False, grande=False):
        return self._agregar(texto, 'c', negrita, grande)

    def texto(self, texto, negrita=False):
        return self._agregar(texto, 'i', negrita)

    def fila(self, clave, valor, negrita=False):
        """'Clave:' a la izquierda y el valor pegado a la derecha."""
        clave, valor = str(clave), str(valor)
        espacio = ANCHO - len(clave) - len(valor)
        if espacio >= 1:
            return self._agregar(clave + ' ' * espacio + valor, 'i', negrita)
        # No entra en una línea: la clave arriba y el valor abajo a la derecha.
        self._agregar(clave, 'i', negrita)
        for parte in _partir(valor, ANCHO):
            self._agregar(parte.rjust(ANCHO), 'i', negrita)
        return self

    def raya(self, caracter='-'):
        return self._agregar(caracter * ANCHO)

    def blanco(self, cantidad=1):
        for _ in range(cantidad):
            self.lineas.append({'texto': '', 'alinear': 'i', 'negrita': False, 'grande': False})
        return self


def _partir(texto, ancho):
    """Corta un texto largo en líneas de `ancho` caracteres, sin partir palabras si se puede."""
    texto = ' '.join(str(texto).split())
    if len(texto) <= ancho:
        return [texto]
    lineas, actual = [], ''
    for palabra in texto.split(' '):
        while len(palabra) > ancho:  # palabra más larga que la línea
            if actual:
                lineas.append(actual)
                actual = ''
            lineas.append(palabra[:ancho])
            palabra = palabra[ancho:]
        if not actual:
            actual = palabra
        elif len(actual) + 1 + len(palabra) <= ancho:
            actual += ' ' + palabra
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def bs(monto):
    """Monto con 2 decimales y punto: 'Bs 1250.50'."""
    try:
        return f'Bs {Decimal(str(monto)):.2f}'
    except (InvalidOperation, ValueError):
        return f'Bs {monto}'


# =============================================================
# MONTO EN LETRAS
# =============================================================

_UNIDADES = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE',
             'DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE',
             'DIECIOCHO', 'DIECINUEVE', 'VEINTE', 'VEINTIUNO', 'VEINTIDÓS', 'VEINTITRÉS',
             'VEINTICUATRO', 'VEINTICINCO', 'VEINTISÉIS', 'VEINTISIETE', 'VEINTIOCHO', 'VEINTINUEVE']
_DECENAS = ['', '', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA',
            'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
_CENTENAS = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS',
             'QUINIENTOS', 'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS']


def _menos_de_mil(n):
    if n == 100:
        return 'CIEN'
    c, resto = divmod(n, 100)
    partes = [_CENTENAS[c]] if c else []
    if resto < 30:
        if resto:
            partes.append(_UNIDADES[resto])
    else:
        d, u = divmod(resto, 10)
        partes.append(_DECENAS[d] + (f' Y {_UNIDADES[u]}' if u else ''))
    return ' '.join(partes)


def _entero_a_letras(n):
    if n == 0:
        return 'CERO'
    partes = []
    millones, n = divmod(n, 1_000_000)
    miles, resto = divmod(n, 1000)
    if millones:
        partes.append('UN MILLÓN' if millones == 1 else f'{_menos_de_mil(millones)} MILLONES')
    if miles:
        partes.append('MIL' if miles == 1 else f'{_menos_de_mil(miles)} MIL')
    if resto:
        partes.append(_menos_de_mil(resto))
    texto = ' '.join(partes)
    # "veintiuno mil" -> "veintiún mil", "uno" final se mantiene
    return texto.replace('VEINTIUNO MIL', 'VEINTIÚN MIL').replace('UNO MIL', 'UN MIL')


def monto_a_literal(monto):
    """
    Monto en letras, como en los recibos: 60.50 -> "SESENTA CON 50/100 BOLIVIANOS".
    Funciona con miles y millones (antes solo llegaba a 999).
    """
    try:
        monto = Decimal(str(monto)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return 'MONTO INVÁLIDO'
    entero = int(monto)
    centavos = int((monto - entero) * 100)
    return f'{_entero_a_letras(entero)} CON {centavos:02d}/100 BOLIVIANOS'
