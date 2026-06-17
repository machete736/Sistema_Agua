import base64


class BNBQRService:

    @staticmethod
    def generar_qr(recibo):

        return {
            "success": True,
            "qr_id": f"TEST-{recibo.numero_recibo}",
            "qr_base64": "",
            "message": "QR generado en modo simulado"
        }

    @staticmethod
    def consultar_estado(qr_id):

        return {
            "success": True,
            "estado": "GENERADO"
        }

    @staticmethod
    def cancelar_qr(qr_id):

        return {
            "success": True
        }