"""
Middleware de Bitácora
=======================
Django's signals (post_save, post_delete) no reciben el request, así que no
saben qué usuario hizo el cambio. Este middleware guarda el usuario actual
en una variable "thread-local" (una por cada petición/hilo) para que las
señales en models.py puedan leerlo.

INSTALACIÓN:
1. Guarda este archivo como agua/middleware_bitacora.py
2. En settings.py, agrega 'agua.middleware_bitacora.BitacoraMiddleware'
   al final de la lista MIDDLEWARE.
"""
import threading

_thread_locals = threading.local()


def get_usuario_actual():
    """Devuelve el usuario autenticado de la petición en curso, o None."""
    return getattr(_thread_locals, 'usuario', None)


def get_ip_actual():
    """Devuelve la IP de la petición en curso, o None."""
    return getattr(_thread_locals, 'ip', None)


def _obtener_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class BitacoraMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, 'user', None)
        _thread_locals.usuario = usuario if (usuario and usuario.is_authenticated) else None
        _thread_locals.ip = _obtener_ip(request)
        try:
            response = self.get_response(request)
        finally:
            # Limpieza para no arrastrar datos de una petición a otra
            _thread_locals.usuario = None
            _thread_locals.ip = None
        return response