import io
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from ...models import Socio, Medidor, Tarifa, Lectura, Cobro, Pago

# Datos fijos del socio de prueba. `eliminar_datos_prueba` los usa para
# encontrarlo y borrarlo, así que no deben coincidir con un socio real.
CI_PRUEBA = '99999999'
NOMBRE_PRUEBA = 'Usuario de Prueba'
MEDIDOR_PRUEBA = 'PRUEBA-001'


def periodo_relativo(hoy, meses_atras):
    """Periodo "AAAA-MM" de hace `meses_atras` meses (0 = el mes actual)."""
    indice = hoy.year * 12 + (hoy.month - 1) - meses_atras
    return f'{indice // 12:04d}-{indice % 12 + 1:02d}'


def comprobante_falso():
    """Imagen de relleno para que el pago "En Revision" tenga algo que mostrar."""
    imagen = Image.new('RGB', (480, 640), 'white')
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle((20, 20, 460, 620), outline='black', width=3)
    dibujo.text((60, 280), 'COMPROBANTE DE PRUEBA', fill='black')
    dibujo.text((60, 310), 'No es un pago real', fill='black')
    buffer = io.BytesIO()
    imagen.save(buffer, format='PNG')
    return ContentFile(buffer.getvalue(), name='comprobante_prueba.png')


class Command(BaseCommand):
    help = (
        'Crea un socio de prueba ("Usuario de Prueba") con su medidor y seis '
        'recibos en todos los estados (cancelado, vencido, rechazado, '
        'pendiente y en revisión) para probar el panel y la app móvil. '
        'Se borra con: python manage.py eliminar_datos_prueba'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=CI_PRUEBA,
            help='Contraseña del usuario de prueba (por defecto, su CI, igual que los socios reales).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        Usuario = get_user_model()

        if Socio.objects.filter(ci=CI_PRUEBA).exists() or Usuario.objects.filter(username=CI_PRUEBA).exists():
            raise CommandError(
                f'Ya existe un socio o usuario con CI {CI_PRUEBA}. '
                'Bórralo primero con: python manage.py eliminar_datos_prueba'
            )
        if Medidor.objects.filter(numero_medidor=MEDIDOR_PRUEBA).exists():
            raise CommandError(f'Ya existe un medidor con número {MEDIDOR_PRUEBA}.')
        if not Tarifa.objects.filter(activa=True).exists():
            raise CommandError('No hay una tarifa activa. Crea una en el panel antes de generar los datos de prueba.')

        usuario = Usuario.objects.create_user(
            username=CI_PRUEBA,
            password=options['password'],
            first_name=NOMBRE_PRUEBA,
        )
        usuario.rol = 'socio'
        usuario.ci = CI_PRUEBA
        usuario.activo = True
        usuario.save()

        socio = Socio.objects.create(
            usuario=usuario,
            ci=CI_PRUEBA,
            nombre_completo=NOMBRE_PRUEBA,
            telefono='70000000',
        )
        medidor = Medidor.objects.create(
            socio=socio,
            numero_medidor=MEDIDOR_PRUEBA,
            manzano='PRUEBA',
            parcela='1',
        )

        # Un recibo por mes, del más antiguo al actual. Las fechas se calculan
        # desde hoy para que los estados salgan igual sin importar cuándo se
        # ejecute el comando.
        #   (meses atrás, consumo en m³, caso)
        plan = [
            (5, 6, 'cancelado_efectivo'),
            (4, 9, 'cancelado_qr'),
            (3, 7, 'vencido'),          # 2 meses de multa por atraso
            (2, 8, 'rechazado'),        # vencido + comprobante rechazado
            (1, 5, 'pendiente'),        # todavía dentro del plazo de pago
            (0, 6, 'en_revision'),      # comprobante enviado, esperando revisión
        ]

        hoy = timezone.localdate()
        lectura_acumulada = Decimal('100')
        resumen = []

        for meses_atras, consumo, caso in plan:
            periodo = periodo_relativo(hoy, meses_atras)
            anio, mes = (int(x) for x in periodo.split('-'))
            fecha = hoy if meses_atras == 0 else date(anio, mes, 28)
            momento = timezone.make_aware(datetime.combine(fecha, time(10, 0)))

            lectura = Lectura.objects.create(
                medidor=medidor,
                periodo=periodo,
                lectura_anterior=lectura_acumulada,
                lectura_actual=lectura_acumulada + consumo,
                observacion='Dato de prueba',
            )
            lectura_acumulada += consumo

            # Las fechas son automáticas (hoy): se corrigen a la del periodo.
            Lectura.objects.filter(pk=lectura.pk).update(fecha_lectura=momento)
            cobro = Cobro.objects.get(lectura=lectura)
            Cobro.objects.filter(pk=cobro.pk).update(fecha_emision=fecha)

            if caso in ('cancelado_efectivo', 'cancelado_qr'):
                pago = Pago.objects.create(
                    recibo=cobro,
                    monto_pagado=cobro.monto_total,
                    metodo_pago='efectivo' if caso == 'cancelado_efectivo' else 'qr',
                )
                Pago.objects.filter(pk=pago.pk).update(fecha_pago=momento)

            elif caso == 'vencido':
                cobro.aplicar_recargo_automatico()

            elif caso in ('rechazado', 'en_revision'):
                pago = Pago.objects.create(
                    recibo=cobro,
                    monto_pagado=cobro.monto_total,
                    metodo_pago='qr',
                    foto_comprobante=comprobante_falso(),
                    registrado_por=usuario,
                    estado='En Revision',
                    nro_transaccion='PRUEBA000001' if caso == 'rechazado' else 'PRUEBA000002',
                )
                if caso == 'rechazado':
                    pago.estado = 'Rechazado'
                    pago.motivo_rechazo = 'La foto está borrosa (dato de prueba)'
                    pago.fecha_revision = timezone.now()
                    pago.save()
                    cobro.aplicar_recargo_automatico()

            cobro.refresh_from_db()
            resumen.append((periodo, cobro.numero_recibo, cobro.estado_pago, cobro.monto_total, caso))

        self.stdout.write(self.style.SUCCESS('\nSocio de prueba creado.\n'))
        self.stdout.write(f'  Nombre:      {NOMBRE_PRUEBA}')
        self.stdout.write(f'  Medidor:     {MEDIDOR_PRUEBA}')
        self.stdout.write(f'  Usuario app: {CI_PRUEBA}')
        self.stdout.write(f'  Contraseña:  {options["password"]}\n')
        self.stdout.write('  Periodo   Recibo  Estado        Monto      Caso')
        for periodo, numero, estado, monto, caso in resumen:
            self.stdout.write(f'  {periodo}   #{numero:<5} {estado:<13} Bs {monto:<7} {caso}')
        self.stdout.write('\nPara borrarlo todo: python manage.py eliminar_datos_prueba\n')
