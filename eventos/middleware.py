"""
Middleware de exigibilidad y recuperación automática de calificaciones obligatorias pendientes (RF-27).
Proyecto: EventosSIGAE-UNIMINUTO
"""

import re
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .services import es_estudiante_elegible_rol, obtener_primera_evaluacion_pendiente


_EXEMPT_PATH_PATTERNS = (
    re.compile(r'^/eventos/\d+/calificar/?$'),
    re.compile(r'^/usuarios/(login|logout|verificar-correo|solicitar-verificacion-correo|password-reset|reset)/?'),
    re.compile(r'^/asistencia/evento/\d+/(salida|registrar-salida)/?$'),
    re.compile(r'^/participantes/mis-inscripciones/?$'),
    re.compile(r'^/health/?$'),
    re.compile(r'^/static/'),
    re.compile(r'^/media/'),
    re.compile(r'^/admin/'),
)


class CalificacionPendienteMiddleware:
    """
    Detecta de forma confiable si el estudiante autenticado tiene alguna evaluación
    obligatoria pendiente (entrada + salida confirmadas sin calificación registrada)
    y redirige automáticamente hacia la pantalla de calificación obligatoria.

    Garantiza que un estudiante que abandona la evaluación tras registrar su salida
    no pueda evadirla navegando por el portal, sin afectar a docentes, administradores,
    participantes externos ni endpoints de cierre de sesión o salida QR.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and es_estudiante_elegible_rol(user):
            path = request.path_info or request.path or ''
            if not self._es_ruta_exenta(path):
                pendiente = obtener_primera_evaluacion_pendiente(user)
                if pendiente is not None:
                    url_calificar = reverse('eventos:calificar_evento', kwargs={'id_evento': pendiente.evento_id})
                    is_ajax = (
                        request.headers.get('x-requested-with') == 'XMLHttpRequest'
                        or request.content_type == 'application/json'
                    )
                    if is_ajax:
                        return JsonResponse({
                            'exito': False,
                            'codigo': 'CALIFICACION_PENDIENTE_OBLIGATORIA',
                            'mensaje': (
                                f"Tienes una calificación obligatoria pendiente para el evento "
                                f"'{pendiente.evento.nombre}'. Debes completarla para continuar."
                            ),
                            'requiere_calificacion': True,
                            'url_calificacion': url_calificar,
                        }, status=403)
                    return redirect(url_calificar)

        return self.get_response(request)

    @staticmethod
    def _es_ruta_exenta(path):
        for pattern in _EXEMPT_PATH_PATTERNS:
            if pattern.match(path):
                return True
        return False
