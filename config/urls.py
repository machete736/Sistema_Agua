from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    # Panel admin de Django (solo para desarrollo)
    path('django-admin/', admin.site.urls),

    # Todas las rutas de la app agua (API + panel web)
    path('', include('agua.urls')),

    # API móvil
    path('api/', include('agua.urls_api')),
]

# Servir archivos media en desarrollo (fotos de medidores y comprobantes)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)