from rest_framework.permissions import BasePermission


class EsAdmin(BasePermission):
    """Solo usuarios con rol 'admin' pueden acceder."""
    message = 'Se requiere rol de administrador.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.rol == 'admin'
        )


class EsLector(BasePermission):
    """Solo usuarios con rol 'lector' pueden acceder."""
    message = 'Se requiere rol de lector de medidores.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.rol == 'lector'
        )


class EsSocio(BasePermission):
    """Solo usuarios con rol 'socio' pueden acceder."""
    message = 'Se requiere rol de socio.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.rol == 'socio'
        )


class EsAdminOLector(BasePermission):
    """Admin o lector pueden acceder (para registrar lecturas)."""
    message = 'Se requiere rol de administrador o lector.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.rol in ['admin', 'lector']
        )