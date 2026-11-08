"""
Servicios de lógica de negocio para la gestión de participantes,
invitaciones y accesos externos en EventosSIGAE-UNIMINUTO.
"""

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def enviar_correo_invitacion(invitacion, raw_token, request=None):
    """
    Construye y envía el correo electrónico institucional de invitación a un evento.
    
    Reglas de seguridad:
    - El token original solo reside en memoria y se interpola en el enlace seguro.
    - Nunca se registra el token en logs ni se persiste en texto plano.
    - Manejo seguro de fallos de transporte SMTP reportando éxito booleano.
    """
    rel_url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
    if request:
        enlace_invitacion = request.build_absolute_uri(rel_url)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        enlace_invitacion = f"{site_url.rstrip('/')}{rel_url}"

    asunto = f"Invitación al evento institucional: {invitacion.evento.nombre} - UNIMINUTO"
    context = {
        'invitacion': invitacion,
        'evento': invitacion.evento,
        'organizador': invitacion.invitado_por,
        'enlace_invitacion': enlace_invitacion,
        'fecha_limite': invitacion.fecha_expiracion,
    }

    html_content = render_to_string('participantes/emails/invitacion_evento.html', context)
    text_content = render_to_string('participantes/emails/invitacion_evento.txt', context)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'SIGAE UNIMINUTO <no-reply@uniminuto.edu.co>')

    try:
        email = EmailMultiAlternatives(
            subject=asunto,
            body=text_content,
            from_email=from_email,
            to=[invitacion.correo],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error(
            "Fallo en entrega de correo de invitación para %s en evento #%s: %s",
            invitacion.correo,
            invitacion.evento_id,
            str(exc)
        )
        return False


def enviar_correo_confirmacion_externa(inscripcion, acceso_externo, raw_token, request=None):
    """
    Construye y envía el correo electrónico de confirmación de inscripción para un participante externo (Etapa 7.2.2).
    
    Contenido garantizado:
    - Nombre del evento, fecha, hora y lugar.
    - Datos básicos del participante y su inscripción.
    - Enlace personal seguro para consultar su inscripción y acceder a su página individual.
    
    Reglas de seguridad:
    - El token original solo reside en memoria y se interpola en el enlace seguro.
    - Nunca se almacena el token en texto plano en la base de datos ni se escribe en logs.
    - Manejo seguro de fallos de transporte SMTP reportando éxito booleano (no genera falsos éxitos).
    """
    rel_url = reverse('participantes:consultar_acceso_externo', kwargs={'token': raw_token})
    if request:
        enlace_acceso = request.build_absolute_uri(rel_url)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        enlace_acceso = f"{site_url.rstrip('/')}{rel_url}"

    evento = inscripcion.evento
    participante = inscripcion.participante

    asunto = f"Confirmación de inscripción: {evento.nombre} - UNIMINUTO"
    context = {
        'inscripcion': inscripcion,
        'evento': evento,
        'participante': participante,
        'acceso_externo': acceso_externo,
        'enlace_acceso': enlace_acceso,
        'fecha_expiracion': acceso_externo.fecha_expiracion,
    }

    html_content = render_to_string('participantes/emails/confirmacion_inscripcion_externa.html', context)
    text_content = render_to_string('participantes/emails/confirmacion_inscripcion_externa.txt', context)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'SIGAE UNIMINUTO <no-reply@uniminuto.edu.co>')

    try:
        email = EmailMultiAlternatives(
            subject=asunto,
            body=text_content,
            from_email=from_email,
            to=[participante.correo],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error(
            "Fallo en entrega de correo de confirmación externa para participante #%s en evento #%s: %s",
            participante.pk,
            evento.pk,
            str(exc)
        )
        return False


def generar_qr_inscripcion_publica(evento, request=None):
    """
    Genera en memoria la imagen binaria PNG del código QR que apunta
    al formulario público de inscripción del evento (Etapa 7.2.2).
    """
    from asistencia.services import generar_imagen_qr_bytes

    rel_url = reverse('participantes:inscripcion_publica', kwargs={'id_evento': evento.pk})
    if request:
        url_publica = request.build_absolute_uri(rel_url)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        url_publica = f"{site_url.rstrip('/')}{rel_url}"

    return generar_imagen_qr_bytes(url_publica, formato='PNG')


