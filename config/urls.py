from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
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

# static() solo funciona con DEBUG=True. Con DEBUG=False (como debe estar en
# producción) las fotos dejarían de verse, por eso se sirven también así.
if not settings.DEBUG:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]