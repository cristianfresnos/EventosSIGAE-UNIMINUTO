"""
Servicios de lógica de negocio para la gestión de participantes,
invitaciones y accesos externos en EventosSIGAE-UNIMINUTO.
"""

import datetime
import hashlib
import hmac
import ipaddress
import logging
import re
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

# Parámetros de limitación de intentos (anti fuerza bruta) para consulta y validación pública
CONSULTA_MAX_INTENTOS = 5
CONSULTA_MAX_INTENTOS_DOC = 5
CONSULTA_MAX_INTENTOS_IP = 5
CONSULTA_VENTANA_SEGUNDOS = 600  # 10 minutos
RATE_LIMIT_SALT = "sigae-rate-limit-publico-v1"


class AccesoExternoRevocadoError(Exception):
    """
    Excepción de dominio lanzada cuando un AccesoExternoInscripcion fue revocado
    administrativamente y no puede ser rehabilitado desde el flujo público.
    """
    pass


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


# ==============================================================================
# SERVICIOS DE CONSULTA Y RECUPERACIÓN SEGURA DE INSCRIPCIONES PÚBLICAS
# ==============================================================================

SESSION_KEYS_ACCESO_EXTERNO = (
    'acceso_externo_id',
    'acceso_externo_hash',
    'acceso_externo_inscripcion_id',
    'acceso_externo_evento_id',
)


def normalizar_documento_rate_limit(documento):
    """
    Normaliza el documento eliminando espacios, puntos, guiones y guiones bajos en minúscula
    para evitar evasión del límite mediante variaciones cosméticas del mismo documento.
    """
    return re.sub(r'[\s\.\-_]+', '', (documento or '').strip()).lower()


def _validar_ip(valor):
    candidato = (valor or '').strip()
    if not candidato:
        return None
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return None


def obtener_ip_rate_limit(request):
    """
    Resuelve de forma segura la IP efectiva para rate limiting y auditoría:
    - Cuando existe X-Forwarded-For con múltiples saltos, toma la IP más a la derecha
      (añadida por el proxy inverso de borde como Render) para dificultar suplantación
      de cabeceras enviadas por el cliente.
    - Valida formato IP estándar (evitando errores de tipo inet en PostgreSQL).
    - Hace fallback seguro a REMOTE_ADDR.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        partes = [p.strip() for p in xff.split(',') if p.strip()]
        for parte in reversed(partes):
            ip_valida = _validar_ip(parte)
            if ip_valida:
                return ip_valida
    return _validar_ip(request.META.get('REMOTE_ADDR'))


def generar_hmac_rate_limit(tipo, evento_id, valor):
    """
    Genera un identificador HMAC-SHA256 truncado (24 hex chars) con clave del servidor
    (SECRET_KEY + salt de dominio), evitando almacenar documentos o datos personales en claro.
    """
    clave_secreta = f"{RATE_LIMIT_SALT}:{settings.SECRET_KEY}".encode('utf-8')
    mensaje = f"{tipo}:{evento_id}:{valor}".encode('utf-8')
    return hmac.new(clave_secreta, mensaje, hashlib.sha256).hexdigest()[:24]


def _construir_tags_rate_limit(evento_id, ip=None, documento=None):
    ip_norm = _validar_ip(ip) or 'unknown'
    ip_hmac = generar_hmac_rate_limit('ip', evento_id, ip_norm)
    doc_norm = normalizar_documento_rate_limit(documento)
    doc_hmac = generar_hmac_rate_limit('doc', evento_id, doc_norm) if doc_norm else None
    return doc_hmac, ip_hmac


def _contar_fallos_en_ventana(evento_id, tag_objetivo, ventana_inicio):
    """
    Cuenta intentos fallidos persistidos en PostgreSQL/BD (tabla auditoria_auditoria)
    dentro de la ventana temporal, respetando cualquier recuperación exitosa posterior
    sin eliminar registros inmutables de auditoría.
    """
    from auditoria.models import Auditoria

    prefijo_evento = f"rl|e:{evento_id}|"
    ultimo_exito = (
        Auditoria.objects
        .filter(
            modulo='PARTICIPANTES',
            accion='RECUPERAR_INSCRIPCION_PUBLICA',
            fecha__gte=ventana_inicio,
            registro_afectado__contains=tag_objetivo,
        )
        .order_by('-fecha')
        .values_list('fecha', flat=True)
        .first()
    )
    desde = ultimo_exito if (ultimo_exito and ultimo_exito > ventana_inicio) else ventana_inicio

    return Auditoria.objects.filter(
        modulo='PARTICIPANTES',
        accion='CONSULTA_PUBLICA_FALLIDA',
        fecha__gte=desde,
        registro_afectado__startswith=prefijo_evento,
        registro_afectado__contains=tag_objetivo,
    ).count()


def esta_bloqueada_consulta_inscripcion(evento_id, ip, documento=None):
    """
    Evalúa de forma persistente en BD (compartida entre todos los workers de Gunicorn
    sin requerir tablas nuevas ni servicios externos) si se alcanzó el límite de intentos
    fallidos para este evento por:
    1) (evento_id, HMAC(documento normalizado)) -> protege contra rotación de IP / X-Forwarded-For.
    2) (evento_id, HMAC(IP)) -> protege contra enumeración horizontal desde una misma IP.

    No bloquea indiscriminadamente a otros participantes del evento con distinto documento e IP.
    Retorna (bloqueada: bool, intentos_max: int).
    """
    ventana_inicio = timezone.now() - datetime.timedelta(seconds=CONSULTA_VENTANA_SEGUNDOS)
    doc_hmac, ip_hmac = _construir_tags_rate_limit(evento_id, ip=ip, documento=documento)

    intentos_ip = _contar_fallos_en_ventana(evento_id, f"|i:{ip_hmac}", ventana_inicio)
    if intentos_ip >= CONSULTA_MAX_INTENTOS_IP:
        return True, intentos_ip

    intentos_doc = 0
    if doc_hmac:
        intentos_doc = _contar_fallos_en_ventana(evento_id, f"|d:{doc_hmac}|", ventana_inicio)
        if intentos_doc >= CONSULTA_MAX_INTENTOS_DOC:
            return True, intentos_doc

    return False, max(intentos_ip, intentos_doc)


def registrar_intento_fallido_consulta(evento_id, ip, documento=None):
    """
    Persiste un intento fallido de consulta o validación pública en la tabla Auditoria
    utilizando exclusivamente HMACs con secreto del servidor (sin almacenar documentos en claro).
    """
    from auditoria.models import Auditoria

    ip_valida = _validar_ip(ip)
    doc_hmac, ip_hmac = _construir_tags_rate_limit(evento_id, ip=ip_valida, documento=documento)
    doc_parte = doc_hmac if doc_hmac else 'none'
    registro = f"rl|e:{evento_id}|d:{doc_parte}|i:{ip_hmac}"[:100]

    Auditoria.objects.create(
        usuario=None,
        accion='CONSULTA_PUBLICA_FALLIDA',
        modulo='PARTICIPANTES',
        registro_afectado=registro,
        ip=ip_valida,
    )
    _, conteo = esta_bloqueada_consulta_inscripcion(evento_id, ip_valida, documento=documento)
    return conteo


def construir_registro_auditoria_recuperacion(inscripcion, ip=None):
    """
    Construye una cadena de auditoría <= 100 caracteres sin datos personales en claro
    con tags HMAC para restablecer limpiamente la ventana del participante tras éxito.
    """
    doc = getattr(inscripcion.participante, 'documento', '') if inscripcion else ''
    doc_hmac, ip_hmac = _construir_tags_rate_limit(inscripcion.evento_id, ip=ip, documento=doc)
    doc_parte = doc_hmac if doc_hmac else 'none'
    return f"rec|ins:{inscripcion.pk}|e:{inscripcion.evento_id}|d:{doc_parte}|i:{ip_hmac}"[:100]


def limpiar_intentos_consulta(evento_id, ip, documento=None):
    """
    Mantiene compatibilidad de interfaz; el restablecimiento de ventana en el diseño
    inmutable se realiza automáticamente mediante la marca temporal del registro
    RECUPERAR_INSCRIPCION_PUBLICA sin eliminar filas de auditoría.
    """
    return None


def _normalizar_telefono(valor):
    return re.sub(r'[\s\-\(\)\+\.]', '', (valor or '').strip())


def coincide_dato_verificacion_participante(participante, dato_verificacion):
    """
    Valida en tiempo constante (hmac.compare_digest) si el segundo dato de verificación
    coincide con el correo electrónico o con el teléfono registrado del participante.
    """
    if not participante or not dato_verificacion:
        return False

    entrada = dato_verificacion.strip()
    if not entrada:
        return False

    correo_reg = (participante.correo or '').strip().lower()
    if correo_reg and hmac.compare_digest(correo_reg, entrada.lower()):
        return True

    tel_reg = _normalizar_telefono(participante.telefono)
    tel_in = _normalizar_telefono(entrada)
    if tel_reg and len(tel_in) >= 7 and tel_in.isdigit() and hmac.compare_digest(tel_reg, tel_in):
        return True

    return False


def buscar_inscripcion_publica_verificada(evento, documento, dato_verificacion):
    """
    Busca una inscripción ACTIVA estrictamente asociada al evento indicado cuyo
    participante coincida en número de documento y en el segundo dato de verificación
    (correo electrónico o teléfono).

    No asume unicidad global del documento en Participante: evalúa todos los candidatos
    asociados al evento sin crear ni modificar registros.
    Retorna la instancia de Inscripcion si coincide, o None en caso contrario.
    """
    from .models import Inscripcion, EstadoInscripcion

    doc_limpio = (documento or '').strip()
    verif_limpio = (dato_verificacion or '').strip()
    if not evento or not doc_limpio or not verif_limpio:
        return None

    candidatas = (
        Inscripcion.objects
        .select_related('participante', 'evento', 'asistencia')
        .filter(
            evento=evento,
            estado=EstadoInscripcion.ACTIVA,
            participante__documento=doc_limpio,
        )
    )

    # Priorizar coincidencia externa sin cuenta si hubiese más de un perfil con mismo documento
    coincidencia_institucional = None
    for insc in candidatas:
        if coincide_dato_verificacion_participante(insc.participante, verif_limpio):
            if insc.participante.usuario_id is None:
                return insc
            coincidencia_institucional = insc

    return coincidencia_institucional


def obtener_o_restaurar_acceso_externo(inscripcion, duracion_dias=30):
    """
    Obtiene o renueva de forma segura el AccesoExternoInscripcion de una inscripción externa:
    1. Si existe y fue revocado administrativamente (revocado=True):
       NO modifica revocado, fecha_revocacion, token_hash, fecha_expiracion ni ultimo_acceso,
       y lanza AccesoExternoRevocadoError para impedir su rehabilitación desde el flujo público.
    2. Si existe, NO está revocado y sigue vigente (es_valido=True):
       Reutiliza el registro SIN rotar ni invalidar token_hash (solo actualiza ultimo_acceso).
    3. Si existe, NO está revocado pero está expirado:
       Renueva token_hash y fecha_expiracion conservando revocado=False.
    4. Si no existe registro previo:
       Emite un nuevo AccesoExternoInscripcion seguro.

    Garantiza:
    - No crea nuevas inscripciones.
    - No altera el estado de asistencia.
    - No rehabilita accesos revocados administrativamente.
    Retorna (acceso_ext, raw_token_o_None).
    """
    from .models import AccesoExternoInscripcion

    with transaction.atomic():
        acceso_ext = (
            AccesoExternoInscripcion.objects
            .select_for_update()
            .filter(inscripcion=inscripcion)
            .first()
        )
        ahora = timezone.now()
        if acceso_ext:
            if acceso_ext.revocado:
                raise AccesoExternoRevocadoError(
                    "El acceso a esta inscripción no se encuentra disponible. "
                    "Por favor comunícate con el administrador o coordinador del evento para solicitar asistencia."
                )

            if acceso_ext.es_valido:
                acceso_ext.ultimo_acceso = ahora
                acceso_ext.save(update_fields=['ultimo_acceso'])
                return acceso_ext, None

            # Acceso expirado pero NO revocado: renovar vigencia y token de forma segura
            raw_token, nuevo_hash = AccesoExternoInscripcion.generar_token()
            acceso_ext.token_hash = nuevo_hash
            acceso_ext.fecha_expiracion = ahora + datetime.timedelta(days=duracion_dias)
            acceso_ext.ultimo_acceso = ahora
            acceso_ext.save(update_fields=['token_hash', 'fecha_expiracion', 'ultimo_acceso'])
            return acceso_ext, raw_token

        acceso_ext, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(
            inscripcion,
            duracion_dias=duracion_dias,
        )
        acceso_ext.ultimo_acceso = ahora
        acceso_ext.save(update_fields=['ultimo_acceso'])
        return acceso_ext, raw_token


def establecer_sesion_acceso_externo(request, acceso_ext, inscripcion):
    """Establece el contexto seguro de acceso externo en la sesión del navegador."""
    if acceso_ext and inscripcion and acceso_ext.inscripcion_id == inscripcion.pk:
        request.session['acceso_externo_id'] = acceso_ext.pk
        request.session['acceso_externo_hash'] = acceso_ext.token_hash
        request.session['acceso_externo_inscripcion_id'] = inscripcion.pk
        request.session['acceso_externo_evento_id'] = inscripcion.evento_id


def limpiar_sesion_acceso_externo(request):
    """Elimina cualquier contexto previo de acceso externo en la sesión."""
    for clave in SESSION_KEYS_ACCESO_EXTERNO:
        request.session.pop(clave, None)


def tiene_sesion_externa_activa_evento(request, evento):
    """
    Indica si la sesión actual ya cuenta con un AccesoExternoInscripcion válido
    y vigente para una inscripción ACTIVA de este evento específico.
    """
    from .models import AccesoExternoInscripcion, EstadoInscripcion

    acceso_id = request.session.get('acceso_externo_id')
    token_hash = request.session.get('acceso_externo_hash')
    if not acceso_id or not token_hash or not evento:
        return False

    acceso = (
        AccesoExternoInscripcion.objects
        .select_related('inscripcion', 'inscripcion__participante')
        .filter(
            pk=acceso_id,
            token_hash=token_hash,
            revocado=False,
            inscripcion__evento_id=evento.pk,
            inscripcion__estado=EstadoInscripcion.ACTIVA,
        )
        .first()
    )
    return bool(acceso and acceso.es_valido)



