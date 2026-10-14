from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from .models import Cobro, Lectura, Medidor, Pago, Socio
from .views_egresos import CERO, _anio_pedido, _datos_balance
from .views_web import es_admin_o_tesorero, _metadata_reporte


ESTADOS_DEUDA = ['Pendiente', 'En Revision', 'En Revisión', 'Vencido']
MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _bs(valor):
    return f'Bs {valor:,.2f}'


def _porcentaje(parte, total):
    if not total:
        return 0
    return round(float(parte) / float(total) * 100)


def _por_periodo(consulta, campo_periodo, campo_monto):
    """Devuelve una lista de 12 totales (enero a diciembre) según el periodo 'AAAA-MM'."""
    totales = [CERO] * 12
    for fila in consulta.values(campo_periodo).annotate(total=Sum(campo_monto)):
        try:
            mes = int(str(fila[campo_periodo]).split('-')[1])
        except (IndexError, ValueError):
            continue
        if 1 <= mes <= 12:
            totales[mes - 1] += fila['total'] or CERO
    return totales


def _datos_reporte_general(anio):
    """Junta en un solo lugar los números de toda la gestión."""
    hoy = timezone.localdate()
    prefijo = f'{anio}-'

    balance = _datos_balance(anio)
    totales = balance['totales']
    meses = balance['meses']

    # Meses que ya pasaron: en el año en curso no se compara con meses
    # que todavía no llegan.
    if anio < hoy.year:
        meses_transcurridos = 12
    elif anio == hoy.year:
        meses_transcurridos = hoy.month
    else:
        meses_transcurridos = 0

    # ── Agua: consumo y cobros emitidos por periodo ─────────────
    consumo_mes = _por_periodo(
        Lectura.objects.filter(periodo__startswith=prefijo), 'periodo', 'consumo_cubos')
    cobros_anio = Cobro.objects.filter(lectura__periodo__startswith=prefijo)
    emitido_mes = _por_periodo(cobros_anio, 'lectura__periodo', 'monto_total')

    consumo_total = sum(consumo_mes, CERO)
    emitido_total = sum(emitido_mes, CERO)
    cobros_cantidad = cobros_anio.count()

    estados = list(
        cobros_anio.values('estado_pago')
        .annotate(cantidad=Count('pk'), total=Sum('monto_total'))
        .order_by('estado_pago')
    )
    emitido_cancelado = sum(
        (e['total'] or CERO for e in estados if e['estado_pago'] == 'Cancelado'), CERO)

    metodos = list(
        Pago.objects.filter(estado='Aprobado', fecha_pago__year=anio)
        .values('metodo_pago')
        .annotate(cantidad=Count('pk'), total=Sum('monto_pagado'))
        .order_by('-total')
    )
    nombres_metodo = dict(Pago.METODO_CHOICES)
    for m in metodos:
        m['nombre'] = nombres_metodo.get(m['metodo_pago'], m['metodo_pago'] or 'Sin método')

    # ── Deuda: lo que se debe HOY, sin importar de qué año es ───
    cobros_con_deuda = Cobro.objects.filter(estado_pago__in=ESTADOS_DEUDA)
    deuda_total = cobros_con_deuda.aggregate(total=Sum('monto_total'))['total'] or CERO
    socios_con_deuda = cobros_con_deuda.values('socio').distinct().count()
    cobros_vencidos = cobros_con_deuda.filter(estado_pago='Vencido').count()
    top_deudores = list(
        Socio.objects.filter(recibos__estado_pago__in=ESTADOS_DEUDA)
        .annotate(deuda=Sum('recibos__monto_total'), cobros_debe=Count('recibos'))
        .filter(deuda__gt=0)
        .order_by('-deuda')[:10]
    )

    socios_activos = Socio.objects.filter(estado='ACTIVO').count()
    medidores_activos = Medidor.objects.filter(estado='Activo').count()
    pagos_en_revision = Pago.objects.filter(estado='En Revision').count()

    anterior = _datos_balance(anio - 1)['totales']

    datos = {
        'anio': anio,
        'meses': meses,
        'totales': totales,
        'por_categoria': balance['por_categoria'],
        'meses_transcurridos': meses_transcurridos,
        'consumo_total': consumo_total,
        'emitido_total': emitido_total,
        'emitido_cancelado': emitido_cancelado,
        'porcentaje_cobrado': _porcentaje(emitido_cancelado, emitido_total),
        'cobros_cantidad': cobros_cantidad,
        'estados': estados,
        'metodos': metodos,
        'deuda_total': deuda_total,
        'socios_con_deuda': socios_con_deuda,
        'cobros_vencidos': cobros_vencidos,
        'top_deudores': top_deudores,
        'socios_activos': socios_activos,
        'medidores_activos': medidores_activos,
        'pagos_en_revision': pagos_en_revision,
        'anterior': anterior,
        'resumen_meses': [
            {
                'nombre': meses[i]['nombre'],
                'consumo': consumo_mes[i],
                'emitido': emitido_mes[i],
                'ingresos': meses[i]['ingresos'],
                'egresos': meses[i]['egresos'],
                'saldo': meses[i]['saldo'],
            }
            for i in range(12)
        ],
        # Datos para las gráficas
        'graf_meses': MESES_CORTOS,
        'graf_ingresos': [float(m['ingresos']) for m in meses],
        'graf_egresos': [float(m['egresos']) for m in meses],
        'graf_acumulado': [float(m['acumulado']) for m in meses],
        'graf_consumo': [float(c) for c in consumo_mes],
        'graf_emitido': [float(e) for e in emitido_mes],
        'graf_categorias': {
            'nombres': [c['categoria__nombre'] for c in balance['por_categoria']],
            'totales': [float(c['total']) for c in balance['por_categoria']],
        },
        'graf_estados': {
            'nombres': [e['estado_pago'] for e in estados],
            'totales': [e['cantidad'] for e in estados],
        },
        'graf_metodos': {
            'nombres': [m['nombre'] for m in metodos],
            'totales': [float(m['total'] or 0) for m in metodos],
        },
    }
    datos['interpretacion'] = _interpretar(datos, consumo_mes)
    return datos


def _interpretar(d, consumo_mes):
    """
    Lee los números del reporte y los explica en frases sencillas.
    Cada frase lleva un tipo (success / info / warning / danger) que
    define el color con el que se muestra.
    """
    frases = []

    def agregar(tipo, titulo, texto):
        frases.append({'tipo': tipo, 'titulo': titulo, 'texto': texto})

    anio = d['anio']
    totales = d['totales']
    ingresos, egresos, saldo = totales['ingresos'], totales['egresos'], totales['saldo']
    con_datos = d['meses'][:d['meses_transcurridos']]

    # ── Saldo de la gestión ─────────────────────────────────────
    if not ingresos and not egresos:
        agregar('info', 'Sin movimiento',
                f'En la gestión {anio} todavía no hay ingresos ni egresos registrados.')
    elif saldo >= 0:
        gastado = _porcentaje(egresos, ingresos)
        agregar('success', 'Saldo a favor',
                f'Entraron {_bs(ingresos)} y se gastaron {_bs(egresos)}: quedan {_bs(saldo)} a favor. '
                f'De cada Bs 100 que ingresaron se gastaron Bs {gastado}.')
    else:
        agregar('danger', 'Se gastó más de lo que entró',
                f'Entraron {_bs(ingresos)} y se gastaron {_bs(egresos)}: faltan {_bs(-saldo)}. '
                f'Conviene revisar los egresos o reforzar la cobranza.')

    # ── Cobranza ────────────────────────────────────────────────
    if d['emitido_total']:
        pct = d['porcentaje_cobrado']
        texto = (f'De los {_bs(d["emitido_total"])} emitidos en {d["cobros_cantidad"]} cobros, '
                 f'ya está cancelado el {pct}% ({_bs(d["emitido_cancelado"])}).')
        if pct >= 90:
            agregar('success', 'Cobranza muy buena', texto)
        elif pct >= 70:
            agregar('warning', 'Cobranza aceptable', texto + ' Todavía hay margen para mejorar.')
        else:
            agregar('danger', 'Cobranza baja', texto + ' Es el punto que más atención necesita.')

    # ── Mejor y peor mes de ingresos ────────────────────────────
    con_ingresos = [m for m in con_datos if m['ingresos'] > 0]
    if len(con_ingresos) >= 2:
        mejor = max(con_ingresos, key=lambda m: m['ingresos'])
        peor = min(con_ingresos, key=lambda m: m['ingresos'])
        promedio = ingresos / len(con_ingresos)
        agregar('info', 'Ritmo de ingresos',
                f'El mes con más ingresos fue {mejor["nombre"].capitalize()} ({_bs(mejor["ingresos"])}) '
                f'y el más bajo {peor["nombre"].capitalize()} ({_bs(peor["ingresos"])}). '
                f'El promedio mensual es {_bs(promedio)}.')

    meses_en_rojo = [m['nombre'].capitalize() for m in con_datos if m['saldo'] < 0]
    if meses_en_rojo:
        agregar('warning', 'Meses con saldo negativo',
                f'En {", ".join(meses_en_rojo)} se gastó más de lo que se recaudó ese mes.')

    # ── Egresos ─────────────────────────────────────────────────
    if d['por_categoria']:
        mayor = d['por_categoria'][0]
        parte = _porcentaje(mayor['total'], egresos)
        texto = (f'El gasto más grande es "{mayor["categoria__nombre"]}" con {_bs(mayor["total"])}, '
                 f'el {parte}% de todos los egresos.')
        con_egresos = [m for m in con_datos if m['egresos'] > 0]
        if con_egresos:
            mes_caro = max(con_egresos, key=lambda m: m['egresos'])
            texto += f' El mes con más gasto fue {mes_caro["nombre"].capitalize()} ({_bs(mes_caro["egresos"])}).'
        agregar('warning' if parte >= 60 else 'info', 'En qué se gasta', texto)
    elif ingresos:
        agregar('info', 'Sin egresos registrados',
                'No hay egresos registrados en esta gestión. Si el comité tuvo gastos, '
                'hay que registrarlos para que el saldo sea real.')

    # ── Deuda actual ────────────────────────────────────────────
    if d['deuda_total'] > 0:
        texto = (f'Hoy {d["socios_con_deuda"]} socios deben en total {_bs(d["deuda_total"])}; '
                 f'{d["cobros_vencidos"]} cobros ya están vencidos.')
        if d['top_deudores']:
            primero = d['top_deudores'][0]
            texto += (f' Quien más debe es {primero.nombre_completo} con {_bs(primero.deuda)} '
                      f'({_porcentaje(primero.deuda, d["deuda_total"])}% de la deuda).')
        parte_socios = _porcentaje(d['socios_con_deuda'], d['socios_activos'])
        agregar('danger' if parte_socios >= 40 else 'warning', 'Deuda pendiente', texto)
    else:
        agregar('success', 'Sin deudas', 'No hay cobros pendientes ni vencidos.')

    if d['pagos_en_revision']:
        agregar('warning', 'Comprobantes por revisar',
                f'Hay {d["pagos_en_revision"]} comprobantes enviados desde la app esperando revisión. '
                f'Mientras no se revisen, esos pagos no cuentan como recaudados.')

    # ── Consumo de agua ─────────────────────────────────────────
    if d['consumo_total']:
        con_consumo = [(i, c) for i, c in enumerate(consumo_mes) if c > 0]
        indice_pico, pico = max(con_consumo, key=lambda par: par[1])
        promedio = d['consumo_total'] / len(con_consumo)
        texto = (f'Se consumieron {d["consumo_total"]:,.0f} m³ en la gestión, unos {promedio:,.0f} m³ por mes. '
                 f'El mes de mayor consumo fue {d["meses"][indice_pico]["nombre"].capitalize()} ({pico:,.0f} m³).')
        if d['medidores_activos']:
            por_medidor = promedio / d['medidores_activos']
            texto += f' Eso da cerca de {por_medidor:,.1f} m³ al mes por medidor activo.'
        agregar('info', 'Consumo de agua', texto)

    # ── Forma de pago ───────────────────────────────────────────
    total_metodos = sum((m['total'] or CERO for m in d['metodos']), CERO)
    if total_metodos:
        partes = [f'{m["nombre"]} {_porcentaje(m["total"] or CERO, total_metodos)}%' for m in d['metodos']]
        agregar('info', 'Cómo pagan los socios',
                'Reparto de lo pagado por método: ' + ', '.join(partes) + '.')

    # ── Comparación con la gestión anterior ─────────────────────
    anterior = d['anterior']
    if anterior['ingresos'] or anterior['egresos']:
        partes = []
        for nombre, actual, antes in (('ingresos', ingresos, anterior['ingresos']),
                                      ('egresos', egresos, anterior['egresos'])):
            if antes:
                cambio = round((float(actual) - float(antes)) / float(antes) * 100)
                sentido = 'subieron' if cambio >= 0 else 'bajaron'
                partes.append(f'los {nombre} {sentido} {abs(cambio)}% ({_bs(antes)} → {_bs(actual)})')
        if partes:
            aviso = ''
            if d['meses_transcurridos'] < 12:
                aviso = (f' La gestión {anio} todavía no termina, así que la comparación '
                         f'con el año completo {anio - 1} es solo una referencia.')
            agregar('info', f'Comparado con {anio - 1}',
                    f'Frente a la gestión {anio - 1}, ' + ' y '.join(partes) + '.' + aviso)

    return frases


@login_required
@es_admin_o_tesorero
def reporte_general(request):
    anio = _anio_pedido(request)
    return render(request, 'reportes/general.html', {
        **_datos_reporte_general(anio),
        **_metadata_reporte(request),
    })
