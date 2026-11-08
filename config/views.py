"""
Vistas de infraestructura y monitoreo global de SIGAE-UNIMINUTO.
"""
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def health_check(request):
    """
    Endpoint de monitoreo y verificación de salud institucional (RNF-06).
    Verifica la conectividad con la base de datos activa (SQLite / PostgreSQL)
    mediante una consulta liviana (SELECT 1).

    Retorna:
      - HTTP 200 con status 'healthy' si la base de datos responde correctamente.
      - HTTP 503 con status 'unhealthy' si la conexión falla o se degrada.
      - En ningún escenario expone cadenas de conexión, contraseñas, trazas ni datos personales.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                return JsonResponse({
                    "status": "healthy",
                    "database": "connected",
                    "timestamp": timezone.now().isoformat(),
                }, status=200)
            return JsonResponse({
                "status": "unhealthy",
                "database": "unexpected_result",
                "timestamp": timezone.now().isoformat(),
            }, status=503)
    except Exception:
        # Medida de seguridad: nunca exponer trazas de excepción, credenciales ni detalles internos
        return JsonResponse({
            "status": "unhealthy",
            "database": "unavailable",
            "timestamp": timezone.now().isoformat(),
        }, status=503)
