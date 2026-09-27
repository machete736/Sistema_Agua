# agua/qz_views.py
# Vistas para firmar las peticiones de QZ Tray y servir el certificado.
# Elimina el popup "Untrusted website / Action Required" en el cliente.
#
# El certificado y la clave privada se leen de variables de entorno
# (QZ_CERTIFICATE y QZ_PRIVATE_KEY) para que funcione en Railway,
# donde el sistema de archivos no es persistente entre deploys.
# En local, si no defines las variables, cae a los archivos en qz_keys/.

import base64
import os
from django.conf import settings
from django.http import HttpResponse
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

CERT_PATH = os.path.join(settings.BASE_DIR, 'qz_keys', 'digital-certificate.txt')
KEY_PATH = os.path.join(settings.BASE_DIR, 'qz_keys', 'private-key.pem')


def _obtener_certificado():
    contenido = os.environ.get('QZ_CERTIFICATE')
    if contenido:
        return contenido
    with open(CERT_PATH, 'r') as f:
        return f.read()


def _obtener_clave_privada():
    contenido = os.environ.get('QZ_PRIVATE_KEY')
    if not contenido:
        with open(KEY_PATH, 'r') as f:
            contenido = f.read()
    return serialization.load_pem_private_key(
        contenido.encode('utf-8'),
        password=None,  # si la clave tiene contraseña, ponla aquí en bytes
    )


def qz_certificado(request):
    """
    Sirve el contenido del certificado público.
    QZ Tray lo pide vía AJAX al iniciar (setCertificatePromise).
    """
    return HttpResponse(_obtener_certificado(), content_type='text/plain')


def qz_firmar(request):
    """
    Firma el string que QZ Tray envía en el parámetro GET "request"
    usando SHA512 + la clave privada, y devuelve la firma en base64.
    """
    texto = request.GET.get('request', '')
    clave_privada = _obtener_clave_privada()

    firma = clave_privada.sign(
        texto.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA512(),
    )

    firma_b64 = base64.b64encode(firma).decode('utf-8')
    return HttpResponse(firma_b64, content_type='text/plain')