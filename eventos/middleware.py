"""
Middleware de exigibilidad y recuperación automática de calificaciones obligatorias pendientes (RF-27, RF-31).
Proyecto: EventosSIGAE-UNIMINUTO
"""

import re
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from participantes.services import resolver_acceso_externo_sesion
from .services import (
    es_estudiante_elegible_rol,
    obtener_primera_evaluacion_pendiente,
    obtener_evaluacion_pendiente_externa,
)


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

_EXTERNO_EXTRA_EXEMPT_PATTERNS = (
    re.compile(r'^/participantes/evento/\d+/(registro-publico|consultar-inscripcion|qr-inscripcion)/?$'),
    re.compile(r'^/participantes/externo/(?!mi-inscripcion/?$)[^/]+/?$'),
    re.compile(r'^/asistencia/inscripcion/\d+/qr-dinamico/?$'),
)


class CalificacionPendienteMiddleware:
    """
    Detecta de forma confiable si el estudiante autenticado o el participante externo
    con sesión segura activa tiene alguna evaluación obligatoria pendiente (entrada + salida
    confirmadas sin calificación registrada) y redirige automáticamente hacia la pantalla
    de calificación obligatoria.

    Garantiza que quien abandona la evaluación tras registrar su salida no pueda evadirla
    navegando por el portal, sin afectar a docentes, administradores, visitantes anónimos
    sin sesión externa ni endpoints de cierre de sesión, recuperación pública o salida QR.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        path = request.path_info or request.path or ''

        if user and es_estudiante_elegible_rol(user):
            if not self._es_ruta_exenta(path):
                pendiente = obtener_primera_evaluacion_pendiente(user)
                if pendiente is not None:
                    return self._construir_respuesta_pendiente(request, pendiente)
        elif not (user and getattr(user, 'is_authenticated', False)):
            session = getattr(request, 'session', None)
            if (
                session is not None
                and session.get('acceso_externo_id')
                and session.get('acceso_externo_hash')
                and not self._es_ruta_exenta_externo(path)
            ):
                acceso_ext = resolver_acceso_externo_sesion(request)
                if acceso_ext is not None:
                    pendiente_ext = obtener_evaluacion_pendiente_externa(acceso_ext)
                    if pendiente_ext is not None:
                        resp = self._construir_respuesta_pendiente(request, pendiente_ext)
                        resp['Referrer-Policy'] = 'no-referrer'
                        return resp

        return self.get_response(request)

    @staticmethod
    def _construir_respuesta_pendiente(request, pendiente):
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

    @staticmethod
    def _es_ruta_exenta(path):
        for pattern in _EXEMPT_PATH_PATTERNS:
            if pattern.match(path):
                return True
        return False

    @classmethod
    def _es_ruta_exenta_externo(cls, path):
        if cls._es_ruta_exenta(path):
            return True
        for pattern in _EXTERNO_EXTRA_EXEMPT_PATTERNS:
            if pattern.match(path):
                return True
        return False
