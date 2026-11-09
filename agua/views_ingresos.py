"""
Ingresos extra: dinero que entra al comité fuera de los cobros de agua y de
las afiliaciones (venta de materiales sobrantes, donaciones, alquileres...).

Funciona igual que los egresos: se registran con categoría y respaldo, se
pueden editar y, si no corresponden, se ANULAN con motivo (nunca se borran).
Los anulados no suman en ningún total. Suman en el Dashboard, el Balance, el
Reporte General y el backup.
"""
from decimal import Decimal, InvalidOperation

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import CategoriaIngreso, IngresoExtra
from .ticket import Ticket, bs, monto_a_literal
from .views_egresos import _hoja_con_tabla, _respuesta_excel
from .views_web import es_admin_o_tesorero, es_solo_admin

CERO = Decimal('0.00')


def total_ingresos_extra(consulta):
    """Suma solo los ingresos extra vigentes: los anulados no cuentan."""
    return consulta.filter(anulado=False).aggregate(total=Sum('monto'))['total'] or CERO


# =============================================================
# LISTA, REGISTRO, EDICIÓN Y ANULACIÓN
# =============================================================

def _ingresos_filtrados(request):
    """Ingresos extra según los filtros de la pantalla (los usa la lista y el Excel)."""
    filtros = {
        'fecha_inicio': request.GET.get('fecha_inicio', '').strip(),
        'fecha_fin': request.GET.get('fecha_fin', '').strip(),
        'categoria': request.GET.get('categoria', '').strip(),
        'metodo': request.GET.get('metodo', '').strip(),
        'q': request.GET.get('q', '').strip(),
    }
    ingresos = IngresoExtra.objects.select_related('categoria', 'registrado_por')

    fi = parse_date(filtros['fecha_inicio']) if filtros['fecha_inicio'] else None
    if fi:
        ingresos = ingresos.filter(fecha__gte=fi)
    ff = parse_date(filtros['fecha_fin']) if filtros['fecha_fin'] else None
    if ff:
        ingresos = ingresos.filter(fecha__lte=ff)
    if filtros['categoria'].isdigit():
        ingresos = ingresos.filter(categoria_id=int(filtros['categoria']))
    if filtros['metodo'] in dict(IngresoExtra.METODO_CHOICES):
        ingresos = ingresos.filter(metodo=filtros['metodo'])
    if filtros['q']:
        ingresos = ingresos.filter(
            Q(descripcion__icontains=filtros['q']) |
            Q(recibido_de__icontains=filtros['q'])
        )
    return ingresos, filtros


@login_required
@es_admin_o_tesorero
def ingresos_extra_lista(request):
    ingresos, filtros = _ingresos_filtrados(request)
    pagina = Paginator(ingresos, 50).get_page(request.GET.get('page'))

    parametros = request.GET.copy()
    parametros.pop('page', None)

    return render(request, 'ingresos_extra/lista.html', {
        'pagina': pagina,
        'total': total_ingresos_extra(ingresos),
        'cantidad': ingresos.filter(anulado=False).count(),
        'categorias': CategoriaIngreso.objects.all(),
        'metodos': IngresoExtra.METODO_CHOICES,
        'parametros': parametros.urlencode(),
        **filtros,
    })


def _guardar_ingreso(request, ingreso):
    """Valida el formulario y guarda. Devuelve True si se guardó; si no, deja el error."""
    fecha = parse_date(request.POST.get('fecha', '').strip() or '')
    categoria_id = request.POST.get('categoria', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()
    recibido_de = request.POST.get('recibido_de', '').strip()
    metodo = request.POST.get('metodo', '').strip()
    foto = request.FILES.get('foto_respaldo')

    try:
        monto = Decimal(request.POST.get('monto', '').strip().replace(',', '.'))
    except InvalidOperation:
        monto = None

    categoria = None
    if categoria_id.isdigit():
        categoria = CategoriaIngreso.objects.filter(pk=int(categoria_id)).first()

    if not fecha:
        messages.error(request, 'La fecha del ingreso es obligatoria.')
    elif fecha > timezone.localdate():
        messages.error(request, 'La fecha del ingreso no puede ser una fecha futura.')
    elif not categoria:
        messages.error(request, 'Elige la categoría del ingreso.')
    elif not descripcion:
        messages.error(request, 'Escribe qué se vendió o de qué es el ingreso.')
    elif metodo not in dict(IngresoExtra.METODO_CHOICES):
        messages.error(request, 'Elige cómo entró el dinero (efectivo, QR o transferencia).')
    elif monto is None or monto <= 0:
        messages.error(request, 'El monto debe ser un número mayor a cero.')
    elif monto >= Decimal('100000000'):
        messages.error(request, 'El monto es demasiado grande.')
    elif foto and not (foto.content_type or '').startswith('image/'):
        messages.error(request, 'El respaldo debe ser una imagen (foto del recibo o documento).')
    else:
        ingreso.fecha = fecha
        ingreso.categoria = categoria
        ingreso.descripcion = descripcion[:255]
        ingreso.recibido_de = recibido_de[:150]
        ingreso.metodo = metodo
        ingreso.monto = monto.quantize(Decimal('0.01'))
        if foto:
            ingreso.foto_respaldo = foto
        if not ingreso.pk:
            ingreso.registrado_por = request.user
        ingreso.save()
        return True
    return False


def _contexto_form(request, accion, ingreso=None):
    """Si el guardado falló, se vuelve a mostrar lo escrito para no llenar todo de nuevo."""
    datos = request.POST if request.method == 'POST' else None
    categorias = CategoriaIngreso.objects.filter(
        Q(activo=True) | Q(pk=ingreso.categoria_id if ingreso else None)
    )

    def valor(campo, desde_objeto):
        if datos is not None:
            return datos.get(campo, '')
        return desde_objeto if ingreso else ''

    return {
        'accion': accion,
        'ingreso': ingreso,
        'categorias': categorias,
        'metodos': IngresoExtra.METODO_CHOICES,
        'valor_fecha': datos.get('fecha', '') if datos else (
            ingreso.fecha.isoformat() if ingreso else timezone.localdate().isoformat()),
        'valor_categoria': valor('categoria', str(ingreso.categoria_id) if ingreso else ''),
        'valor_descripcion': valor('descripcion', ingreso.descripcion if ingreso else ''),
        'valor_recibido_de': valor('recibido_de', ingreso.recibido_de if ingreso else ''),
        'valor_metodo': datos.get('metodo', '') if datos else (ingreso.metodo if ingreso else 'efectivo'),
        'valor_monto': valor('monto', str(ingreso.monto) if ingreso else ''),
    }


@login_required
@es_admin_o_tesorero
def ingreso_extra_crear(request):
    if request.method == 'POST':
        ingreso = IngresoExtra()
        if _guardar_ingreso(request, ingreso):
            messages.success(request, f'Ingreso extra de Bs {ingreso.monto} registrado correctamente.')
            # Se abre el comprobante para imprimirlo y entregarlo.
            return redirect('ingreso_extra_imprimir', ingreso.pk)
    return render(request, 'ingresos_extra/form.html', _contexto_form(request, 'Registrar'))


@login_required
@es_admin_o_tesorero
def ingreso_extra_editar(request, pk):
    ingreso = get_object_or_404(IngresoExtra, pk=pk)
    if ingreso.anulado:
        messages.warning(request, 'Este ingreso está anulado y ya no se puede modificar.')
        return redirect('ingresos_extra_lista')

    if request.method == 'POST' and _guardar_ingreso(request, ingreso):
        messages.success(request, 'Ingreso extra actualizado correctamente.')
        return redirect('ingresos_extra_lista')
    return render(request, 'ingresos_extra/form.html', _contexto_form(request, 'Editar', ingreso))


@login_required
@es_admin_o_tesorero
def ingreso_extra_anular(request, pk):
    ingreso = get_object_or_404(IngresoExtra.objects.select_related('categoria'), pk=pk)
    if ingreso.anulado:
        messages.warning(request, 'Este ingreso ya estaba anulado.')
        return redirect('ingresos_extra_lista')

    if request.method == 'POST':
        motivo = request.POST.get('motivo_anulacion', '').strip()
        if not motivo:
            messages.error(request, 'Escribe el motivo de la anulación.')
        else:
            ingreso.anulado = True
            ingreso.motivo_anulacion = motivo[:255]
            ingreso.save()
            messages.success(request, f'Ingreso extra N.º {ingreso.pk} anulado. Ya no suma en los totales.')
            return redirect('ingresos_extra_lista')
    return render(request, 'ingresos_extra/anular.html', {'ingreso': ingreso})


# =============================================================
# COMPROBANTE PARA LA IMPRESORA TÉRMICA
# =============================================================

def _ticket_ingreso(ingreso):
    t = Ticket()
    t.centro('COMITÉ DE AGUA POTABLE', negrita=True)
    t.centro('Junta Vecinal "Paraíso"')
    t.raya('=')
    t.centro('COMPROBANTE DE INGRESO')
    t.centro(f'N° {ingreso.pk:04d}', negrita=True, grande=True)
    if ingreso.anulado:
        t.centro('*** ANULADO ***', negrita=True)
    t.raya()
    t.fila('Fecha:', ingreso.fecha.strftime('%d/%m/%Y'))
    t.fila('Categoría:', ingreso.categoria.nombre)
    if ingreso.recibido_de:
        t.fila('Recibido de:', ingreso.recibido_de)
    t.fila('Método:', ingreso.get_metodo_display())
    t.raya()
    t.texto('Concepto:', negrita=True)
    t.texto(ingreso.descripcion)
    t.raya('=')
    t.centro('MONTO RECIBIDO')
    t.centro(bs(ingreso.monto), negrita=True, grande=True)
    t.centro(monto_a_literal(ingreso.monto))
    t.raya('=')
    if ingreso.registrado_por:
        t.fila('Registrado por:', ingreso.registrado_por.get_full_name() or ingreso.registrado_por.username)
    t.fila('Impreso:', timezone.localtime().strftime('%d/%m/%Y %H:%M'))
    t.raya()
    t.centro('Sistema de Agua Potable')
    t.centro('Junta Vecinal "Paraíso"')
    return t


@login_required
@es_admin_o_tesorero
def ingreso_extra_imprimir(request, pk):
    ingreso = get_object_or_404(IngresoExtra.objects.select_related('categoria', 'registrado_por'), pk=pk)
    return render(request, 'cobros/imprimir_termico.html', {
        'ticket': _ticket_ingreso(ingreso).lineas,
        'titulo_ticket': f'Ingreso extra #{ingreso.pk}',
        'url_volver': reverse('ingresos_extra_lista'),
    })


# =============================================================
# CATEGORÍAS — solo el administrador
# =============================================================

@login_required
@es_solo_admin
def categorias_ingreso(request):
    if request.method == 'POST':
        accion = request.POST.get('accion')
        nombre = ' '.join(request.POST.get('nombre', '').split())[:80]

        if accion == 'crear':
            if not nombre:
                messages.error(request, 'Escribe el nombre de la categoría.')
            elif CategoriaIngreso.objects.filter(nombre__iexact=nombre).exists():
                messages.error(request, f'Ya existe la categoría "{nombre}".')
            else:
                CategoriaIngreso.objects.create(nombre=nombre)
                messages.success(request, f'Categoría "{nombre}" creada.')

        elif accion in ('renombrar', 'cambiar_estado'):
            categoria = get_object_or_404(CategoriaIngreso, pk=request.POST.get('pk') or 0)
            if accion == 'cambiar_estado':
                categoria.activo = not categoria.activo
                categoria.save()
                estado = 'activada' if categoria.activo else 'desactivada'
                messages.success(request, f'Categoría "{categoria.nombre}" {estado}.')
            elif not nombre:
                messages.error(request, 'El nombre de la categoría no puede quedar vacío.')
            elif CategoriaIngreso.objects.filter(nombre__iexact=nombre).exclude(pk=categoria.pk).exists():
                messages.error(request, f'Ya existe otra categoría llamada "{nombre}".')
            else:
                categoria.nombre = nombre
                categoria.save()
                messages.success(request, 'Categoría actualizada.')
        return redirect('categorias_ingreso')

    return render(request, 'ingresos_extra/categorias.html', {
        'categorias': CategoriaIngreso.objects.all(),
    })


# =============================================================
# EXCEL
# =============================================================

@login_required
@es_admin_o_tesorero
def ingresos_extra_excel(request):
    ingresos, filtros = _ingresos_filtrados(request)

    titulo = 'REPORTE DE INGRESOS EXTRA'
    if filtros['fecha_inicio'] or filtros['fecha_fin']:
        titulo += f" — desde {filtros['fecha_inicio'] or 'el inicio'} hasta {filtros['fecha_fin'] or 'hoy'}"

    filas = []
    for i in ingresos:
        registrado_por = ''
        if i.registrado_por:
            registrado_por = i.registrado_por.get_full_name() or i.registrado_por.username
        filas.append([
            i.pk, i.fecha.strftime('%d/%m/%Y'), i.categoria.nombre, i.descripcion,
            i.recibido_de, i.get_metodo_display(), float(i.monto),
            f'Anulado: {i.motivo_anulacion}' if i.anulado else 'Vigente', registrado_por,
        ])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Ingresos extra'
    _hoja_con_tabla(
        ws, titulo,
        ['N.º', 'Fecha', 'Categoría', 'Descripción', 'Recibido de', 'Método',
         'Monto Bs', 'Estado', 'Registrado por'],
        filas,
        fila_total=['', '', '', '', '', 'TOTAL (sin anulados)',
                    float(total_ingresos_extra(ingresos)), '', ''],
        columnas_monto=(7,),
    )
    return _respuesta_excel(wb, f'ingresos_extra_{timezone.localdate():%Y%m%d}.xlsx')


# =============================================================
# BACKUP: hoja para exportar e importar
# =============================================================

COLUMNAS_PLANTILLA = ['fecha', 'categoria', 'descripcion', 'recibido_de', 'metodo', 'monto']
COLUMNAS_BACKUP = ['N°', 'Fecha', 'Categoría', 'Descripción', 'Recibido de', 'Método', 'Monto (Bs)',
                   'Tiene Foto', 'Anulado', 'Motivo Anulación', 'Registrado por', 'Fecha Registro']


def filas_backup():
    """Filas de la hoja 'Ingresos Extra' del backup (incluye los anulados)."""
    for i in IngresoExtra.objects.select_related('categoria', 'registrado_por').order_by('fecha', 'pk'):
        yield [
            i.pk, i.fecha.strftime('%d/%m/%Y'), i.categoria.nombre, i.descripcion, i.recibido_de,
            i.get_metodo_display(), float(i.monto),
            'Sí' if i.foto_respaldo else 'No',
            'Sí' if i.anulado else 'No', i.motivo_anulacion,
            (i.registrado_por.get_full_name() or i.registrado_por.username) if i.registrado_por else '',
            timezone.localtime(i.fecha_registro).strftime('%d/%m/%Y %H:%M') if i.fecha_registro else '',
        ]


def _a_fecha(valor):
    """Fecha de una celda de Excel: puede venir como fecha, '31/12/2026' o '2026-12-31'."""
    from datetime import datetime
    if hasattr(valor, 'hour'):
        return valor.date()
    if hasattr(valor, 'year'):
        return valor
    texto = str(valor or '').strip()
    for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _a_metodo(valor):
    texto = str(valor or '').strip().lower()
    for clave, nombre in IngresoExtra.METODO_CHOICES:
        if texto in (clave, nombre.lower()):
            return clave
    return 'efectivo'


def importar_hoja(ws, usuario):
    """
    Carga la hoja 'Ingresos Extra' de un Excel. Acepta las columnas de la
    plantilla vacía y las del backup del sistema (así un backup se puede
    volver a cargar). Si un ingreso ya existe (misma fecha, categoría,
    descripción y monto) no se repite. Devuelve cuántos se crearon.
    """
    encabezados = [str(c or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True), [])]
    if [e.lower() for e in encabezados[:3]] == COLUMNAS_PLANTILLA[:3]:
        formato = 'plantilla'
    elif encabezados[:3] == COLUMNAS_BACKUP[:3]:
        formato = 'backup'
    else:
        return 0

    creados = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        row = list(row or []) + [None] * 12
        if formato == 'plantilla':
            fecha, categoria, descripcion, recibido_de, metodo, monto = row[:6]
            anulado, motivo = False, ''
        else:
            _, fecha, categoria, descripcion, recibido_de, metodo, monto, _, anulado, motivo = row[:10]
            anulado = str(anulado or '').strip().lower() in ('sí', 'si', 'true', '1')
        fecha = _a_fecha(fecha)
        if not fecha or not categoria or not descripcion or monto in (None, ''):
            continue
        try:
            monto = Decimal(str(monto).replace(',', '.')).quantize(Decimal('0.01'))
        except InvalidOperation:
            continue
        if monto <= 0:
            continue

        nombre_categoria = ' '.join(str(categoria).split())[:80]
        cat = CategoriaIngreso.objects.filter(nombre__iexact=nombre_categoria).first()
        if not cat:
            cat = CategoriaIngreso.objects.create(nombre=nombre_categoria)
        descripcion = str(descripcion).strip()[:255]

        if IngresoExtra.objects.filter(fecha=fecha, categoria=cat, descripcion=descripcion, monto=monto).exists():
            continue
        IngresoExtra.objects.create(
            fecha=fecha, categoria=cat, descripcion=descripcion,
            recibido_de=str(recibido_de or '').strip()[:150],
            metodo=_a_metodo(metodo), monto=monto,
            anulado=anulado, motivo_anulacion=str(motivo or '').strip()[:255] if anulado else '',
            registrado_por=usuario,
        )
        creados += 1
    return creados
