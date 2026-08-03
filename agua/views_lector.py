import base64
import os
import re
import requests

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Medidor, Lectura


# ─────────────────────────────────────────────────────────────
# DECORADOR DE PERMISOS
# ─────────────────────────────────────────────────────────────

def solo_lector_o_admin(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.rol not in ['admin', 'tesorero', 'lector']:
            messages.error(request, 'No tienes permiso para acceder a esta sección.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────

def comprimir_imagen(imagen_bytes: bytes, max_kb: int = 800) -> bytes:
    """Comprime la imagen para no exceder el límite de Google Vision."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(imagen_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        max_dim = 1200
        if max(img.width, img.height) > max_dim:
            ratio = max_dim / max(img.width, img.height)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                Image.LANCZOS
            )
        for calidad in [85, 70, 55, 40]:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=calidad, optimize=True)
            if len(buffer.getvalue()) <= max_kb * 1024:
                return buffer.getvalue()
        return buffer.getvalue()
    except Exception:
        return imagen_bytes


def extraer_numero_serie_medidor(texto_ocr: str) -> str | None:
    """
    Extrae el número de serie del medidor desde el texto OCR.
    Patrón principal de los medidores Itron: A18S80XXXX
    """
    if not texto_ocr:
        return None
    texto = texto_ocr.upper().replace(' ', '').replace('\n', '')

    # Patrón principal: A18S80 + 4 dígitos (ej: A18S801878)
    patron = re.findall(r'A18S80\d{4}', texto)
    if patron:
        return patron[0]

    # Patrón genérico: letra + 2 dígitos + letra + 6 dígitos
    patron2 = re.findall(r'[A-Z]\d{2}[A-Z]\d{6}', texto)
    if patron2:
        return patron2[0]

    # Patrón de respaldo: alfanumérico 8-12 caracteres mixto
    patron3 = re.findall(r'[A-Z0-9]{8,12}', texto)
    if patron3:
        mixtos = [p for p in patron3 if re.search(r'[A-Z]', p) and re.search(r'\d', p)]
        if mixtos:
            return mixtos[0]
        return patron3[0]

    return None


def extraer_lectura_odometro(texto_ocr: str) -> str | None:
    """
    Intenta extraer la lectura numérica del odómetro.
    Busca secuencias de 4-7 dígitos que sean candidatos a m³.
    """
    if not texto_ocr:
        return None
    candidatos = re.findall(r'\b\d{4,7}\b', texto_ocr)
    if not candidatos:
        return None
    return candidatos[0]


def llamar_google_vision(imagen_bytes: bytes) -> dict:
    """Llama a la API de Google Vision y retorna texto + datos extraídos."""
    api_key = os.environ.get('GOOGLE_VISION_API_KEY', '')
    if not api_key:
        return {
            'exitoso': False,
            'error': 'API key de Google Vision no configurada.',
            'texto': '',
            'numero_serie': None,
            'lectura_odometro': None,
        }
    try:
        imagen_comprimida = comprimir_imagen(imagen_bytes)
        imagen_b64 = base64.b64encode(imagen_comprimida).decode('utf-8')
        url = f'https://vision.googleapis.com/v1/images:annotate?key={api_key}'
        payload = {
            'requests': [{
                'image': {'content': imagen_b64},
                'features': [{'type': 'TEXT_DETECTION', 'maxResults': 1}],
                'imageContext': {'languageHints': ['es', 'en']},
            }]
        }
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()

        respuesta = data.get('responses', [{}])[0]
        texto_completo = ''
        anotaciones = respuesta.get('textAnnotations', [])
        if anotaciones:
            texto_completo = anotaciones[0].get('description', '')
        elif respuesta.get('fullTextAnnotation'):
            texto_completo = respuesta['fullTextAnnotation'].get('text', '')

        numero_serie    = extraer_numero_serie_medidor(texto_completo)
        lectura_odometro = extraer_lectura_odometro(texto_completo)

        return {
            'exitoso': True,
            'texto': texto_completo.strip(),
            'numero_serie': numero_serie,
            'lectura_odometro': lectura_odometro,
        }

    except requests.exceptions.Timeout:
        return {
            'exitoso': False,
            'error': 'Tiempo de espera agotado. Verifica tu conexión.',
            'texto': '', 'numero_serie': None, 'lectura_odometro': None,
        }
    except Exception as e:
        return {
            'exitoso': False,
            'error': str(e),
            'texto': '', 'numero_serie': None, 'lectura_odometro': None,
        }


def _calcular_periodo_siguiente(ultima_lectura) -> str:
    """Calcula el periodo sugerido basado en la última lectura."""
    from datetime import date
    hoy = date.today()
    periodo_sugerido = hoy.strftime('%Y-%m')
    if ultima_lectura:
        try:
            anio, mes = map(int, ultima_lectura.periodo.split('-'))
            mes += 1
            if mes > 12:
                mes = 1
                anio += 1
            periodo_sugerido = f'{anio:04d}-{mes:02d}'
        except Exception:
            pass
    return periodo_sugerido


def _build_medidor_info(medidor) -> dict:
    """
    Construye el dict de información del medidor que se devuelve al frontend.
    Incluye datos del socio, medidor y última lectura.
    """
    ultima = medidor.lecturas.order_by('-fecha_lectura').first()
    return {
        'pk': str(medidor.pk),
        'numero_medidor':  medidor.numero_medidor or 'Sin número',
        'socio_nombre':    medidor.socio.nombre_completo,
        'socio_ci':        medidor.socio.ci,
        'manzano':         medidor.manzano or '',
        'parcela':         medidor.parcela or '',
        # Lectura anterior = último valor registrado
        'lectura_anterior':  str(ultima.lectura_actual) if ultima else '0.00',
        'ultimo_periodo':    ultima.periodo if ultima else 'Sin lecturas previas',
        'periodo_sugerido':  _calcular_periodo_siguiente(ultima),
        'encontrado': True,
    }


# ─────────────────────────────────────────────────────────────
# VISTAS
# ─────────────────────────────────────────────────────────────

@solo_lector_o_admin
def lector_inicio(request):
    """Lista de medidores activos con búsqueda y filtro por manzano."""
    from datetime import date

    q       = request.GET.get('q', '').strip()
    manzano = request.GET.get('manzano', '').strip()

    medidores = (
        Medidor.objects
        .select_related('socio')
        .filter(estado='Activo')
        .order_by('manzano', 'numero_medidor')
    )
    if q:
        medidores = medidores.filter(
            Q(numero_medidor__icontains=q)
            | Q(socio__nombre_completo__icontains=q)
            | Q(socio__ci__icontains=q)
        )
    if manzano:
        medidores = medidores.filter(manzano__icontains=manzano)

    manzanos = (
        Medidor.objects
        .filter(estado='Activo')
        .exclude(manzano__isnull=True)
        .exclude(manzano='')
        .values_list('manzano', flat=True)
        .distinct()
        .order_by('manzano')
    )

    # ── Progreso del periodo actual ──────────────────────────
    hoy = date.today()
    periodo_actual = hoy.strftime('%Y-%m')

    medidores_activos_total = Medidor.objects.filter(estado='Activo').count()
    leidos_periodo = (
        Lectura.objects
        .filter(periodo=periodo_actual, medidor__estado='Activo')
        .values('medidor')
        .distinct()
        .count()
    )
    pendientes_periodo = medidores_activos_total - leidos_periodo
    porcentaje_periodo = (
        round(leidos_periodo / medidores_activos_total * 100)
        if medidores_activos_total > 0 else 0
    )

    lecturas_hoy = Lectura.objects.filter(
        creado_por=request.user,
        fecha_lectura__date=hoy,
    ).count()

    return render(request, 'lector/inicio.html', {
        'medidores': medidores,
        'q':         q,
        'manzano':   manzano,
        'manzanos':  manzanos,
        'total':     medidores.count(),
        'periodo_actual':        periodo_actual,
        'medidores_activos_total': medidores_activos_total,
        'leidos_periodo':        leidos_periodo,
        'pendientes_periodo':    pendientes_periodo,
        'porcentaje_periodo':    porcentaje_periodo,
        'lecturas_hoy':          lecturas_hoy,
    })

@solo_lector_o_admin
def lector_registrar(request, medidor_pk=None):
    """
    Registra una lectura.

    Funciona en dos modos:
      - Con medidor_pk en la URL → medidor preseleccionado (flujo normal)
      - Sin medidor_pk (lector_registrar_scan) → el pk viene del POST via OCR

    El medidor final se determina así:
      POST['medidor_pk_final'] tiene prioridad sobre el medidor_pk de la URL.
      Esto permite que el OCR cambie el medidor sin confusión.
    """
    # ── Determinar el medidor ────────────────────────────────
    if request.method == 'POST':
        pk_final = request.POST.get('medidor_pk_final', '').strip()
        pk_usar  = pk_final if pk_final else str(medidor_pk)
    else:
        pk_usar = str(medidor_pk) if medidor_pk else None

    if not pk_usar:
        messages.error(request, 'No se indicó el medidor a registrar.')
        return redirect('lector_inicio')

    medidor = get_object_or_404(Medidor, pk=pk_usar, estado='Activo')

    # ── Datos del medidor para el template ──────────────────
    ultima_lectura   = medidor.lecturas.order_by('-fecha_lectura').first()
    lectura_anterior = ultima_lectura.lectura_actual if ultima_lectura else Decimal('0.00')
    ultimo_periodo   = ultima_lectura.periodo if ultima_lectura else 'Sin lecturas previas'
    periodo_sugerido = _calcular_periodo_siguiente(ultima_lectura)
    ya_existe        = Lectura.objects.filter(medidor=medidor, periodo=periodo_sugerido).exists()

    # ── POST: guardar lectura ────────────────────────────────
    if request.method == 'POST':
        periodo     = request.POST.get('periodo', '').strip()
        lectura_ant = request.POST.get('lectura_anterior', '').strip()
        lectura_act = request.POST.get('lectura_actual', '').strip()
        foto        = request.FILES.get('foto_evidencia')
        observacion = request.POST.get('observacion', '').strip()

        errores = []
        if not periodo:     errores.append('El periodo es obligatorio.')
        if not lectura_ant: errores.append('La lectura anterior es obligatoria.')
        if not lectura_act: errores.append('La lectura actual es obligatoria.')

        if not errores:
            try:
                la  = Decimal(lectura_ant)
                lac = Decimal(lectura_act)

                if lac < la:
                    errores.append('La lectura actual no puede ser menor que la anterior.')
                elif Lectura.objects.filter(medidor=medidor, periodo=periodo).exists():
                    errores.append(f'Ya existe una lectura para el periodo {periodo}.')
                else:
                    Lectura.objects.create(
                        medidor          = medidor,
                        periodo          = periodo,
                        lectura_anterior = la,
                        lectura_actual   = lac,
                        foto_evidencia   = foto,
                        observacion      = observacion or None,
                        creado_por       = request.user,
                    )
                    consumo = lac - la
                    messages.success(
                        request,
                        f'✓ Lectura registrada — '
                        f'{medidor.numero_medidor or str(medidor.pk)[:8]} | '
                        f'Periodo: {periodo} | Consumo: {consumo} m³'
                    )
                    return redirect('lector_inicio')

            except Exception as e:
                errores.append(f'Error al guardar: {e}')

        for error in errores:
            messages.error(request, error)

    return render(request, 'lector/registrar.html', {
        'medidor':          medidor,
        'ultima_lectura':   ultima_lectura,
        'lectura_anterior': lectura_anterior,
        'ultimo_periodo':   ultimo_periodo,
        'periodo_sugerido': periodo_sugerido,
        'ya_existe':        ya_existe,
    })


@login_required
@require_POST
def lector_ocr(request):
    """
    Endpoint AJAX: recibe una foto, llama a Google Vision,
    extrae número de serie y lectura, busca el medidor en BD
    y devuelve toda la información necesaria para el frontend.
    """
    if request.user.rol not in ['admin', 'tesorero', 'lector']:
        return JsonResponse({'exitoso': False, 'error': 'Sin permiso.'}, status=403)

    foto = request.FILES.get('foto')
    if not foto:
        return JsonResponse({'exitoso': False, 'error': 'No se recibió ninguna foto.'})
    if not foto.content_type.startswith('image/'):
        return JsonResponse({'exitoso': False, 'error': 'El archivo no es una imagen válida.'})

    # ── Llamar OCR ───────────────────────────────────────────
    resultado_ocr = llamar_google_vision(foto.read())

    if not resultado_ocr['exitoso']:
        return JsonResponse({
            'exitoso': False,
            'error':   resultado_ocr.get('error', 'Error al procesar la imagen.'),
            'medidor': None,
        })

    numero_serie     = resultado_ocr.get('numero_serie')
    lectura_odometro = resultado_ocr.get('lectura_odometro')
    medidor_info     = None

    # ── Buscar medidor por número de serie ───────────────────
    if numero_serie:
        try:
            medidor = (
                Medidor.objects
                .select_related('socio')
                .get(numero_medidor__iexact=numero_serie, estado='Activo')
            )
            medidor_info = _build_medidor_info(medidor)

        except Medidor.DoesNotExist:
            medidor_info = {
                'encontrado':       False,
                'numero_detectado': numero_serie,
                'mensaje': (
                    f'Medidor "{numero_serie}" no está registrado en el sistema. '
                    f'Verifica el número o busca manualmente.'
                ),
            }
        except Exception as e:
            medidor_info = {
                'encontrado': False,
                'mensaje':    f'Error al buscar medidor: {e}',
            }

    return JsonResponse({
        'exitoso':                   True,
        'numero_serie_detectado':    numero_serie,
        'lectura_odometro_detectada': lectura_odometro,
        'texto_completo':            resultado_ocr.get('texto', '')[:300],
        'medidor':                   medidor_info,
    })


@solo_lector_o_admin
def lector_historial(request, medidor_pk):
    """Muestra el historial de lecturas de un medidor."""
    medidor  = get_object_or_404(Medidor, pk=medidor_pk)
    lecturas = medidor.lecturas.order_by('-fecha_lectura')[:12]
    return render(request, 'lector/historial.html', {
        'medidor':  medidor,
        'lecturas': lecturas,
    })