from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import TransaccionQRBNB

from .models import Usuario, Socio, Medidor, Tarifa, Lectura, Recibo, Pago


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ['username', 'first_name', 'last_name', 'ci', 'rol', 'activo']
    list_filter = ['rol', 'activo']
    search_fields = ['username', 'first_name', 'last_name', 'ci']
    fieldsets = UserAdmin.fieldsets + (
        ('Datos adicionales', {
            'fields': ('ci', 'telefono', 'rol', 'activo')
        }),
    )


@admin.register(Socio)
class SocioAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo', 'ci', 'codigo_cliente', 'fecha_registro']
    search_fields = ['nombre_completo', 'ci', 'codigo_cliente']
    ordering = ['nombre_completo']


@admin.register(Medidor)
class MedidorAdmin(admin.ModelAdmin):
    list_display = ['numero_medidor', 'socio', 'manzano', 'parcela', 'estado']
    list_filter = ['estado', 'manzano']
    search_fields = ['numero_medidor', 'socio__nombre_completo', 'socio__ci']
    filter_horizontal = ['co_titulares']


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'costo_por_cubo', 'cuota_fija', 'fecha_vigencia', 'activa']
    list_filter = ['activa']


@admin.register(Lectura)
class LecturaAdmin(admin.ModelAdmin):
    list_display = [
        'medidor', 'periodo', 'lectura_anterior',
        'lectura_actual', 'consumo_cubos', 'fecha_lectura'
    ]
    list_filter = ['periodo']
    search_fields = ['medidor__numero_medidor', 'medidor__socio__nombre_completo']
    ordering = ['-fecha_lectura']
    readonly_fields = ['consumo_cubos', 'fecha_lectura']


@admin.register(Recibo)
class ReciboAdmin(admin.ModelAdmin):
    list_display = [
        'numero_recibo', 'socio', 'fecha_emision',
        'monto_total', 'estado_pago'
    ]
    list_filter = ['estado_pago', 'fecha_emision']
    search_fields = ['numero_recibo', 'socio__nombre_completo', 'socio__ci']
    ordering = ['-fecha_emision', '-numero_recibo']
    readonly_fields = ['numero_recibo', 'monto_total', 'fecha_emision']


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = [
        'recibo', 'fecha_pago', 'monto_pagado',
        'metodo_pago', 'registrado_por'
    ]
    list_filter = ['metodo_pago', 'fecha_pago']
    search_fields = ['recibo__numero_recibo', 'recibo__socio__nombre_completo']
    ordering = ['-fecha_pago']
    readonly_fields = ['fecha_pago']

@admin.register(TransaccionQRBNB)
class TransaccionQRBNBAdmin(admin.ModelAdmin):

    list_display = (
        'qr_id_bnb',
        'recibo',
        'monto',
        'estado',
        'fecha_creacion',
    )

    search_fields = (
        'qr_id_bnb',
    )

    list_filter = (
        'estado',
    )    