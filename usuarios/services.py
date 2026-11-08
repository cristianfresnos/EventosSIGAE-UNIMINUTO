"""
Servicios auxiliares para el módulo de usuarios y autenticación institucional.
"""

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def enviar_correo_verificacion(usuario, raw_token, request=None):
    """
    Envía el correo electrónico institucional con el enlace de verificación de cuenta.
    El token en texto plano solo existe en memoria durante la composición del mensaje.
    """
    rel_url = reverse('usuarios:verificar_correo', kwargs={'token': raw_token})
    if request:
        enlace_verificacion = request.build_absolute_uri(rel_url)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        enlace_verificacion = f"{site_url.rstrip('/')}{rel_url}"

    asunto = "Verificación de Correo Electrónico — SIGAE UNIMINUTO"
    context = {
        'usuario': usuario,
        'enlace_verificacion': enlace_verificacion,
    }

    html_content = render_to_string('usuarios/emails/verificar_correo.html', context)
    text_content = render_to_string('usuarios/emails/verificar_correo.txt', context)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'SIGAE UNIMINUTO <no-reply@uniminuto.edu.co>')

    try:
        email = EmailMultiAlternatives(
            subject=asunto,
            body=text_content,
            from_email=from_email,
            to=[usuario.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error(
            "Fallo al enviar correo de verificación para %s (ID %s): %s",
            usuario.email,
            usuario.pk,
            str(exc)
        )
        return False

