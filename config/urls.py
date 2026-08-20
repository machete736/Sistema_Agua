from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Panel admin de Django
    path('django-admin/', admin.site.urls),

    # Rutas de la app agua (Panel web + API)
    path('', include('agua.urls')),

    # API móvil
    path('api/', include('agua.urls_api')),
]

# Servir archivos media (fotos de medidores, QRs y comprobantes) en desarrollo y producción
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)