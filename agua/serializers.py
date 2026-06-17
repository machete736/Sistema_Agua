from django.contrib.auth import get_user_model
from rest_framework import serializers


from .models import Medidor, Socio, Tarifa, Lectura, Recibo, Pago, TransaccionQRBNB

Usuario = get_user_model()


# =============================================================
# USUARIO
# =============================================================

class UsuarioSerializer(serializers.ModelSerializer):
    rol_display = serializers.CharField(source='get_rol_display', read_only=True)

    class Meta:
        model = Usuario
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
            'ci',
            'telefono',
            'rol',
            'rol_display',
            'activo',
            'is_active',
            'fecha_registro',
        ]
        read_only_fields = ['id', 'fecha_registro']


class UsuarioCrearSerializer(serializers.ModelSerializer):
    """
    Para que el admin cree cuentas de socios, lectores, tesoreros o administradores.
    """
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = Usuario
        fields = [
            'username',
            'password',
            'first_name',
            'last_name',
            'email',
            'ci',
            'telefono',
            'rol',
            'activo',
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')
        usuario = Usuario(**validated_data)
        usuario.set_password(password)

        if hasattr(usuario, 'is_active'):
            usuario.is_active = validated_data.get('activo', True)

        usuario.save()
        return usuario


class CambiarPasswordSerializer(serializers.Serializer):
    """
    Para que el socio cambie su propia contraseña.
    """
    password_actual = serializers.CharField(write_only=True)
    password_nuevo = serializers.CharField(write_only=True, min_length=6)

    def validate_password_actual(self, value):
        usuario = self.context['request'].user

        if not usuario.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")

        return value

    def save(self):
        usuario = self.context['request'].user
        usuario.set_password(self.validated_data['password_nuevo'])
        usuario.save()
        return usuario


class ResetPasswordAdminSerializer(serializers.Serializer):
    """
    Para que el admin resetee la contraseña de cualquier usuario.
    """
    password_nuevo = serializers.CharField(write_only=True, min_length=6)


# =============================================================
# SOCIO
# =============================================================

class SocioSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)
    tiene_usuario_movil = serializers.SerializerMethodField()

    class Meta:
        model = Socio
        fields = [
            'id_socio',
            'usuario',
            'usuario_username',
            'tiene_usuario_movil',
            'ci',
            'codigo_cliente',
            'nombre_completo',
            'fecha_registro',
        ]
        read_only_fields = [
            'id_socio',
            'fecha_registro',
            'usuario_username',
            'tiene_usuario_movil',
        ]

    def get_tiene_usuario_movil(self, obj):
        return obj.usuario is not None


class SocioResumenSerializer(serializers.ModelSerializer):
    """
    Versión reducida para usar dentro de otros serializers.
    """

    class Meta:
        model = Socio
        fields = [
            'id_socio',
            'ci',
            'codigo_cliente',
            'nombre_completo',
        ]


class SocioPerfilSerializer(serializers.ModelSerializer):
    """
    Perfil del socio para la app móvil.
    """
    usuario = serializers.SerializerMethodField()

    class Meta:
        model = Socio
        fields = [
            'id_socio',
            'usuario',
            'ci',
            'codigo_cliente',
            'nombre_completo',
            'fecha_registro',
        ]

    def get_usuario(self, obj):
        if obj.usuario:
            return obj.usuario.username
        return None


# =============================================================
# MEDIDOR
# =============================================================

class MedidorSerializer(serializers.ModelSerializer):
    socio_nombre = serializers.ReadOnlyField(source='socio.nombre_completo')
    socio_ci = serializers.ReadOnlyField(source='socio.ci')
    socio_codigo_cliente = serializers.ReadOnlyField(source='socio.codigo_cliente')

    co_titulares = SocioResumenSerializer(many=True, read_only=True)

    co_titulares_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Socio.objects.all(),
        source='co_titulares',
        write_only=True,
        required=False,
    )

    class Meta:
        model = Medidor
        fields = [
            'id_medidor',
            'socio',
            'socio_nombre',
            'socio_ci',
            'socio_codigo_cliente',
            'numero_medidor',
            'manzano',
            'parcela',
            'estado',
            'co_titulares',
            'co_titulares_ids',
        ]
        read_only_fields = ['id_medidor']

class MedidorSocioSerializer(serializers.ModelSerializer):
    """
    Medidores que verá el socio desde la app móvil.
    """
    socio_nombre = serializers.CharField(source='socio.nombre_completo', read_only=True)
    socio_ci = serializers.CharField(source='socio.ci', read_only=True)

    class Meta:
        model = Medidor
        fields = [
            'id_medidor',
            'numero_medidor',
            'socio_nombre',
            'socio_ci',
            'manzano',
            'parcela',
            'estado',
        ]

# =============================================================
# TARIFA
# =============================================================

class TarifaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tarifa
        fields = [
            'id_tarifa',
            'nombre',
            'costo_por_cubo',
            'cuota_fija',
            'multa_atraso',
            'dias_gracia',
            'fecha_vigencia',
            'activa',
        ]
        read_only_fields = ['id_tarifa', 'fecha_vigencia']


# =============================================================
# LECTURA
# =============================================================

class LecturaSerializer(serializers.ModelSerializer):
    medidor_numero = serializers.ReadOnlyField(source='medidor.numero_medidor')
    socio_nombre = serializers.ReadOnlyField(source='medidor.socio.nombre_completo')
    socio_ci = serializers.ReadOnlyField(source='medidor.socio.ci')
    periodo_nombre = serializers.ReadOnlyField()
    creado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Lectura
        fields = [
            'id_lectura',
            'medidor',
            'medidor_numero',
            'socio_nombre',
            'socio_ci',
            'periodo',
            'periodo_nombre',
            'fecha_lectura',
            'lectura_anterior',
            'lectura_actual',
            'consumo_cubos',
            'foto_evidencia',
            'observacion',
            'creado_por',
            'creado_por_nombre',
        ]
        read_only_fields = [
            'id_lectura',
            'fecha_lectura',
            'consumo_cubos',
            'creado_por',
            'creado_por_nombre',
            'periodo_nombre',
        ]

    def get_creado_por_nombre(self, obj):
        if obj.creado_por:
            nombre = obj.creado_por.get_full_name()
            return nombre if nombre else obj.creado_por.username
        return None

    def validate(self, data):
        lectura_actual = data.get('lectura_actual')
        lectura_anterior = data.get('lectura_anterior')

        if lectura_actual is not None and lectura_anterior is not None:
            if lectura_actual < lectura_anterior:
                raise serializers.ValidationError(
                    "La lectura actual no puede ser menor que la lectura anterior."
                )

        return data

    def create(self, validated_data):
        request = self.context.get('request')

        if request and request.user and request.user.is_authenticated:
            validated_data['creado_por'] = request.user

        return super().create(validated_data)


class LecturaResumenSerializer(serializers.ModelSerializer):
    """
    Lecturas para historial de consumo en la app móvil.
    """
    periodo_nombre = serializers.ReadOnlyField()
    numero_medidor = serializers.CharField(source='medidor.numero_medidor', read_only=True)

    class Meta:
        model = Lectura
        fields = [
            'id_lectura',
            'numero_medidor',
            'periodo',
            'periodo_nombre',
            'fecha_lectura',
            'lectura_anterior',
            'lectura_actual',
            'consumo_cubos',
            'foto_evidencia',
        ]


# =============================================================
# RECIBO
# =============================================================

class ReciboSerializer(serializers.ModelSerializer):
    socio_nombre = serializers.ReadOnlyField(source='socio.nombre_completo')
    socio_ci = serializers.ReadOnlyField(source='socio.ci')
    socio_codigo_cliente = serializers.ReadOnlyField(source='socio.codigo_cliente')

    lectura_periodo = serializers.ReadOnlyField(source='lectura.periodo')
    lectura_periodo_nombre = serializers.ReadOnlyField(source='lectura.periodo_nombre')
    medidor_numero = serializers.ReadOnlyField(source='lectura.medidor.numero_medidor')
    consumo_cubos = serializers.ReadOnlyField(source='lectura.consumo_cubos')
    lectura_anterior = serializers.ReadOnlyField(source='lectura.lectura_anterior')
    lectura_actual = serializers.ReadOnlyField(source='lectura.lectura_actual')

    class Meta:
        model = Recibo
        fields = [
            'id_recibo',
            'numero_recibo',
            'socio',
            'socio_nombre',
            'socio_ci',
            'socio_codigo_cliente',
            'lectura',
            'lectura_periodo',
            'lectura_periodo_nombre',
            'medidor_numero',
            'lectura_anterior',
            'lectura_actual',
            'consumo_cubos',
            'fecha_emision',
            'importe_consumo',
            'recargo_falta_pago',
            'instalacion_clandestina',
            'multa_alteracion',
            'reconexion',
            'limpieza_tanque',
            'falta_asamblea',
            'otros',
            'monto_total',
            'estado_pago',
        ]
        read_only_fields = [
            'id_recibo',
            'numero_recibo',
            'fecha_emision',
            'monto_total',
            'socio_nombre',
            'socio_ci',
            'socio_codigo_cliente',
            'lectura_periodo',
            'lectura_periodo_nombre',
            'medidor_numero',
            'lectura_anterior',
            'lectura_actual',
            'consumo_cubos',
        ]


class ReciboSocioSerializer(serializers.ModelSerializer):
    """
    Recibos que verá el socio desde la app móvil.
    """
    periodo = serializers.CharField(source='lectura.periodo', read_only=True)
    periodo_nombre = serializers.CharField(source='lectura.periodo_nombre', read_only=True)
    numero_medidor = serializers.CharField(source='lectura.medidor.numero_medidor', read_only=True)

    lectura_anterior = serializers.DecimalField(
        source='lectura.lectura_anterior',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    lectura_actual = serializers.DecimalField(
        source='lectura.lectura_actual',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    consumo_cubos = serializers.DecimalField(
        source='lectura.consumo_cubos',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = Recibo
        fields = [
            'id_recibo',
            'numero_recibo',
            'periodo',
            'periodo_nombre',
            'numero_medidor',
            'lectura_anterior',
            'lectura_actual',
            'consumo_cubos',
            'fecha_emision',
            'importe_consumo',
            'recargo_falta_pago',
            'instalacion_clandestina',
            'multa_alteracion',
            'reconexion',
            'limpieza_tanque',
            'falta_asamblea',
            'otros',
            'monto_total',
            'estado_pago',
        ]


# =============================================================
# PAGO
# =============================================================

class PagoSerializer(serializers.ModelSerializer):
    recibo_numero = serializers.ReadOnlyField(source='recibo.numero_recibo')
    socio_nombre = serializers.ReadOnlyField(source='recibo.socio.nombre_completo')
    periodo_nombre = serializers.ReadOnlyField(source='recibo.lectura.periodo_nombre')

    metodo_pago_display = serializers.CharField(
        source='get_metodo_pago_display',
        read_only=True
    )

    registrado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            'id_pago',
            'recibo',
            'recibo_numero',
            'socio_nombre',
            'periodo_nombre',
            'fecha_pago',
            'monto_pagado',
            'metodo_pago',
            'metodo_pago_display',
            'foto_comprobante',
            'registrado_por',
            'registrado_por_nombre',
        ]
        read_only_fields = [
            'id_pago',
            'fecha_pago',
            'registrado_por',
            'registrado_por_nombre',
            'recibo_numero',
            'socio_nombre',
            'periodo_nombre',
            'metodo_pago_display',
        ]

    def get_registrado_por_nombre(self, obj):
        if obj.registrado_por:
            nombre = obj.registrado_por.get_full_name()
            return nombre if nombre else obj.registrado_por.username
        return None

    def create(self, validated_data):
        request = self.context.get('request')

        if request and request.user and request.user.is_authenticated:
            validated_data['registrado_por'] = request.user

        return super().create(validated_data)


class PagoSocioSerializer(serializers.ModelSerializer):
    """
    Pagos que verá el socio desde la app móvil.
    """
    numero_recibo = serializers.IntegerField(source='recibo.numero_recibo', read_only=True)
    periodo = serializers.CharField(source='recibo.lectura.periodo', read_only=True)
    periodo_nombre = serializers.CharField(source='recibo.lectura.periodo_nombre', read_only=True)
    numero_medidor = serializers.CharField(source='recibo.lectura.medidor.numero_medidor', read_only=True)

    metodo_pago_display = serializers.CharField(
        source='get_metodo_pago_display',
        read_only=True
    )

    class Meta:
        model = Pago
        fields = [
            'id_pago',
            'numero_recibo',
            'periodo',
            'periodo_nombre',
            'numero_medidor',
            'fecha_pago',
            'monto_pagado',
            'metodo_pago',
            'metodo_pago_display',
            'foto_comprobante',
        ]


# =============================================================
# ESTADO DE CUENTA SOCIO
# =============================================================

class EstadoCuentaSocioSerializer(serializers.Serializer):
    anio = serializers.CharField()
    consumo_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_emitido = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_pagado = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_retrasos = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_pendiente = serializers.DecimalField(max_digits=10, decimal_places=2)
from .models import TransaccionQRBNB


class TransaccionQRBNBSerializer(serializers.ModelSerializer):

    class Meta:
        model = TransaccionQRBNB

        fields = [
            'id_transaccion',
            'qr_id_bnb',
            'monto',
            'estado',
            'fecha_creacion',
            'fecha_pago',
        ]