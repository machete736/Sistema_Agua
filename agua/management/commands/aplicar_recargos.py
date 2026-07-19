from django.core.management.base import BaseCommand

from ...models import Cobro


class Command(BaseCommand):
    help = (
        "Recalcula y aplica el recargo por atraso (Bs por cada mes de atraso) "
        "a todos los cobros pendientes o vencidos que aún no fueron cancelados."
    )

    def handle(self, *args, **options):
        cobros = Cobro.objects.exclude(estado_pago='Cancelado').select_related(
            'lectura'
        )

        actualizados = 0
        for cobro in cobros:
            if cobro.aplicar_recargo_automatico():
                actualizados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Se actualizaron {actualizados} de {cobros.count()} cobros."
            )
        )