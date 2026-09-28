# agua/qz_views.py
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
        # Reemplaza caracteres '\n' literales si Railway los escapó
        return contenido.replace('\\n', '\n').strip()
    with open(CERT_PATH, 'r') as f:
        return f.read().strip()


def _obtener_clave_privada():
    contenido = os.environ.get('QZ_PRIVATE_KEY')
    if contenido:
        contenido = contenido.replace('\\n', '\n')
    else:
        with open(KEY_PATH, 'r') as f:
            contenido = f.read()

    return serialization.load_pem_private_key(
        contenido.encode('utf-8'),
        password=None,
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

    # Corregido: Se eliminó la coma y el texto residual al final
    firma_b64 = base64.b64encode(firma).decode('utf-8')
    return HttpResponse(firma_b64, content_type='text/plain')