from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views_api


urlpatterns = [
    # Login con JWT
    path('token/', TokenObtainPairView.as_view(), name='api_token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),

    # API móvil del socio
    path('socio/perfil/', views_api.SocioPerfilAPIView.as_view(), name='api_socio_perfil'),
    path('socio/medidores/', views_api.SocioMedidoresAPIView.as_view(), name='api_socio_medidores'),
    path('socio/recibos/', views_api.SocioRecibosAPIView.as_view(), name='api_socio_recibos'),
    path('socio/recibos/<uuid:pk>/', views_api.SocioReciboDetalleAPIView.as_view(), name='api_socio_recibo_detalle'),
    path('socio/pagos/', views_api.SocioPagosAPIView.as_view(), name='api_socio_pagos'),
    path('socio/consumo/', views_api.SocioConsumoAPIView.as_view(), name='api_socio_consumo'),
    path('socio/estado-cuenta/', views_api.SocioEstadoCuentaAPIView.as_view(), name='api_socio_estado_cuenta'),

    # QR BNB preparado para integración nivel 3
    path(
        'socio/recibos/<uuid:pk>/generar-qr-bnb/',
        views_api.SocioGenerarQRBNBAPIView.as_view(),
        name='api_socio_generar_qr_bnb'
    ),

    path(
        'socio/qr-bnb/<uuid:pk>/',
        views_api.SocioConsultarQRBNBAPIView.as_view(),
        name='api_socio_consultar_qr_bnb'
    ),

    path(
        'socio/mis-qr-bnb/',
        views_api.SocioMisQRBNBAPIView.as_view(),
        name='api_socio_mis_qr_bnb'
    ),
]