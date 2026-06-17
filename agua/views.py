from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import Medidor, Socio, Tarifa, Lectura, Recibo, Pago
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