from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

import requests
from django.conf import settings
from datetime import date, timedelta

from .views_web import llamar_ocr_space

from .models import Medidor, Socio, Tarifa, Lectura, Recibo, Pago, QRGenerico
from .serializers import (
    UsuarioSerializer, UsuarioCrearSerializer,
    CambiarPasswordSerializer, ResetPasswordAdminSerializer,
    SocioSerializer, MedidorSerializer, TarifaSerializer,
    LecturaSerializer, ReciboSerializer, ReciboSocioSerializer,
    PagoSerializer,
)
from .permissions import EsAdmin, EsLector, EsSocio

Usuario = get_user_model()


# =============================================================
# PERMISOS HELPERS
# =============================================================

def es_admin(user):
    return user.is_authenticated and user.rol == 'admin'

def es_lector(user):
    return user.is_authenticated and user.rol == 'lector'

def es_socio(user):
    return user.is_authenticated and user.rol == 'socio'


# =============================================================
# USUARIOS
# =============================================================

class UsuarioViewSet(viewsets.ModelViewSet):
    """
    Solo el admin puede crear, ver y editar usuarios.
    """
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'ci', 'rol']
    ordering_fields = ['last_name', 'rol', 'fecha_registro']
    ordering = ['last_name']

    def get_serializer_class(self):
        if self.action == 'create':
            return UsuarioCrearSerializer
        return UsuarioSerializer

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        """Admin resetea la contrasena de cualquier usuario."""
        usuario = self.get_object()
        serializer = ResetPasswordAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario.set_password(serializer.validated_data['password_nuevo'])
        usuario.save()
        return Response({'mensaje': 'Contraseña restablecida correctamente.'})

    @action(detail=False, methods=['post'], url_path='cambiar-password',
            permission_classes=[IsAuthenticated])
    def cambiar_password(self, request):
        """Cualquier usuario cambia su propia contrasena."""
        serializer = CambiarPasswordSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'mensaje': 'Contraseña cambiada correctamente.'})

    @action(detail=False, methods=['get'], url_path='perfil',
            permission_classes=[IsAuthenticated])
    def perfil(self, request):
        """Devuelve los datos del usuario autenticado."""
        serializer = UsuarioSerializer(request.user)
        return Response(serializer.data)


# =============================================================
# SOCIOS
# =============================================================

class SocioViewSet(viewsets.ModelViewSet):
    queryset = Socio.objects.all()
    serializer_class = SocioSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['ci', 'codigo_cliente', 'nombre_completo']
    ordering_fields = ['nombre_completo', 'ci', 'fecha_registro']
    ordering = ['nombre_completo']

    @action(detail=True, methods=['get'], url_path='medidores')
    def medidores(self, request, pk=None):
        """Medidores donde este socio es titular o co-titular."""
        socio = self.get_object()
        medidores = Medidor.objects.filter(
            Q(socio=socio) | Q(co_titulares=socio)
        ).distinct()
        serializer = MedidorSerializer(medidores, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='recibos')
    def recibos(self, request, pk=None):
        """Recibos del socio ordenados del mas reciente al mas antiguo."""
        socio = self.get_object()
        recibos = socio.recibos.all().order_by('-fecha_emision')
        serializer = ReciboSerializer(recibos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='deuda-total')
    def deuda_total(self, request, pk=None):
        """Suma de recibos pendientes del socio."""
        socio = self.get_object()
        pendientes = socio.recibos.filter(
            estado_pago__in=['Pendiente', 'En Revision', 'Vencido']
        )
        total = pendientes.aggregate(total=Sum('monto_total'))['total'] or 0
        return Response({
            'socio': socio.nombre_completo,
            'deuda_total': total,
            'recibos_pendientes': pendientes.count(),
        })


# =============================================================
# MEDIDORES
# =============================================================

class MedidorViewSet(viewsets.ModelViewSet):
    queryset = Medidor.objects.select_related('socio').all()
    serializer_class = MedidorSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'numero_medidor', 'manzano', 'parcela',
        'socio__nombre_completo', 'socio__ci',
    ]
    ordering_fields = ['numero_medidor', 'manzano', 'parcela', 'estado']
    ordering = ['numero_medidor']

    @action(detail=True, methods=['get'], url_path='lecturas')
    def lecturas(self, request, pk=None):
        """Historial de lecturas del medidor."""
        medidor = self.get_object()
        lecturas = medidor.lecturas.all().order_by('-fecha_lectura')
        serializer = LecturaSerializer(lecturas, many=True)
        return Response(serializer.data)


# =============================================================
# TARIFAS
# =============================================================

class TarifaViewSet(viewsets.ModelViewSet):
    queryset = Tarifa.objects.all()
    serializer_class = TarifaSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre']
    ordering = ['-id_tarifa']

    @action(detail=False, methods=['get'], url_path='vigente',
            permission_classes=[IsAuthenticated])
    def vigente(self, request):
        """Devuelve la tarifa activa mas reciente."""
        tarifa = Tarifa.objects.filter(activa=True).order_by('-id_tarifa').first()
        if tarifa is None:
            return Response(
                {'detalle': 'No hay tarifa activa registrada.'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(TarifaSerializer(tarifa).data)


# =============================================================
# LECTURAS
# Solo el admin y el lector pueden registrar lecturas.
# =============================================================

class LecturaViewSet(viewsets.ModelViewSet):
    queryset = Lectura.objects.select_related(
        'medidor', 'medidor__socio', 'creado_por'
    ).all()
    serializer_class = LecturaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'periodo',
        'medidor__numero_medidor',
        'medidor__socio__nombre_completo',
    ]
    ordering_fields = ['fecha_lectura', 'periodo', 'consumo_cubos']
    ordering = ['-fecha_lectura']

    def get_permissions(self):
        """
        Crear/editar/eliminar: solo admin o lector.
        Ver: cualquier autenticado (los socios ven a traves de su propio endpoint).
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), EsAdmin() if es_admin(self.request.user)
                    else EsLector()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        medidor_id = self.request.query_params.get('medidor')
        periodo = self.request.query_params.get('periodo')
        if medidor_id:
            queryset = queryset.filter(medidor_id=medidor_id)
        if periodo:
            queryset = queryset.filter(periodo__icontains=periodo)
        return queryset


# =============================================================
# RECIBOS
# =============================================================

class ReciboViewSet(viewsets.ModelViewSet):
    queryset = Recibo.objects.select_related(
        'socio', 'lectura', 'lectura__medidor'
    ).all()
    serializer_class = ReciboSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'numero_recibo',
        'socio__ci',
        'socio__nombre_completo',
        'lectura__periodo',
    ]
    ordering_fields = ['fecha_emision', 'numero_recibo', 'monto_total', 'estado_pago']
    ordering = ['-fecha_emision', '-numero_recibo']

    def get_queryset(self):
        queryset = super().get_queryset()
        socio_id = self.request.query_params.get('socio')
        estado = self.request.query_params.get('estado')
        numero = self.request.query_params.get('numero')
        if socio_id:
            queryset = queryset.filter(socio_id=socio_id)
        if estado:
            queryset = queryset.filter(estado_pago=estado)
        if numero:
            queryset = queryset.filter(numero_recibo=numero)
        return queryset

    @action(detail=False, methods=['get'], url_path='pendientes')
    def pendientes(self, request):
        """Todos los recibos con deuda pendiente (para el panel web)."""
        recibos = self.get_queryset().filter(
            estado_pago__in=['Pendiente', 'En Revision', 'Vencido']
        )
        serializer = ReciboSerializer(recibos, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='pagos')
    def pagos(self, request, pk=None):
        """Pagos registrados para este recibo."""
        recibo = self.get_object()
        serializer = PagoSerializer(recibo.pagos.all(), many=True)
        return Response(serializer.data)


# =============================================================
# PAGOS
# =============================================================

class PagoViewSet(viewsets.ModelViewSet):
    queryset = Pago.objects.select_related(
        'recibo', 'recibo__socio', 'registrado_por'
    ).all()
    serializer_class = PagoSerializer
    permission_classes = [IsAuthenticated, EsAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'recibo__numero_recibo',
        'recibo__socio__nombre_completo',
        'metodo_pago',
    ]
    ordering_fields = ['fecha_pago', 'monto_pagado', 'metodo_pago']
    ordering = ['-fecha_pago']

    def get_queryset(self):
        queryset = super().get_queryset()
        recibo_id = self.request.query_params.get('recibo')
        metodo = self.request.query_params.get('metodo')
        if recibo_id:
            queryset = queryset.filter(recibo_id=recibo_id)
        if metodo:
            queryset = queryset.filter(metodo_pago=metodo)
        return queryset


# =============================================================
# APP MOVIL — SOCIO
# Endpoints que usa la app Flutter del socio.
# El socio solo puede ver sus propios datos.
# =============================================================

class MiCuentaViewSet(viewsets.ViewSet):
    """
    Endpoints para la app del socio.
    El socio autenticado accede a su historial, recibos y deudas.
    """
    permission_classes = [IsAuthenticated]

    def _get_socio(self, user):
        """Obtiene el perfil de socio del usuario autenticado."""
        try:
            return user.socio_perfil
        except Socio.DoesNotExist:
            return None

    @action(detail=False, methods=['get'], url_path='mis-medidores')
    def mis_medidores(self, request):
        socio = self._get_socio(request.user)
        if not socio:
            return Response(
                {'detalle': 'No tienes un perfil de socio asociado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        medidores = Medidor.objects.filter(
            Q(socio=socio) | Q(co_titulares=socio)
        ).distinct()
        return Response(MedidorSerializer(medidores, many=True).data)

    @action(detail=False, methods=['get'], url_path='mis-recibos')
    def mis_recibos(self, request):
        socio = self._get_socio(request.user)
        if not socio:
            return Response(
                {'detalle': 'No tienes un perfil de socio asociado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        recibos = socio.recibos.all().order_by('-fecha_emision')
        return Response(ReciboSocioSerializer(recibos, many=True).data)

    @action(detail=False, methods=['get'], url_path='mi-deuda')
    def mi_deuda(self, request):
        socio = self._get_socio(request.user)
        if not socio:
            return Response(
                {'detalle': 'No tienes un perfil de socio asociado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        pendientes = socio.recibos.filter(
            estado_pago__in=['Pendiente', 'En Revision', 'Vencido']
        )
        total = pendientes.aggregate(total=Sum('monto_total'))['total'] or 0
        return Response({
            'deuda_total': total,
            'recibos_pendientes': pendientes.count(),
        })

    @action(detail=False, methods=['get'], url_path='mi-historial')
    def mi_historial(self, request):
        """Historial de consumos del socio (para graficas en la app)."""
        socio = self._get_socio(request.user)
        if not socio:
            return Response(
                {'detalle': 'No tienes un perfil de socio asociado.'},
                status=status.HTTP_404_NOT_FOUND
            )
        medidores = Medidor.objects.filter(
            Q(socio=socio) | Q(co_titulares=socio)
        ).distinct()
        lecturas = Lectura.objects.filter(
            medidor__in=medidores
        ).order_by('-fecha_lectura').values(
            'periodo', 'consumo_cubos', 'lectura_actual',
            'fecha_lectura', 'medidor__numero_medidor'
        )
        return Response(list(lecturas))
    
    @action(detail=True, methods=['get'], url_path='obtener-qr-generico')
    def obtener_qr_generico(self, request, pk=None):
        """
        Endpoint que busca el QR genérico correspondiente al monto del recibo.
        Si la deuda es de 30 Bs, busca el QR de 30 Bs y envía la imagen a la app.
        """
        socio = self._get_socio(request.user)
        if not socio:
            return Response({'error': 'No tienes perfil de socio.'}, status=404)

        try:
            # Buscamos el recibo que el socio quiere pagar
            recibo = socio.recibos.get(pk=pk)
        except Exception:
            return Response({'error': 'Recibo no encontrado.'}, status=404)

        monto_deuda = recibo.monto_total

        # Buscamos en la base de datos si existe un QR activo para ese monto exacto
        qr_match = QRGenerico.objects.filter(monto=monto_deuda, activo=True).first()

        if not qr_match:
            return Response({
                'error': f'No hay un QR configurado para el monto exacto de {monto_deuda} Bs. Por favor, comunícate con la junta vecinal o paga en oficinas.'
            }, status=404)

        # Si el QR existe, construimos el enlace completo (http://...) para que Flutter pueda dibujar la imagen
        url_imagen_qr = request.build_absolute_uri(qr_match.imagen_qr.url)

        return Response({
            'exitoso': True,
            'qr_image_url': url_imagen_qr,
            'referencia': f"Recibo #{recibo.numero_recibo}",
            'monto': str(monto_deuda),
            'estado': 'Generado',
            'periodo_nombre': recibo.lectura.periodo
        })
    
    @action(detail=True, methods=['post'], url_path='validar-pago-ocr')
    def validar_pago_ocr(self, request, pk=None):
        """
        El cerebro del sistema: Recibe el comprobante, lo lee con IA,
        busca fraudes, valida el monto y registra el pago.
        """
        socio = self._get_socio(request.user)
        if not socio:
            return Response({'error': 'No tienes perfil de socio.'}, status=404)

        try:
            recibo = socio.recibos.get(pk=pk)
        except Exception:
            return Response({'error': 'Recibo no encontrado.'}, status=404)

        foto = request.FILES.get('comprobante')
        if not foto:
            return Response({'error': 'Debe adjuntar la foto del comprobante.'}, status=400)

        # 1. Llamar a la IA (OCR) para leer la imagen
        resultado_ocr = llamar_ocr_space(foto.read())
        
        if not resultado_ocr['exitoso']:
            return Response({'error': resultado_ocr.get('error', 'Error al procesar la imagen.')}, status=400)

        texto_detectado = resultado_ocr.get('texto', '').upper()
        monto_deuda = recibo.monto_total

        # =========================================================
        # 2. EL ESCUDO ANTI-FRAUDE (Análisis de Texto)
        # =========================================================
        
        # A) Validar Monto: Buscamos si el monto exacto está impreso en el ticket
        # Cubrimos varios formatos, ej para 30 Bs: "30", "30.00", "30,00"
        monto_str_1 = str(int(monto_deuda)) 
        monto_str_2 = f"{monto_deuda:.2f}"  
        monto_str_3 = monto_str_2.replace('.', ',') 

        if not (monto_str_1 in texto_detectado or monto_str_2 in texto_detectado or monto_str_3 in texto_detectado):
            return Response({
                'error': f'Fraude detectado o foto borrosa: No se encontró el monto exacto de {monto_deuda} Bs. en el comprobante.'
            }, status=400)

        # B) Cazador de Transacciones (El escudo anti-vecinos vivos)
        # Los números de comprobante de los bancos suelen tener entre 6 y 20 dígitos seguidos.
        numeros_largos = re.findall(r'\b\d{6,20}\b', texto_detectado)
        
        if numeros_largos:
            # Tomamos el número más largo como el ID de transacción del banco
            nro_transaccion = max(numeros_largos, key=len) 
        else:
            # Si el banco usa letras y números, generamos un código de emergencia
            nro_transaccion = f"MANUAL-OCR-{date.today().strftime('%Y%m%d')}-{recibo.pk}"

        # C) Validar Duplicados
        # Buscamos en la base de datos si alguien ya usó este número de transacción
        if Pago.objects.filter(metodo_pago='qr', registrado_por__isnull=False, recibo__pagos__isnull=False).filter(
            # Buscamos en una nota secreta si este comprobante ya pasó por aquí
            foto_comprobante__icontains=nro_transaccion 
        ).exists():
            return Response({
                'error': '¡Alerta de Seguridad! Este comprobante ya fue utilizado por otro socio.'
            }, status=403)

        # =========================================================
        # 3. REGISTRO EXITOSO DEL PAGO
        # =========================================================
        try:
            pago = Pago.objects.create(
                recibo=recibo,
                monto_pagado=monto_deuda,
                metodo_pago='qr', 
                foto_comprobante=foto,
                registrado_por=request.user, 
            )
            
            # Guardamos el nro de transacción en un campo interno para evitar que se repita
            if hasattr(pago, 'observacion'):
                pago.observacion = f"Validado por IA. Nro Transacción: {nro_transaccion}"
                pago.save()

            return Response({
                'exitoso': True,
                'mensaje': '¡Comprobante verificado con Inteligencia Artificial! El pago ha sido registrado.',
                'nro_transaccion': nro_transaccion
            })
            
        except Exception as e:
            return Response({'error': f'Error al guardar el pago: {str(e)}'}, status=500)
    @action(detail=True, methods=['post'], url_path='generar-qr-bnb')
    def generar_qr_bnb(self, request, pk=None):
        from datetime import date, timedelta
        import requests
        
        try:
            socio = self._get_socio(request.user)
            if not socio:
                return Response({'error': 'No tienes perfil de socio.'}, status=404)

            recibo = socio.recibos.get(pk=pk)

            # 1. Pedir Token al BNB
            url_token = "http://test.bnb.com.bo/ClientAuthentication.API/api/v1/auth/token"
            credenciales = {
                "accountId": "s9CG8FE7Id75ef2jeX9bUA==", # Credencial de prueba
                "authorizationId": "713K7PvTIACs1gdmv9jGgA==" # Clave de prueba
            }
            res_token = requests.post(url_token, json=credenciales, timeout=10)
            res_token.raise_for_status()
            token_banco = res_token.json().get('message')

            # 2. Pedir Imagen QR al BNB
            url_qr = "http://test.bnb.com.bo/QRSimple.API/api/v1/main/getQRWithImageAsync"
            headers_qr = {
                "Authorization": f"Bearer {token_banco}",
                "Content-Type": "application/json"
            }
            
            fecha_expiracion = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
            datos_pago = {
                "currency": "BOB",
                "gloss": f"Pago Agua - Recibo {recibo.numero_recibo}",
                "amount": float(recibo.monto_total),
                "singleUse": True,
                "expirationDate": fecha_expiracion,
                "additionalData": str(recibo.pk),
                "destinationAccountId": "1" 
            }

            res_qr = requests.post(url_qr, headers=headers_qr, json=datos_pago, timeout=15)
            res_qr.raise_for_status()
            
            respuesta_banco = res_qr.json()

            if respuesta_banco.get('success'):
                return Response({
                    'qr_image': respuesta_banco.get('message'),
                    'referencia': f"Recibo #{recibo.numero_recibo}",
                    'monto': str(recibo.monto_total),
                    'estado': 'Generado',
                    'periodo_nombre': recibo.lectura.periodo
                })
            else:
                return Response({'error': respuesta_banco.get('message')}, status=400)

        except Exception as e:
            return Response({'error': f'Problema con el banco: {str(e)}'}, status=500)