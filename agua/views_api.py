from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Socio, Medidor, Recibo, Pago, Lectura, TransaccionQRBNB
from .serializers import (
    SocioPerfilSerializer,
    MedidorSocioSerializer,
    ReciboSocioSerializer,
    PagoSocioSerializer,
    LecturaResumenSerializer,
    TransaccionQRBNBSerializer,
)


# =============================================================
# FUNCIONES AUXILIARES
# =============================================================

def obtener_socio_de_usuario(user):
    """
    Obtiene el socio asociado al usuario autenticado.
    Sirve para que la app móvil muestre solo los datos del socio logueado.
    """
    try:
        return user.socio_perfil
    except Socio.DoesNotExist:
        return None
    except AttributeError:
        return None


def validar_usuario_socio(request):
    """
    Verifica que el usuario tenga rol socio y tenga un socio asociado.
    """
    if not request.user.is_authenticated:
        return None, Response(
            {'error': 'Usuario no autenticado.'},
            status=401
        )

    if getattr(request.user, 'rol', None) != 'socio':
        return None, Response(
            {'error': 'Este acceso es solo para usuarios con rol socio.'},
            status=403
        )

    socio = obtener_socio_de_usuario(request.user)

    if not socio:
        return None, Response(
            {'error': 'Este usuario no tiene un socio asociado.'},
            status=404
        )

    return socio, None


# =============================================================
# API SOCIO - PERFIL
# =============================================================

class SocioPerfilAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        estados_deuda = ['Pendiente', 'En Revision', 'En Revisión', 'Vencido']

        deuda_total = Recibo.objects.filter(
            socio=socio,
            estado_pago__in=estados_deuda
        ).aggregate(total=Sum('monto_total'))['total'] or Decimal('0.00')

        recibos_pendientes = Recibo.objects.filter(
            socio=socio,
            estado_pago__in=estados_deuda
        ).count()

        ultimo_recibo = Recibo.objects.select_related(
            'lectura',
            'lectura__medidor'
        ).filter(
            socio=socio
        ).order_by('-fecha_emision').first()

        ultimo_consumo = Decimal('0.00')
        ultimo_periodo = None

        if ultimo_recibo:
            ultimo_consumo = ultimo_recibo.lectura.consumo_cubos
            ultimo_periodo = ultimo_recibo.lectura.periodo_nombre

        return Response({
            'socio': SocioPerfilSerializer(socio).data,
            'deuda_total': deuda_total,
            'recibos_pendientes': recibos_pendientes,
            'ultimo_consumo': ultimo_consumo,
            'ultimo_periodo': ultimo_periodo,
        })


# =============================================================
# API SOCIO - MEDIDORES
# =============================================================

class SocioMedidoresAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        medidores = Medidor.objects.filter(
            Q(socio=socio) | Q(co_titulares=socio)
        ).distinct().order_by('numero_medidor')

        serializer = MedidorSocioSerializer(medidores, many=True)
        return Response(serializer.data)


# =============================================================
# API SOCIO - RECIBOS
# =============================================================

class SocioRecibosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        estado = request.GET.get('estado', '').strip()
        periodo = request.GET.get('periodo', '').strip()

        recibos = Recibo.objects.select_related(
            'socio',
            'lectura',
            'lectura__medidor'
        ).filter(
            socio=socio
        ).order_by('-fecha_emision')

        if estado:
            recibos = recibos.filter(estado_pago=estado)

        if periodo:
            recibos = recibos.filter(lectura__periodo=periodo)

        serializer = ReciboSocioSerializer(recibos, many=True)
        return Response(serializer.data)


class SocioReciboDetalleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        try:
            recibo = Recibo.objects.select_related(
                'socio',
                'lectura',
                'lectura__medidor'
            ).get(pk=pk, socio=socio)
        except Recibo.DoesNotExist:
            return Response(
                {'error': 'Recibo no encontrado.'},
                status=404
            )

        pagos = Pago.objects.filter(recibo=recibo).order_by('-fecha_pago')

        total_pagado = pagos.aggregate(
            total=Sum('monto_pagado')
        )['total'] or Decimal('0.00')

        saldo = recibo.monto_total - total_pagado

        return Response({
            'recibo': ReciboSocioSerializer(recibo).data,
            'pagos': PagoSocioSerializer(pagos, many=True).data,
            'total_pagado': total_pagado,
            'saldo': saldo,
        })


# =============================================================
# API SOCIO - PAGOS
# =============================================================

class SocioPagosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        pagos = Pago.objects.select_related(
            'recibo',
            'recibo__socio',
            'recibo__lectura',
            'recibo__lectura__medidor'
        ).filter(
            recibo__socio=socio
        ).order_by('-fecha_pago')

        serializer = PagoSocioSerializer(pagos, many=True)
        return Response(serializer.data)


# =============================================================
# API SOCIO - CONSUMO
# =============================================================

class SocioConsumoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        anio = request.GET.get('anio', '').strip()

        if not anio:
            anio = str(date.today().year)

        lecturas = Lectura.objects.select_related(
            'medidor',
            'medidor__socio'
        ).filter(
            Q(medidor__socio=socio) | Q(medidor__co_titulares=socio),
            periodo__startswith=anio
        ).distinct().order_by('periodo')

        consumo_total = Decimal('0.00')

        for lectura in lecturas:
            consumo_total += lectura.consumo_cubos

        return Response({
            'anio': anio,
            'consumo_total': consumo_total,
            'lecturas': LecturaResumenSerializer(lecturas, many=True).data,
        })


# =============================================================
# API SOCIO - ESTADO DE CUENTA ANUAL
# =============================================================

class SocioEstadoCuentaAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        anio = request.GET.get('anio', '').strip()

        if not anio:
            anio = str(date.today().year)

        recibos = Recibo.objects.select_related(
            'socio',
            'lectura',
            'lectura__medidor'
        ).filter(
            socio=socio,
            lectura__periodo__startswith=anio
        ).order_by('lectura__periodo')

        pagos = Pago.objects.filter(
            recibo__socio=socio,
            recibo__lectura__periodo__startswith=anio
        )

        consumo_total = Decimal('0.00')

        for recibo in recibos:
            consumo_total += recibo.lectura.consumo_cubos

        total_emitido = recibos.aggregate(
            total=Sum('monto_total')
        )['total'] or Decimal('0.00')

        total_pagado = pagos.aggregate(
            total=Sum('monto_pagado')
        )['total'] or Decimal('0.00')

        total_retrasos = recibos.aggregate(
            total=Sum('recargo_falta_pago')
        )['total'] or Decimal('0.00')

        total_pendiente = total_emitido - total_pagado

        return Response({
            'anio': anio,
            'socio': SocioPerfilSerializer(socio).data,
            'consumo_total': consumo_total,
            'total_emitido': total_emitido,
            'total_pagado': total_pagado,
            'total_retrasos': total_retrasos,
            'total_pendiente': total_pendiente,
            'recibos': ReciboSocioSerializer(recibos, many=True).data,
        })

# =============================================================
# API SOCIO - QR BNB NIVEL 3 PREPARADO
# =============================================================

def generar_qr_bnb_simulado(recibo, socio):
    """
    Simulación interna de generación QR BNB.
    Más adelante esta función se reemplaza por la llamada real a la API BNB.
    """

    referencia = f"RECIBO-{recibo.numero_recibo}-{recibo.lectura.periodo}"

    qr_id_banco = f"SIM-BNB-{recibo.numero_recibo}-{recibo.lectura.periodo}"

    qr_payload = (
        f"BNB|QR_SIMPLE|"
        f"RECIBO:{recibo.numero_recibo}|"
        f"SOCIO:{socio.ci}|"
        f"MONTO:{recibo.monto_total}|"
        f"PERIODO:{recibo.lectura.periodo}|"
        f"REF:{referencia}"
    )

    respuesta_banco = {
        'success': True,
        'modo': 'simulado',
        'message': 'QR generado en modo simulación. Reemplazar por API BNB real.',
        'qrId': qr_id_banco,
        'reference': referencia,
        'amount': str(recibo.monto_total),
        'currencyCode': 'BOB',
    }

    return {
        'referencia': referencia,
        'qr_id_banco': qr_id_banco,
        'qr_payload': qr_payload,
        'respuesta_banco': respuesta_banco,
    }


class SocioGenerarQRBNBAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        try:
            recibo = Recibo.objects.select_related(
                'socio',
                'lectura',
                'lectura__medidor'
            ).get(pk=pk, socio=socio)
        except Recibo.DoesNotExist:
            return Response(
                {'error': 'Recibo no encontrado.'},
                status=404
            )

        if recibo.estado_pago == 'Cancelado':
            return Response(
                {'error': 'Este recibo ya se encuentra cancelado.'},
                status=400
            )

        transaccion_existente = TransaccionQRBNB.objects.filter(
            recibo=recibo,
            socio=socio,
            estado__in=[
                TransaccionQRBNB.ESTADO_GENERADO,
                TransaccionQRBNB.ESTADO_PENDIENTE,
            ]
        ).first()

        if transaccion_existente:
            return Response({
                'mensaje': 'Ya existe un QR activo para este recibo.',
                'transaccion': TransaccionQRBNBSerializer(transaccion_existente).data
            })

        datos_qr = generar_qr_bnb_simulado(recibo, socio)

        transaccion = TransaccionQRBNB.objects.create(
            recibo=recibo,
            socio=socio,
            monto=recibo.monto_total,
            referencia=datos_qr['referencia'],
            qr_id_banco=datos_qr['qr_id_banco'],
            qr_payload=datos_qr['qr_payload'],
            estado=TransaccionQRBNB.ESTADO_GENERADO,
            ambiente=TransaccionQRBNB.AMBIENTE_SANDBOX,
            respuesta_banco=datos_qr['respuesta_banco'],
        )

        return Response({
            'mensaje': 'QR generado correctamente en modo simulación.',
            'transaccion': TransaccionQRBNBSerializer(transaccion).data
        }, status=201)


class SocioConsultarQRBNBAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        try:
            transaccion = TransaccionQRBNB.objects.select_related(
                'recibo',
                'recibo__lectura',
                'socio'
            ).get(pk=pk, socio=socio)
        except TransaccionQRBNB.DoesNotExist:
            return Response(
                {'error': 'Transacción QR no encontrada.'},
                status=404
            )

        return Response({
            'transaccion': TransaccionQRBNBSerializer(transaccion).data
        })


class SocioMisQRBNBAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        socio, error = validar_usuario_socio(request)
        if error:
            return error

        transacciones = TransaccionQRBNB.objects.select_related(
            'recibo',
            'recibo__lectura',
            'socio'
        ).filter(
            socio=socio
        ).order_by('-fecha_creacion')

        serializer = TransaccionQRBNBSerializer(transacciones, many=True)

        return Response(serializer.data)    