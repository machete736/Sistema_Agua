# Sistema Agua — Comité Agua Paraíso (Django)

Backend del comité de agua: panel web para administrador, tesorero y lector, más la API que usa la app móvil de los socios (`../app_socio_agua/`, repo `machete736/App-Socios-Paraiso`). Responder siempre en español.

Producción: Railway, `https://web-production-a3912.up.railway.app` (`Procfile`: gunicorn + whitenoise, PostgreSQL por `DATABASE_URL`).

## Comandos

```powershell
venv\Scripts\python manage.py runserver
venv\Scripts\python manage.py test agua
venv\Scripts\python manage.py makemigrations agua
venv\Scripts\python manage.py migrate
venv\Scripts\python manage.py crear_datos_prueba      # y eliminar_datos_prueba
venv\Scripts\python manage.py aplicar_recargos
railway logs                                          # logs de producción
```

Configuración por `.env` con `python-decouple`. Nunca leer, mostrar ni subir `.env`.

## Estructura

Una sola app, `agua/`; el proyecto es `config/`.

- `models.py` (910 líneas) — `Usuario` (con rol: admin, tesorero, lector, socio), `Socio`, `Medidor`, `Afiliacion`, `Tarifa`, `Lectura`, `Cobro`, `Pago`, `TransaccionQRBNB`, `QRGenerico`, `Bitacora`. `AUTH_USER_MODEL = 'agua.Usuario'`.
- `views_web.py` (2801 líneas) — todo el panel web con plantillas de `templates/`. Buscar la vista con Grep y leer solo ese rango.
- `views_lector.py` — pantallas del lector (registro de lecturas, lectura de medidor con Google Vision).
- `views_api.py` + `urls_api.py` — API móvil del socio, montada en `/api/` desde `config/urls.py`. JWT con simplejwt.
- `views.py` — ViewSets de DRF registrados en un router dentro de `agua/urls.py`, también bajo `/api/`.
- `serializers.py`, `permissions.py`, `middleware_bitacora.py` (registra acciones en `Bitacora`), `qz_views.py` (firma para impresión térmica con QZ Tray), `services/bnb_qr_service.py`.

## Cuidado con

- **Dos grupos de rutas comparten el prefijo `/api/`**: el router de `agua/urls.py` (se incluye primero) y `agua/urls_api.py`. Al agregar una ruta, revisar que no choque con la otra.
- **Un cambio en `serializers.py` o `views_api.py` puede romper la app móvil ya instalada** en los celulares de los socios, que no se actualiza sola. No renombrar ni quitar campos de la API; agregar campos nuevos sí se puede.
- Todo cambio en `models.py` lleva su migración, y la migración tiene que poder aplicarse sobre los datos reales de producción (campos nuevos con `default` o `null=True`).
- **En producción `DEBUG` muestra la página amarilla de error**, pero un error de plantilla sigue tumbando la pantalla. En las plantillas, nunca usar `|default:objeto.campo` si `objeto` puede estar vacío (por ejemplo `registrado_por`, `creado_por`): Django falla con `VariableDoesNotExist`. Usar `{% if objeto %}...{% else %}—{% endif %}`.
- Las fotos de `media/` (QRs, comprobantes, respaldos de egresos) se guardan en el disco de Railway, que se borra en cada despliegue si no hay un volumen montado.
- `STATICFILES_STORAGE` en `settings.py` no tiene efecto en Django 5.2 (se reemplazó por `STORAGES`).
- Las vistas de egresos y del balance están en `views_egresos.py`, y el reporte general (gráficas e interpretación automática) en `views_reporte_general.py`, no en `views_web.py`.
- Al agregar un modelo nuevo, sumarlo también al backup (`backup_excel` en `views_web.py`: su hoja y la hoja Resumen).
- Los reportes se imprimen con `window.print()`: la impresora se elige en el diálogo del navegador, la página no puede elegirla.
- Zona horaria `America/La_Paz`, idioma `es-bo`.

## Estilo

Nombres y comentarios en español, explicando el porqué en lenguaje sencillo.

## Para trabajar gastando poco

- No leer ni buscar en `venv/`, `staticfiles/`, `media/`, `__pycache__/`.
- Las migraciones solo se leen si el problema es de migraciones.
- Los archivos están en UTF-8: leerlos con la herramienta Read, no con `Get-Content`.
