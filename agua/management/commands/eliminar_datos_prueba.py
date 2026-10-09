from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ...models import Socio, Pago
from .crear_datos_prueba import CI_PRUEBA, NOMBRE_PRUEBA


class Command(BaseCommand):
    help = (
        'Borra el socio de prueba creado con crear_datos_prueba, junto con su '
        'usuario, medidor, lecturas, recibos, pagos y fotos de comprobante.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        Usuario = get_user_model()
        socio = Socio.objects.filter(ci=CI_PRUEBA).first()

        # Seguro: si un socio real llegara a tener ese CI, no se toca.
        if socio and socio.nombre_completo != NOMBRE_PRUEBA:
            raise CommandError(
                f'El socio con CI {CI_PRUEBA} se llama "{socio.nombre_completo}", '
                f'no "{NOMBRE_PRUEBA}". No se borró nada.'
            )

        if socio:
            pagos = Pago.objects.filter(recibo__socio=socio)
            cantidad_recibos = socio.recibos.count()
            cantidad_pagos = pagos.count()

            for pago in pagos:
                if not pago.foto_comprobante:
                    continue
                try:
                    pago.foto_comprobante.delete(save=False)
                except Exception:
                    pass  # el archivo ya no estaba en el servidor

            # Al borrar el socio se van en cascada su medidor, lecturas,
            # recibos y pagos.
            socio.delete()
            self.stdout.write(f'Socio de prueba borrado ({cantidad_recibos} recibos, {cantidad_pagos} pagos).')

        borrados, _ = Usuario.objects.filter(username=CI_PRUEBA, rol='socio').delete()
        if borrados:
            self.stdout.write('Usuario de prueba borrado.')

        if not socio and not borrados:
            self.stdout.write('No había datos de prueba que borrar.')
        else:
            self.stdout.write(self.style.SUCCESS('Listo: no quedan datos de prueba.'))
