import io
import os
import datetime
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
import qrcode

from auditoria.models import Auditoria
from participantes.models import Inscripcion, EstadoInscripcion
from .models import Asistencia, MetodoAsistencia, EstadoAsistencia

SALT_QR = 'sigae-asistencia-qr-salt-v1'
SALT_SALIDA_EVENTO = 'sigae-salida-evento-v1'
MAX_AGE_QR_LLEGADA = 90   # Ventana de validez máxima para QR dinámico de llegada (segundos)
MAX_AGE_QR_SALIDA = 120   # Ventana de validez máxima para QR colectivo de salida (segundos)


def generar_token_qr(inscripcion):
    """
    Genera un token criptográficamente firmado y seguro para una inscripción.
    No expone documentos de identidad, nombres ni PII.
    El payload contiene identificadores y la fecha de inscripción para validar coherencia.
    Incorpora marca de tiempo criptográfica mediante TimestampSigner (signing.dumps).
    """
    payload = {
        'ins': inscripcion.pk,
        'evt': inscripcion.evento_id,
        'f_ins': inscripcion.fecha_inscripcion.isoformat() if inscripcion.fecha_inscripcion else '',
    }
    return signing.dumps(payload, salt=SALT_QR)


def decodificar_token_qr(token, max_age=None):
    """
    Decodifica y verifica la firma criptográfica del token QR.
    Si se especifica max_age, valida que no haya excedido la ventana de validez.
    Lanza signing.BadSignature o signing.SignatureExpired si el token fue manipulado o es inválido.
    """
    if max_age is not None:
        return signing.loads(token, salt=SALT_QR, max_age=max_age)
    return signing.loads(token, salt=SALT_QR)


def generar_token_salida_evento(evento, control=None):
    """
    Genera un token criptográficamente firmado para el código QR de salida común de un evento.
    Incorpora identificador de sesión y nonce vigente de ControlSalidaEvento cuando existe.
    No expone datos personales ni identificadores sensibles.
    """
    from .models import ControlSalidaEvento
    if control is None:
        control = ControlSalidaEvento.objects.filter(evento=evento).first()

    sesion_id = control.sesion_id if (control and control.salidas_habilitadas) else ''
    nonce = control.nonce_vigente if (control and control.salidas_habilitadas) else ''

    payload = {
        'evt': evento.pk,
        'f': evento.fecha.isoformat() if evento.fecha else '',
        'ses': sesion_id,
        'non': nonce,
    }
    return signing.dumps(payload, salt=SALT_SALIDA_EVENTO)


def decodificar_token_salida_evento(token, max_age=None):
    """
    Decodifica y verifica la firma criptográfica del token del QR común de salida del evento.
    Si se especifica max_age, valida la ventana de caducidad temporal.
    Lanza signing.BadSignature o signing.SignatureExpired si el token es inválido o fue manipulado.
    """
    if max_age is not None:
        return signing.loads(token, salt=SALT_SALIDA_EVENTO, max_age=max_age)
    return signing.loads(token, salt=SALT_SALIDA_EVENTO)


def validar_token_salida_evento(token_evento, evento, max_age=MAX_AGE_QR_SALIDA):
    """
    Valida integralmente el token de salida colectivo del evento:
    1. Verifica la firma criptográfica.
    2. Verifica la expiración temporal (max_age).
    3. Verifica que pertenezca al evento en curso.
    4. Verifica con ControlSalidaEvento que la sesión de salida esté activa y que el nonce coincida.
    Retorna (True, payload, None) si es válido, o (False, codigo_error, mensaje) si es inválido.
    """
    if not token_evento:
        return False, 'TOKEN_FALTANTE', "Se requiere un código QR de salida para registrar la salida."

    try:
        payload = decodificar_token_salida_evento(token_evento, max_age=max_age)
    except signing.SignatureExpired:
        return False, 'QR_SALIDA_EXPIRADO', "El código QR de salida presentado ha expirado (ventana de validez superada)."
    except signing.BadSignature:
        return False, 'QR_SALIDA_ALTERADO', "El código QR de salida presentado es inválido o fue alterado."

    if payload.get('evt') != evento.pk:
        return False, 'EVENTO_INCORRECTO', f"El código QR de salida pertenece a otro evento institucional (ID {payload.get('evt')})."

    from .models import ControlSalidaEvento
    control = ControlSalidaEvento.objects.filter(evento=evento).first()

    if control:
        if not control.salidas_habilitadas or control.fecha_cierre is not None:
            return False, 'SESION_CERRADA', "El registro de salidas para este evento se encuentra cerrado o no ha sido habilitado por el organizador."
        if control.sesion_id or control.nonce_vigente:
            ses_token = payload.get('ses')
            non_token = payload.get('non')
            if not control.es_sesion_activa(ses_token, non_token):
                return False, 'SESION_INVALIDA', "El código QR de salida ha sido invalidado por el organizador (sesión renovada, cerrada o rotada)."
    else:
        if not es_salida_habilitada(evento):
            return False, 'SESION_CERRADA', "El registro de salidas para este evento se encuentra cerrado o no ha sido habilitado por el organizador."

    return True, payload, None


def generar_imagen_qr_bytes(token_o_texto, formato='PNG'):
    """
    Genera en memoria (sin almacenar en disco) la imagen del código QR en formato PNG.
    Retorna los bytes binarios correspondientes.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(token_o_texto)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format=formato)
    buffer.seek(0)
    return buffer.getvalue()


def registrar_asistencia_llegada(inscripcion, metodo=MetodoAsistencia.QR, operador=None, ip=None, observaciones=None):
    """
    Registra de manera atómica la llegada de un participante a un evento.
    
    Reglas de negocio aplicadas:
    1. La inscripción debe existir y estar en estado ACTIVA.
    2. Si ya cuenta con asistencia en estado REGISTRADA: rechaza la duplicidad y retorna aviso.
    3. Si cuenta con asistencia en estado ANULADA: reactiva la asistencia a REGISTRADA (corrección autorizada).
    4. Si no cuenta con asistencia: crea la entidad Asistencia vinculada mediante OneToOne.
    5. Registra la trazabilidad completa en auditoria.Auditoria.
    """
    if inscripcion.estado != EstadoInscripcion.ACTIVA:
        return {
            'exito': False,
            'codigo': 'INSCRIPCION_NO_ACTIVA',
            'mensaje': f"La inscripción se encuentra en estado '{inscripcion.get_estado_display()}'. No admite registro de asistencia.",
            'asistencia': None,
            'participante': inscripcion.participante,
            'evento': inscripcion.evento,
        }

    ahora = timezone.localtime(timezone.now()) if getattr(settings, 'USE_TZ', False) else timezone.now()
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    with transaction.atomic():
        # Bloquear fila de inscripción para evitar condiciones de carrera concurrentes
        inscripcion_bloqueada = Inscripcion.objects.select_for_update().get(pk=inscripcion.pk)
        
        # Verificar si ya existe un registro de asistencia
        asistencia = getattr(inscripcion_bloqueada, 'asistencia', None)
        if asistencia is None:
            # Consulta explícita por seguridad ante OneToOne
            asistencia = Asistencia.objects.filter(inscripcion=inscripcion_bloqueada).first()

        if asistencia:
            if asistencia.estado == EstadoAsistencia.REGISTRADA:
                return {
                    'exito': False,
                    'codigo': 'ASISTENCIA_DUPLICADA',
                    'mensaje': f"El participante {inscripcion.participante} ya registró su asistencia el {asistencia.fecha.strftime('%d/%m/%Y')} a las {asistencia.hora_entrada.strftime('%H:%M') if asistencia.hora_entrada else '--:--'}.",
                    'asistencia': asistencia,
                    'participante': inscripcion.participante,
                    'evento': inscripcion.evento,
                }
            elif asistencia.estado == EstadoAsistencia.ANULADA:
                # Reactivación de asistencia previamente anulada
                asistencia.estado = EstadoAsistencia.REGISTRADA
                asistencia.metodo = metodo
                asistencia.fecha = fecha_hoy
                asistencia.hora_entrada = hora_actual
                if observaciones:
                    asistencia.observaciones = observaciones
                asistencia.save()

                Auditoria.objects.create(
                    usuario=operador,
                    accion='REACTIVAR_ASISTENCIA',
                    modulo='ASISTENCIA',
                    registro_afectado=f"Asistencia ID {asistencia.pk} reactivada - Inscripción {inscripcion.pk} - Evento {inscripcion.evento_id}",
                    ip=ip
                )

                return {
                    'exito': True,
                    'codigo': 'ASISTENCIA_REACTIVADA',
                    'mensaje': f"Asistencia reactivada exitosamente para {inscripcion.participante}.",
                    'asistencia': asistencia,
                    'participante': inscripcion.participante,
                    'evento': inscripcion.evento,
                }

        # Creación de nuevo registro de asistencia
        try:
            nueva_asistencia = Asistencia.objects.create(
                inscripcion=inscripcion_bloqueada,
                fecha=fecha_hoy,
                hora_entrada=hora_actual,
                metodo=metodo,
                estado=EstadoAsistencia.REGISTRADA,
                observaciones=observaciones or ''
            )
        except IntegrityError:
            # En caso de concurrencia extrema donde el OneToOne haya sido satisfecho en microsegundos
            asistencia_concurrente = Asistencia.objects.filter(inscripcion=inscripcion_bloqueada).first()
            return {
                'exito': False,
                'codigo': 'ASISTENCIA_DUPLICADA',
                'mensaje': f"Asistencia ya registrada concurrentemente para {inscripcion.participante}.",
                'asistencia': asistencia_concurrente,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

        Auditoria.objects.create(
            usuario=operador,
            accion='REGISTRAR_ASISTENCIA',
            modulo='ASISTENCIA',
            registro_afectado=f"Asistencia ID {nueva_asistencia.pk} ({metodo}) - Inscripción {inscripcion.pk} - Evento {inscripcion.evento_id}",
            ip=ip
        )

        return {
            'exito': True,
            'codigo': 'ASISTENCIA_REGISTRADA',
            'mensaje': f"¡Asistencia registrada con éxito para {inscripcion.participante}!",
            'asistencia': nueva_asistencia,
            'participante': inscripcion.participante,
            'evento': inscripcion.evento,
        }


def registrar_asistencia_salida(inscripcion, metodo=MetodoAsistencia.QR, operador=None, ip=None, observaciones=None, forzar_actualizacion=False, hora_salida_custom=None, ignorar_bloqueo_salidas=False):
    """
    Registra de manera atómica la salida (checkout) de un participante y calcula su permanencia.

    Reglas de negocio aplicadas:
    1. La inscripción debe existir y estar en estado ACTIVA.
    2. El evento asociado no debe estar en estado CANCELADO.
    3. El registro de salidas del evento debe estar habilitado (salvo que el operador fuerce ignorar_bloqueo_salidas).
    4. Debe existir una Asistencia previa en estado REGISTRADA con hora_entrada.
       Si no existe entrada previa o está anulada, rechaza la salida.
    5. Si ya cuenta con hora_salida registrada y forzar_actualizacion es False:
       rechaza la duplicidad y retorna aviso con el registro previo y permanencia.
    6. Valida la secuencia temporal entre hora_entrada y hora_salida (soportando eventos que cruzan medianoche).
    7. Calcula el tiempo efectivo de permanencia (horas y minutos).
    8. Registra la auditoría correspondiente con la permanencia calculada.
    """
    if inscripcion.estado != EstadoInscripcion.ACTIVA:
        return {
            'exito': False,
            'codigo': 'INSCRIPCION_NO_ACTIVA',
            'mensaje': f"La inscripción se encuentra en estado '{inscripcion.get_estado_display()}'. No admite registro de salida.",
            'asistencia': None,
            'permanencia': None,
            'participante': inscripcion.participante,
            'evento': inscripcion.evento,
        }

    if hasattr(inscripcion, 'evento') and inscripcion.evento and inscripcion.evento.estado == 'CANCELADO':
        return {
            'exito': False,
            'codigo': 'EVENTO_CANCELADO',
            'mensaje': "No se puede registrar salida para un evento en estado CANCELADO.",
            'asistencia': None,
            'permanencia': None,
            'participante': inscripcion.participante,
            'evento': inscripcion.evento,
        }

    if hasattr(inscripcion, 'evento') and inscripcion.evento:
        if not ignorar_bloqueo_salidas and not es_salida_habilitada(inscripcion.evento):
            return {
                'exito': False,
                'codigo': 'SALIDAS_DESHABILITADAS',
                'mensaje': "El registro de salidas para este evento se encuentra cerrado o no ha sido habilitado por el organizador.",
                'asistencia': None,
                'permanencia': None,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

    ahora = timezone.localtime(timezone.now()) if getattr(settings, 'USE_TZ', False) else timezone.now()
    hora_actual = hora_salida_custom or ahora.time()

    with transaction.atomic():
        inscripcion_bloqueada = Inscripcion.objects.select_for_update().get(pk=inscripcion.pk)

        asistencia = getattr(inscripcion_bloqueada, 'asistencia', None)
        if asistencia is None:
            asistencia = Asistencia.objects.filter(inscripcion=inscripcion_bloqueada).first()

        if not asistencia or asistencia.estado != EstadoAsistencia.REGISTRADA:
            return {
                'exito': False,
                'codigo': 'ASISTENCIA_NO_REGISTRADA',
                'mensaje': f"El participante {inscripcion.participante} no cuenta con un registro de entrada previo válido.",
                'asistencia': None,
                'permanencia': None,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

        if not asistencia.hora_entrada:
            return {
                'exito': False,
                'codigo': 'HORA_ENTRADA_FALTANTE',
                'mensaje': f"El participante {inscripcion.participante} no tiene registrada una hora de entrada.",
                'asistencia': asistencia,
                'permanencia': None,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

        if asistencia.hora_salida and not forzar_actualizacion:
            perm = asistencia.permanencia
            texto_perm = perm['texto'] if perm else ''
            return {
                'exito': False,
                'codigo': 'SALIDA_YA_REGISTRADA',
                'mensaje': f"La salida de {inscripcion.participante} ya fue registrada a las {asistencia.hora_salida.strftime('%H:%M')}. Permanencia: {texto_perm}.",
                'asistencia': asistencia,
                'permanencia': perm,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

        asistencia.hora_salida = hora_actual
        if observaciones:
            asistencia.observaciones = f"{asistencia.observaciones or ''} [Salida: {observaciones}]".strip()

        # Validar coherencia mediante clean()
        try:
            asistencia.clean()
        except ValidationError as e:
            return {
                'exito': False,
                'codigo': 'VALIDACION_TEMPORAL_FALLIDA',
                'mensaje': e.message_dict.get('hora_salida', [str(e)])[0] if hasattr(e, 'message_dict') else str(e),
                'asistencia': asistencia,
                'permanencia': None,
                'participante': inscripcion.participante,
                'evento': inscripcion.evento,
            }

        asistencia.save()
        perm = asistencia.permanencia
        texto_perm = perm['texto'] if perm else 'calculada'

        Auditoria.objects.create(
            usuario=operador,
            accion='REGISTRAR_SALIDA_ASISTENCIA',
            modulo='ASISTENCIA',
            registro_afectado=f"Salida Asistencia ID {asistencia.pk} ({metodo}) - Inscripción {inscripcion.pk} - Permanencia: {texto_perm}",
            ip=ip
        )

        return {
            'exito': True,
            'codigo': 'SALIDA_REGISTRADA',
            'mensaje': f"¡Salida registrada con éxito para {inscripcion.participante}! Tiempo de permanencia: {texto_perm}.",
            'asistencia': asistencia,
            'permanencia': perm,
            'participante': inscripcion.participante,
            'evento': inscripcion.evento,
        }


def es_salida_habilitada(evento):
    """
    Determina si el registro de salidas está habilitado para el evento.
    Si existe ControlSalidaEvento, evalúa salidas_habilitadas y fecha_cierre.
    Si no existe aún instancia de control, permite compatibilidad con pruebas heredadas si no está cerrado.
    """
    try:
        from .models import ControlSalidaEvento
        control = ControlSalidaEvento.objects.filter(evento=evento).first()
        if control:
            return bool(control.salidas_habilitadas and control.fecha_cierre is None)
        return True
    except Exception:
        return False


def iniciar_sesion_salida_service(evento, operador=None, ip=None):
    """
    Inicia o reinicia de forma atómica y auditada la sesión de salida colectiva para el evento.
    Invalida cualquier código QR de sesiones previas.
    """
    from .models import ControlSalidaEvento
    with transaction.atomic():
        control, _ = ControlSalidaEvento.objects.get_or_create(
            evento=evento,
            defaults={'salidas_habilitadas': False}
        )
        sesion_id, nonce = control.iniciar_sesion(operador=operador)

        Auditoria.objects.create(
            usuario=operador,
            accion='INICIAR_SESION_SALIDA',
            modulo='ASISTENCIA',
            registro_afectado=f"Sesión {sesion_id} iniciada para Evento ID {evento.pk} - {evento.nombre}",
            ip=ip
        )
        return control


def cerrar_sesion_salida_service(evento, operador=None, ip=None):
    """
    Cierra de forma definitiva la sesión activa de salida colectiva bajo transacción.
    Invalida inmediatamente el nonce vigente e impide registros posteriores.
    """
    from .models import ControlSalidaEvento
    with transaction.atomic():
        control, _ = ControlSalidaEvento.objects.get_or_create(
            evento=evento,
            defaults={'salidas_habilitadas': False}
        )
        control.cerrar_sesion(operador=operador)

        Auditoria.objects.create(
            usuario=operador,
            accion='CERRAR_SESION_SALIDA',
            modulo='ASISTENCIA',
            registro_afectado=f"Sesión de salida cerrada para Evento ID {evento.pk} - {evento.nombre}",
            ip=ip
        )
        return control


def rotar_nonce_salida_service(evento, operador=None, ip=None):
    """
    Rota el nonce vigente de la sesión activa de salida colectiva.
    Invalida los códigos QR emitidos con el nonce anterior.
    """
    from .models import ControlSalidaEvento
    with transaction.atomic():
        control = ControlSalidaEvento.objects.filter(evento=evento).first()
        if not control or not control.salidas_habilitadas or control.fecha_cierre is not None:
            raise ValidationError("No se puede rotar el nonce de una sesión inactiva o cerrada.")
        nuevo_nonce = control.rotar_nonce()

        Auditoria.objects.create(
            usuario=operador,
            accion='ROTAR_NONCE_SALIDA',
            modulo='ASISTENCIA',
            registro_afectado=f"Nonce rotado para Evento ID {evento.pk} - {evento.nombre}",
            ip=ip
        )
        return nuevo_nonce


def toggle_salidas_evento_service(evento, habilitar=None, operador=None, ip=None):
    """
    Habilita o deshabilita el registro de salidas para un evento de forma atómica y auditada.
    Si habilitar es None, invierte el estado actual.
    """
    from .models import ControlSalidaEvento
    with transaction.atomic():
        control, _ = ControlSalidaEvento.objects.get_or_create(
            evento=evento,
            defaults={'salidas_habilitadas': False}
        )
        nuevo_estado = (not control.salidas_habilitadas) if habilitar is None else bool(habilitar)
        if nuevo_estado:
            if not control.sesion_id or control.fecha_cierre is not None:
                control.iniciar_sesion(operador=operador)
            else:
                control.salidas_habilitadas = True
                control.save()
        else:
            control.cerrar_sesion(operador=operador)

        accion = 'HABILITAR_SALIDAS_EVENTO' if nuevo_estado else 'DESHABILITAR_SALIDAS_EVENTO'
        Auditoria.objects.create(
            usuario=operador,
            accion=accion,
            modulo='ASISTENCIA',
            registro_afectado=f"Salidas {'habilitadas' if nuevo_estado else 'deshabilitadas'} para Evento ID {evento.pk} - {evento.nombre}",
            ip=ip
        )
        return nuevo_estado


def calcular_permanencia_promedio(evento):
    """
    Calcula la permanencia promedio (en minutos y texto) de los participantes
    que registraron tanto entrada como salida en el evento.
    """
    asistencias = Asistencia.objects.filter(
        inscripcion__evento=evento,
        inscripcion__estado=EstadoInscripcion.ACTIVA,
        estado=EstadoAsistencia.REGISTRADA,
        hora_entrada__isnull=False,
        hora_salida__isnull=False
    )
    total_minutos_acumulados = 0
    conteo = 0
    for a in asistencias:
        perm = a.permanencia
        if perm and perm.get('total_minutos') is not None:
            total_minutos_acumulados += perm['total_minutos']
            conteo += 1

    if conteo == 0:
        return {'promedio_minutos': 0, 'horas': 0, 'minutos': 0, 'texto': '--', 'conteo': 0}

    promedio_min = int(round(total_minutos_acumulados / conteo))
    horas = promedio_min // 60
    mins = promedio_min % 60
    texto = f"{horas}h {mins}m" if horas > 0 else f"{mins} min"
    return {
        'promedio_minutos': promedio_min,
        'horas': horas,
        'minutos': mins,
        'texto': texto,
        'conteo': conteo
    }


def construir_url_salida_evento(request, evento):
    """
    Construye la URL absoluta del QR común de salida de un evento.

    Reglas de resolución de red local (Fases 2 y 3):
    1. Si la petición en el navegador proviene de una dirección de loopback
       (127.0.0.1 o localhost), la sustituye por la IP privada local del equipo en la
       red Wi-Fi/LAN (ej. 192.168.1.10:8000), o por SIGAE_SERVER_HOST si está definida.
       De este modo, cuando un participante escanea el código con su teléfono celular,
       la URL apunta a la máquina real en la red local y no al loopback del propio teléfono.
    2. Incorpora el token criptográfico firmado con HMAC-SHA256 específico del evento.
    3. No expone documentos, correos ni datos personales en el QR.
    """
    import socket
    from django.urls import reverse

    token = generar_token_salida_evento(evento)
    path = reverse('asistencia:salida_evento_publica', args=[evento.pk])

    override_host = os.environ.get('SIGAE_SERVER_HOST', '').strip()
    if override_host:
        target_host = override_host
    else:
        req_host = request.get_host() if request else '127.0.0.1:8000'
        host_parts = req_host.split(':')
        host_name = host_parts[0].lower()
        port = host_parts[1] if len(host_parts) > 1 else ''
        port_suffix = f":{port}" if port else ''

        if host_name in ('127.0.0.1', 'localhost', 'testserver', '[::1]'):
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
                if local_ip.startswith('127.'):
                    local_ip = '192.168.1.10'
            except Exception:
                local_ip = '192.168.1.10'
            target_host = f"{local_ip}{port_suffix}"
        else:
            target_host = req_host

    scheme = 'https' if request and request.is_secure() else 'http'
    return f"{scheme}://{target_host}{path}?token_evento={token}"


