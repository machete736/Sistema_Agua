from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views_lector
from . import views
from . import views_web

# =============================================================
# API — Django REST Framework
# =============================================================
router = DefaultRouter()
router.register(r'usuarios',  views.UsuarioViewSet,   basename='usuario')
router.register(r'socios',    views.SocioViewSet,     basename='socio')
router.register(r'medidores', views.MedidorViewSet,   basename='medidor')
router.register(r'tarifas',   views.TarifaViewSet,    basename='tarifa')
router.register(r'lecturas',  views.LecturaViewSet,   basename='lectura')
router.register(r'recibos',   views.ReciboViewSet,    basename='recibo')
router.register(r'pagos',     views.PagoViewSet,      basename='pago')
router.register(r'mi-cuenta', views.MiCuentaViewSet,  basename='mi-cuenta')

urlpatterns = [

    # API
    path('api/', include(router.urls)),
    path('api/token/',         TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(),    name='token_refresh'),
    path('api-auth/',          include('rest_framework.urls')),

    # PANEL WEB — Autenticacion
    path('login/',            views_web.login_view,            name='login'),
    path('logout/',           views_web.logout_view,           name='logout'),
    path('cambiar-password/', views_web.cambiar_password_view, name='cambiar_password'),

    # PANEL WEB — Dashboard
    path('', views_web.dashboard_view, name='dashboard'),

    # PANEL WEB — Socios
    path('socios/', views_web.socios_lista, name='socios_lista'),
    path('socios/crear/', views_web.socio_crear, name='socio_crear'),
    path('socios/<uuid:pk>/', views_web.socio_detalle, name='socio_detalle'),
    path('socios/<uuid:pk>/editar/', views_web.socio_editar, name='socio_editar'),
    path('socios/<uuid:pk>/estado-cuenta/', views_web.socio_estado_cuenta, name='socio_estado_cuenta'),
    path('socios/<uuid:pk>/crear-usuario-movil/', views_web.socio_crear_usuario_movil, name='socio_crear_usuario_movil'),

    # PANEL WEB — Medidores
    path('medidores/',                  views_web.medidores_lista, name='medidores_lista'),
    path('medidores/nuevo/',            views_web.medidor_crear,   name='medidor_crear'),
    path('medidores/<uuid:pk>/editar/', views_web.medidor_editar,  name='medidor_editar'),

    # PANEL WEB — Lecturas
    path('lecturas/',       views_web.lecturas_lista, name='lecturas_lista'),
    path('lecturas/nueva/', views_web.lectura_crear,  name='lectura_crear'),
    path('lecturas/ocr-detectar/', views_web.lectura_ocr_detectar, name='lectura_ocr_detectar'),
    path('lecturas/medidor-info/<uuid:pk>/', views_web.lectura_medidor_info, name='lectura_medidor_info'),
 

    # PANEL WEB — Cobros
    path('cobros/', views_web.cobros_lista, name='cobros_lista'),
    path('cobros/generar/', views_web.cobro_generar, name='cobro_generar'),
    path('cobros/<uuid:pk>/', views_web.cobro_detalle, name='cobro_detalle'),
    path('cobros/<uuid:pk>/cargos/', views_web.cobro_editar_cargos, name='cobro_editar_cargos'),
    path('cobros/<uuid:pk>/imprimir/', views_web.cobro_imprimir_termico, name='cobro_imprimir_termico'),path('cobros/<uuid:pk>/imprimir/', views_web.cobro_imprimir, name='cobro_imprimir'),

    # PANEL WEB — Pagos
    path('pagos/',                         views_web.pagos_lista,    name='pagos_lista'),
    path('cobros/<uuid:cobro_pk>/pagar/',  views_web.pago_registrar, name='pago_registrar'),

    # PANEL WEB — Tarifas
    # Tarifas
    path('tarifas/', views_web.tarifas_lista, name='tarifas_lista'),
    path('tarifas/crear/', views_web.tarifa_crear, name='tarifa_crear'),
    path('tarifas/<int:pk>/editar/', views_web.tarifa_editar, name='tarifa_editar'),

    # PANEL WEB — Usuarios
    path('usuarios/',                         views_web.usuarios_lista,          name='usuarios_lista'),
    path('usuarios/nuevo/',                   views_web.usuario_crear,           name='usuario_crear'),
    path('usuarios/<int:pk>/reset-password/', views_web.usuario_reset_password,  name='usuario_reset_password'),

    # PANEL WEB — Reportes

    # REPORTES
    # =============================================================
    path('reportes/', views_web.reportes_view, name='reportes'),
    path('reportes/deudas/', views_web.reporte_deudas, name='reporte_deudas'),
    path('reportes/recaudacion/', views_web.reporte_recaudacion, name='reporte_recaudacion'),
    path('reportes/mensual/', views_web.reporte_mensual, name='reporte_mensual'),
    path('reportes/anual/', views_web.reporte_anual, name='reporte_anual'),
    path('reportes/multas/', views_web.reporte_multas, name='reporte_multas'),
    # ajax
    path('ajax/medidor/<uuid:pk>/datos/', views_web.ajax_datos_medidor, name='ajax_datos_medidor'),
    
        # APP LECTOR — web responsiva para el lector de medidores
    path('lector/',                              views_lector.lector_inicio,    name='lector_inicio'),
    path('lector/registrar/',                    views_lector.lector_registrar, name='lector_registrar_scan'),
    path('lector/<uuid:medidor_pk>/registrar/',  views_lector.lector_registrar, name='lector_registrar'),
    path('lector/<uuid:medidor_pk>/historial/',  views_lector.lector_historial, name='lector_historial'),
    path('lector/ocr/',                          views_lector.lector_ocr,       name='lector_ocr'),



    # QRs Genéricos
    path('qrs/', views_web.qrs_lista, name='qrs_lista'),
    path('qrs/crear/', views_web.qr_crear, name='qr_crear'),
    path('qrs/editar/<int:pk>/', views_web.qr_editar, name='qr_editar'),
    path('qrs/eliminar/<int:pk>/', views_web.qr_eliminar, name='qr_eliminar'),

 
# =============================================================
# AGREGA ESTAS 2 RUTAS EN TU urls.py
# =============================================================
 
    path('backup/', views_web.backup_vista, name='backup_vista'),
    path('backup/excel/', views_web.backup_excel, name='backup_excel'),
 
]