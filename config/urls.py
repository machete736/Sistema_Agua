from django.contrib import admin
from django.urls import path, include, re_path

from agua import views_web

urlpatterns = [
    # Panel admin de Django
    path('django-admin/', admin.site.urls),

    # Rutas de la app agua (Panel web + API)
    path('', include('agua.urls')),

    # API móvil
    path('api/', include('agua.urls_api')),
]

# Servir archivos media (fotos de medidores, QRs y comprobantes) en desarrollo
# y producción. Se usa una vista propia para que, si una foto ya no existe,
# se muestre un aviso claro en vez de "Page not found (404)".
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', views_web.servir_media),
]
