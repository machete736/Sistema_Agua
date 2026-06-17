import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
# =============================================================
# USUARIO PERSONALIZADO CON ROLES
# =============================================================

class Usuario(AbstractUser):

    ROL_ADMIN = 'admin'
    ROL_TESORERO = 'tesorero'
    ROL_LECTOR = 'lector'
    ROL_SOCIO = 'socio'

    ROL_CHOICES = [
        (ROL_ADMIN, 'Administrador'),
        (ROL_TESORERO, 'Tesorero'),
        (ROL_LECTOR, 'Lector de medidores'),
        (ROL_SOCIO, 'Socio'),
    ]

    rol = models.CharField(
        max_length=20,
        choices=ROL_CHOICES,
        default=ROL_SOCIO
    )

    ci = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Carnet de identidad'
    )

    telefono = models.CharField(
        max_length=20,
        null=True,
        blank=True
    )

    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_rol_display()})"

    @property
    def es_admin(self):
        return self.rol == self.ROL_ADMIN

    @property
    def es_tesorero(self):
        return self.rol == self.ROL_TESORERO

    @property
    def es_lector(self):
        return self.rol == self.ROL_LECTOR

    @property
    def es_socio(self):
        return self.rol == self.ROL_SOCIO

    @property
    def puede_administrar(self):
        return self.rol in [self.ROL_ADMIN, self.ROL_TESORERO]

    @property
    def puede_registrar_lecturas(self):
        return self.rol in [self.ROL_ADMIN, self.ROL_TESORERO, self.ROL_LECTOR]
    

# =============================================================
# SOCIO
# =============================================================

class Socio(models.Model):
    id_socio = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Usuario opcional para que el socio pueda entrar desde la app móvil
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='socio_perfil',
        verbose_name='Usuario de acceso móvil'
    )

    ci = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Carnet de identidad'
    )

    codigo_cliente = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Código de cliente'
    )

    nombre_completo = models.CharField(
        max_length=150,
        verbose_name='Nombre completo'
    )
    telefono = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name='Teléfono'
    )

    estado = models.CharField(
        max_length=20,
        default='ACTIVO',
        verbose_name='Estado'
    )

    observacion_retiro = models.TextField(
        null=True,
        blank=True,
        verbose_name='Observación de retiro'
    )

    fecha_retiro = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de retiro'
    )
    
    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        db_table = 'socios'
        ordering = ['nombre_completo']
        verbose_name = 'Socio'
        verbose_name_plural = 'Socios'

    def __str__(self):
        return f"{self.nombre_completo} - {self.ci}"
# =============================================================
# MEDIDOR
# Los medidores pueden tener mas de un titular (co-titulares).
# Todos los co-titulares ven el mismo historial y deudas.
# =============================================================

class Medidor(models.Model):
    ESTADO_CHOICES = [
        ('Activo', 'Activo'),
        ('Cortado', 'Cortado'),
        ('Dado de baja', 'Dado de baja'),
    ]

    id_medidor = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Titular principal del medidor
    socio = models.ForeignKey(
        Socio,
        on_delete=models.CASCADE,
        related_name='medidores_titular'
    )
    # Co-titulares: otros socios que pueden ver este medidor
    co_titulares = models.ManyToManyField(
        Socio,
        blank=True,
        related_name='medidores_cotitular',
        verbose_name='Co-titulares'
    )
    numero_medidor = models.CharField(max_length=50, unique=True, null=True, blank=True)
    manzano = models.CharField(max_length=50, null=True, blank=True)
    parcela = models.CharField(max_length=50, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='Activo')

    class Meta:
        db_table = 'medidores'
        ordering = ['numero_medidor']

    def __str__(self):
        return self.numero_medidor or f"Medidor {self.id_medidor}"

    def todos_los_socios(self):
        """Devuelve el titular + todos los co-titulares."""
        return Socio.objects.filter(
            models.Q(medidores_titular=self) | models.Q(medidores_cotitular=self)
        ).distinct()


# =============================================================
# TARIFA
# =============================================================
class Tarifa(models.Model):
    id_tarifa = models.AutoField(primary_key=True)

    nombre = models.CharField(max_length=50)

    costo_por_cubo = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    cuota_fija = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    multa_atraso = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Multa por atraso'
    )

    dias_gracia = models.PositiveIntegerField(
        default=0,
        verbose_name='Días de gracia para pago'
    )

    fecha_vigencia = models.DateField(
        auto_now_add=True,
        null=True,
        blank=True
    )

    activa = models.BooleanField(default=True)

    class Meta:
        db_table = 'tarifas'
        ordering = ['-id_tarifa']

    def __str__(self):
        return self.nombre

# =============================================================
# LECTURA DE MEDIDOR
# Campo sincronizado eliminado — el sistema es centralizado.
# La foto se guarda como archivo en el servidor.
# =============================================================

class Lectura(models.Model):
    id_lectura = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medidor = models.ForeignKey(
        Medidor,
        on_delete=models.CASCADE,
        related_name='lecturas'
    )
    periodo = models.CharField(max_length=20)  # ej: "2025-06"
    fecha_lectura = models.DateTimeField(auto_now_add=True)
    lectura_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    lectura_actual = models.DecimalField(max_digits=10, decimal_places=2)
    consumo_cubos = models.DecimalField(max_digits=10, decimal_places=2,
                                        default=Decimal('0.00'), editable=False)
    foto_evidencia = models.ImageField(
    upload_to='lecturas/fotos/',
    null=True,
    blank=True,
    verbose_name='Foto del medidor'
    )

    observacion = models.TextField(
        null=True,
        blank=True,
        verbose_name='Observación de lectura'
    )
    # Usuario lector que registro la lectura
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lecturas_registradas'
    )

    class Meta:
        db_table = 'lecturas'
        ordering = ['-fecha_lectura']
        constraints = [
            models.UniqueConstraint(
                fields=['medidor', 'periodo'],
                name='unique_lectura_por_periodo'
            )
        ]

    def save(self, *args, **kwargs):
        if self.lectura_actual < self.lectura_anterior:
            raise ValidationError(
                "La lectura actual no puede ser menor que la lectura anterior."
            )
        self.consumo_cubos = self.lectura_actual - self.lectura_anterior
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.medidor} - {self.periodo}"

    @property
    def periodo_nombre(self):
        meses = {
            '01': 'ENERO',
            '02': 'FEBRERO',
            '03': 'MARZO',
            '04': 'ABRIL',
            '05': 'MAYO',
            '06': 'JUNIO',
            '07': 'JULIO',
            '08': 'AGOSTO',
            '09': 'SEPTIEMBRE',
            '10': 'OCTUBRE',
            '11': 'NOVIEMBRE',
            '12': 'DICIEMBRE',
        }

        try:
            anio, mes = self.periodo.split('-')
            return f"{meses.get(mes, mes)} {anio}"
        except Exception:
            return self.periodo

# =============================================================
# RECIBO
# =============================================================

class Cobro(models.Model):
    ESTADO_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('En Revision', 'En Revision'),
        ('Cancelado', 'Cancelado'),
        ('Vencido', 'Vencido'),
    ]

    id_recibo = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_recibo = models.PositiveIntegerField(unique=True, null=True, blank=True,
                                                editable=False)
    socio = models.ForeignKey(
        Socio,
        on_delete=models.CASCADE,
        related_name='recibos'
    )
    lectura = models.OneToOneField(
        Lectura,
        on_delete=models.CASCADE,
        related_name='recibo'
    )
    fecha_emision = models.DateField(auto_now_add=True)

    # Montos calculados automaticamente al guardar
    importe_consumo = models.DecimalField(max_digits=10, decimal_places=2,
                                          default=Decimal('0.00'))
    recargo_falta_pago = models.DecimalField(max_digits=10, decimal_places=2,
                                              default=Decimal('0.00'))
    instalacion_clandestina = models.DecimalField(max_digits=10, decimal_places=2,
                                                   default=Decimal('0.00'))
    multa_alteracion = models.DecimalField(max_digits=10, decimal_places=2,
                                            default=Decimal('0.00'))
    reconexion = models.DecimalField(max_digits=10, decimal_places=2,
                                     default=Decimal('0.00'))
    limpieza_tanque = models.DecimalField(max_digits=10, decimal_places=2,
                                          default=Decimal('0.00'))
    falta_asamblea = models.DecimalField(max_digits=10, decimal_places=2,
                                         default=Decimal('0.00'))
    otros = models.DecimalField(max_digits=10, decimal_places=2,
                                default=Decimal('0.00'))
    monto_total = models.DecimalField(max_digits=10, decimal_places=2,
                                      default=Decimal('0.00'), editable=False)
    estado_pago = models.CharField(max_length=20, choices=ESTADO_CHOICES,
                                   default='Pendiente')

    class Meta:
        db_table = 'recibos'
        ordering = ['-fecha_emision', '-numero_recibo']

    def save(self, *args, **kwargs):
        tarifa = Tarifa.objects.filter(activa=True).order_by('-id_tarifa').first()

        if self.lectura_id and tarifa:
            self.importe_consumo = (
                self.lectura.consumo_cubos * tarifa.costo_por_cubo
            ) + tarifa.cuota_fija

        self.monto_total = (
            self.importe_consumo
            + self.recargo_falta_pago
            + self.instalacion_clandestina
            + self.multa_alteracion
            + self.reconexion
            + self.limpieza_tanque
            + self.falta_asamblea
            + self.otros
        )

        if self.numero_recibo is None:
            ultimo = Cobro.objects.aggregate(max_num=Max('numero_recibo'))['max_num']
            self.numero_recibo = (ultimo or 0) + 1

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cobro N° {self.numero_recibo} - {self.socio.nombre_completo}"


# Alias de compatibilidad: la API de socios (app móvil) y serializers
# importan "Recibo" desde models.py. No renombrar esto sin actualizar
# también serializers.py, views_api.py y urls_api.py.
Recibo = Cobro


@receiver(post_save, sender=Lectura)
def generar_cobro_automatico(sender, instance, created, **kwargs):
    """
    Genera el Cobro automáticamente apenas se registra una nueva lectura,
    sin importar si viene del panel web (manual), del modo móvil/OCR,
    o de cualquier otro punto del sistema que cree una Lectura.

    No se ejecuta en ediciones de lecturas ya existentes (created=False),
    para no duplicar ni recalcular cobros sin que el usuario lo pida.
    """
    if not created:
        return
    # Si por alguna razón ya existe un cobro para esta lectura (OneToOne), no duplicar.
    if hasattr(instance, 'recibo'):
        return
    Cobro.objects.create(
        socio=instance.medidor.socio,
        lectura=instance,
    )


# =============================================================
# PAGO
# =============================================================

class Pago(models.Model):
    METODO_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('qr', 'QR'),
    ]

    id_pago = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recibo = models.ForeignKey(
        Cobro,
        on_delete=models.CASCADE,
        related_name='pagos'
    )
    fecha_pago = models.DateTimeField(auto_now_add=True)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_CHOICES,
                                   default='efectivo')
    # Foto del comprobante (para transferencias)
    foto_comprobante = models.ImageField(
        upload_to='pagos/comprobantes/',
        null=True,
        blank=True,
        verbose_name='Foto del comprobante'
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pagos_registrados'
    )

    class Meta:
        db_table = 'pagos'
        ordering = ['-fecha_pago']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar estado del recibo segun pagos acumulados
        total_pagado = self.recibo.pagos.aggregate(
            total=Sum('monto_pagado')
        )['total'] or Decimal('0.00')

        if total_pagado >= self.recibo.monto_total:
            self.recibo.estado_pago = 'Cancelado'
        else:
            self.recibo.estado_pago = 'En Revision'
        self.recibo.save()

    def __str__(self):
        return f"Pago {self.recibo} - Bs {self.monto_pagado}"
    
# =============================================================
# TRANSACCIONES QR BNB
# =============================================================

class TransaccionQRBNB(models.Model):

    ESTADOS = [
        ('GENERADO', 'Generado'),
        ('PAGADO', 'Pagado'),
        ('EXPIRADO', 'Expirado'),
        ('ERROR', 'Error'),
        ('CANCELADO', 'Cancelado'),
    ]

    id_transaccion = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    recibo = models.ForeignKey(
        'Cobro',
        on_delete=models.CASCADE,
        related_name='transacciones_qr'
    )

    qr_id_bnb = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    monto = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    qr_base64 = models.TextField(
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='GENERADO'
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    fecha_pago = models.DateTimeField(
        blank=True,
        null=True
    )

    observacion = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'transacciones_qr_bnb'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"QR {self.qr_id_bnb} - {self.estado}"