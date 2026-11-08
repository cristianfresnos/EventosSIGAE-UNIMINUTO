import base64
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.core import signing

from auditoria.models import Auditoria
from eventos.models import Evento
from participantes.models import Inscripcion, EstadoInscripcion, AccesoExternoInscripcion
from .models import Asistencia, MetodoAsistencia, EstadoAsistencia, ControlSalidaEvento
from .services import (
    SALT_QR,
    SALT_SALIDA_EVENTO,
    MAX_AGE_QR_LLEGADA,
    MAX_AGE_QR_SALIDA,
    generar_token_qr,
    decodificar_token_qr,
    generar_token_salida_evento,
    decodificar_token_salida_evento,
    validar_token_salida_evento,
    generar_imagen_qr_bytes,
    registrar_asistencia_llegada,
    registrar_asistencia_salida,
    es_salida_habilitada,
    iniciar_sesion_salida_service,
    cerrar_sesion_salida_service,
    rotar_nonce_salida_service,
    toggle_salidas_evento_service,
    calcular_permanencia_promedio,
    construir_url_salida_evento,
)


def get_client_ip(request):
    """Obtiene la dirección IP del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def tiene_permiso_evento(user, evento):
    """Determina si un usuario tiene permisos de gestión y asistencia sobre un evento."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Administrador', 'Coordinador']:
        return True
    if evento.organizador_id == user.id:
        return True
    return False


def pase_digital(request, id_inscripcion):
    """
    Vista del pase digital institucional para el participante.
    Muestra los detalles del evento, los datos del participante y su código QR firmado.
    """
    inscripcion = get_object_or_404(
        Inscripcion.objects.select_related('evento', 'participante', 'asistencia'),
        pk=id_inscripcion
    )

    token_param = request.GET.get('token')
    es_propietario = False

    # Verificación de acceso institucional o externo
    if request.user.is_authenticated:
        if (
            inscripcion.participante.usuario_id == request.user.id
            or tiene_permiso_evento(request.user, inscripcion.evento)
        ):
            es_propietario = True
    elif request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(**filtros_acceso).first()
        if acceso and acceso.inscripcion_id == inscripcion.pk and acceso.es_valido:
            es_propietario = True

    if not es_propietario and token_param:
        acceso_tok = AccesoExternoInscripcion.validar_token(token_param)
        if acceso_tok and acceso_tok.inscripcion_id == inscripcion.pk:
            es_propietario = True
            request.session['acceso_externo_id'] = acceso_tok.pk
            request.session['acceso_externo_hash'] = acceso_tok.token_hash
        else:
            try:
                payload = decodificar_token_qr(token_param)
                if payload.get('ins') == inscripcion.pk and payload.get('evt') == inscripcion.evento_id:
                    es_propietario = True
            except (signing.BadSignature, signing.SignatureExpired):
                es_propietario = False

    if not es_propietario:
        if not request.user.is_authenticated:
            if token_param:
                raise PermissionDenied("El token del pase digital es inválido o no corresponde a esta inscripción.")
            return redirect(f"/usuarios/login/?next=/asistencia/inscripcion/{id_inscripcion}/pase/")
        raise PermissionDenied("No tienes autorización para consultar este pase digital.")

    token_qr = generar_token_qr(inscripcion)
    qr_bytes = generar_imagen_qr_bytes(token_qr)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    asistencia = getattr(inscripcion, 'asistencia', None)
    llegada_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_entrada)
    salida_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_salida)

    return render(request, 'asistencia/pase_digital.html', {
        'inscripcion': inscripcion,
        'token_qr': token_qr,
        'qr_base64': qr_base64,
        'evento': inscripcion.evento,
        'participante': inscripcion.participante,
        'asistencia': asistencia,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
    })


def descargar_qr_imagen(request, id_inscripcion):
    """
    Descarga la imagen del código QR en formato PNG bajo demanda en memoria.
    """
    inscripcion = get_object_or_404(
        Inscripcion.objects.select_related('evento', 'participante'),
        pk=id_inscripcion
    )

    token_param = request.GET.get('token')
    es_propietario = False

    if request.user.is_authenticated:
        if (
            inscripcion.participante.usuario_id == request.user.id
            or tiene_permiso_evento(request.user, inscripcion.evento)
        ):
            es_propietario = True
    elif request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(**filtros_acceso).first()
        if acceso and acceso.inscripcion_id == inscripcion.pk and acceso.es_valido:
            es_propietario = True

    if not es_propietario and token_param:
        acceso_tok = AccesoExternoInscripcion.validar_token(token_param)
        if acceso_tok and acceso_tok.inscripcion_id == inscripcion.pk:
            es_propietario = True
            request.session['acceso_externo_id'] = acceso_tok.pk
            request.session['acceso_externo_hash'] = acceso_tok.token_hash
        else:
            try:
                payload = decodificar_token_qr(token_param)
                if payload.get('ins') == inscripcion.pk and payload.get('evt') == inscripcion.evento_id:
                    es_propietario = True
            except (signing.BadSignature, signing.SignatureExpired):
                es_propietario = False

    if not es_propietario:
        if not request.user.is_authenticated:
            if token_param:
                raise PermissionDenied("El token del código QR es inválido o no corresponde a esta inscripción.")
            return redirect(f"/usuarios/login/?next=/asistencia/inscripcion/{id_inscripcion}/qr-imagen/")
        raise PermissionDenied("No tienes autorización para descargar este código QR.")

    token_qr = generar_token_qr(inscripcion)
    qr_bytes = generar_imagen_qr_bytes(token_qr, formato='PNG')

    filename = f"pase_qr_evento_{inscripcion.evento_id}_inscripcion_{inscripcion.pk}.png"
    response = HttpResponse(qr_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def qr_dinamico(request, id_inscripcion):
    """
    Retorna en formato JSON un código QR personal de llegada recién generado con rotación dinámica (30 segundos).
    Valida la autorización del participante (institucional con sesión o externo mediante acceso seguro).
    No expone nombres, documentos ni datos personales dentro del contenido del token QR.
    """
    inscripcion = get_object_or_404(
        Inscripcion.objects.select_related('evento', 'participante', 'asistencia'),
        pk=id_inscripcion
    )

    es_autorizado = False
    if request.user.is_authenticated:
        if (
            inscripcion.participante.usuario_id == request.user.id
            or tiene_permiso_evento(request.user, inscripcion.evento)
        ):
            es_autorizado = True
    elif request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(**filtros_acceso).first()
        if acceso and acceso.inscripcion_id == inscripcion.pk and acceso.es_valido:
            es_autorizado = True

    if not es_autorizado:
        raw_token = (request.GET.get('token') or request.GET.get('token_acceso') or '').strip()
        if raw_token:
            acceso = AccesoExternoInscripcion.validar_token(raw_token)
            if acceso and acceso.inscripcion_id == inscripcion.pk:
                es_autorizado = True
                request.session['acceso_externo_id'] = acceso.pk
                request.session['acceso_externo_hash'] = acceso.token_hash
            else:
                try:
                    payload = decodificar_token_qr(raw_token)
                    if payload.get('ins') == inscripcion.pk and payload.get('evt') == inscripcion.evento_id:
                        es_autorizado = True
                except (signing.BadSignature, signing.SignatureExpired):
                    pass

    if not es_autorizado:
        return JsonResponse({
            'exito': False,
            'codigo': 'NO_AUTORIZADO',
            'mensaje': "No tienes autorización para consultar el código QR dinámico de esta inscripción."
        }, status=403)

    if inscripcion.estado != EstadoInscripcion.ACTIVA:
        return JsonResponse({
            'exito': False,
            'codigo': 'INSCRIPCION_NO_ACTIVA',
            'mensaje': f"La inscripción se encuentra en estado '{inscripcion.get_estado_display()}'. El código QR no está disponible."
        }, status=400)

    token_qr = generar_token_qr(inscripcion)
    qr_bytes = generar_imagen_qr_bytes(token_qr)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    asistencia = getattr(inscripcion, 'asistencia', None)
    llegada_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_entrada)
    salida_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_salida)

    return JsonResponse({
        'exito': True,
        'token': token_qr,
        'token_qr': token_qr,
        'qr_base64': qr_base64,
        'rotacion_segundos': 30,
        'id_inscripcion': inscripcion.pk,
        'evento_id': inscripcion.evento_id,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
        'hora_entrada': asistencia.hora_entrada.strftime('%H:%M:%S') if llegada_registrada else None,
        'hora_salida': asistencia.hora_salida.strftime('%H:%M:%S') if salida_registrada else None,
        'permanencia': asistencia.tiempo_permanencia_str if (salida_registrada and asistencia) else '',
    })


@login_required
def control_asistencia(request, id_evento):
    """
    Panel móvil y de escritorio para control de asistencia de organizadores.
    Soporta validación de códigos QR mediante cámara y búsqueda manual de participantes.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para gestionar la asistencia de este evento.")

    # Procesar solicitudes de registro (POST)
    if request.method == 'POST':
        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or request.content_type == 'application/json'
            or request.GET.get('format') == 'json'
        )

        accion = request.POST.get('accion')
        token_qr = request.POST.get('token_qr')
        id_inscripcion = request.POST.get('id_inscripcion')
        tipo_registro = request.POST.get('tipo_registro', 'entrada')
        if accion in ['registrar_salida', 'registrar_manual_salida']:
            tipo_registro = 'salida'

        if request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body)
                token_qr = token_qr or body_data.get('token_qr')
                id_inscripcion = id_inscripcion or body_data.get('id_inscripcion')
                accion = accion or body_data.get('accion')
                tipo_registro = body_data.get('tipo_registro', tipo_registro)
                if accion in ['registrar_salida', 'registrar_manual_salida']:
                    tipo_registro = 'salida'
            except Exception:
                pass

        ip_cliente = get_client_ip(request)

        # CASO 1: Validación por Código QR
        if token_qr:
            token_qr_clean = token_qr.strip()
            # Detección específica: ¿Se escaneó el QR común de salida en el lector del operador?
            if '/salida/' in token_qr_clean or 'token_evento' in token_qr_clean or 'token_salida' in token_qr_clean:
                msg_error = (
                    "Has escaneado el código QR común de SALIDA del evento. "
                    "Este código no es un pase personal de asistencia; está destinado a ser "
                    "escaneado por los participantes desde sus celulares para registrar su salida."
                )
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'QR_SALIDA_COMUN_NO_ES_PASE', 'mensaje': msg_error}, status=400)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)

            try:
                payload = decodificar_token_qr(token_qr_clean, max_age=MAX_AGE_QR_LLEGADA)
                id_ins = payload.get('ins')
                id_evt = payload.get('evt')
            except signing.SignatureExpired:
                msg_error = "El código QR presentado ha expirado (ventana de validez superada). El participante debe actualizar su pase."
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'QR_EXPIRADO', 'mensaje': msg_error}, status=400)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)
            except signing.BadSignature:
                msg_error = "El código QR presentado es inválido, ha caducado o fue alterado."
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'QR_INVALIDO', 'mensaje': msg_error}, status=400)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)

            # Validar que pertenezca al evento en curso
            if id_evt != evento.pk:
                msg_error = f"El código QR presentado corresponde a otro evento institucional (ID {id_evt}). No es válido para este evento."
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'EVENTO_INCORRECTO', 'mensaje': msg_error}, status=400)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)

            inscripcion = Inscripcion.objects.filter(pk=id_ins, evento=evento).select_related('participante', 'asistencia').first()
            if not inscripcion:
                msg_error = "No se encontró registro de inscripción asociado a este código QR."
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'INSCRIPCION_NO_EXISTE', 'mensaje': msg_error}, status=404)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)

            if inscripcion.estado != EstadoInscripcion.ACTIVA:
                msg_error = f"La inscripción se encuentra en estado '{inscripcion.get_estado_display()}'. No admite registro de asistencia."
                if is_ajax:
                    return JsonResponse({'exito': False, 'codigo': 'INSCRIPCION_NO_ACTIVA', 'mensaje': msg_error}, status=200)
                messages.error(request, msg_error)
                return redirect('asistencia:control_asistencia', id_evento=evento.pk)

            if tipo_registro == 'salida':
                resultado = registrar_asistencia_salida(
                    inscripcion,
                    metodo=MetodoAsistencia.QR,
                    operador=request.user,
                    ip=ip_cliente
                )
            else:
                resultado = registrar_asistencia_llegada(
                    inscripcion,
                    metodo=MetodoAsistencia.QR,
                    operador=request.user,
                    ip=ip_cliente
                )

            hora_salida_str = resultado['asistencia'].hora_salida.strftime('%H:%M:%S') if resultado.get('asistencia') and resultado['asistencia'].hora_salida else ''
            hora_entrada_str = resultado['asistencia'].hora_entrada.strftime('%H:%M:%S') if resultado.get('asistencia') and resultado['asistencia'].hora_entrada else ''
            permanencia_str = resultado.get('permanencia', {}).get('texto', '') if resultado.get('permanencia') else (resultado['asistencia'].tiempo_permanencia_str if resultado.get('asistencia') else '')

            if is_ajax:
                return JsonResponse({
                    'exito': resultado['exito'],
                    'codigo': resultado['codigo'],
                    'mensaje': resultado['mensaje'],
                    'tipo_registro': tipo_registro,
                    'participante': f"{inscripcion.participante.nombres} {inscripcion.participante.apellidos}",
                    'tipo': inscripcion.participante.get_tipo_display(),
                    'documento': inscripcion.participante.documento,
                    'hora': hora_salida_str if tipo_registro == 'salida' else hora_entrada_str,
                    'hora_entrada': hora_entrada_str,
                    'hora_salida': hora_salida_str,
                    'permanencia': permanencia_str,
                })

            if resultado['exito']:
                messages.success(request, resultado['mensaje'])
            else:
                messages.warning(request, resultado['mensaje'])
            return redirect('asistencia:control_asistencia', id_evento=evento.pk)

        # CASO 2: Registro Manual por Selección de Inscripción
        elif id_inscripcion:
            inscripcion = get_object_or_404(
                Inscripcion.objects.select_related('participante', 'asistencia'),
                pk=id_inscripcion,
                evento=evento
            )

            if tipo_registro == 'salida':
                resultado = registrar_asistencia_salida(
                    inscripcion,
                    metodo=MetodoAsistencia.MANUAL,
                    operador=request.user,
                    ip=ip_cliente,
                    observaciones=request.POST.get('observaciones')
                )
            else:
                resultado = registrar_asistencia_llegada(
                    inscripcion,
                    metodo=MetodoAsistencia.MANUAL,
                    operador=request.user,
                    ip=ip_cliente,
                    observaciones=request.POST.get('observaciones')
                )

            hora_salida_str = resultado['asistencia'].hora_salida.strftime('%H:%M:%S') if resultado.get('asistencia') and resultado['asistencia'].hora_salida else ''
            hora_entrada_str = resultado['asistencia'].hora_entrada.strftime('%H:%M:%S') if resultado.get('asistencia') and resultado['asistencia'].hora_entrada else ''
            permanencia_str = resultado.get('permanencia', {}).get('texto', '') if resultado.get('permanencia') else (resultado['asistencia'].tiempo_permanencia_str if resultado.get('asistencia') else '')

            if is_ajax:
                return JsonResponse({
                    'exito': resultado['exito'],
                    'codigo': resultado['codigo'],
                    'mensaje': resultado['mensaje'],
                    'tipo_registro': tipo_registro,
                    'participante': f"{inscripcion.participante.nombres} {inscripcion.participante.apellidos}",
                    'tipo': inscripcion.participante.get_tipo_display(),
                    'documento': inscripcion.participante.documento,
                    'hora': hora_salida_str if tipo_registro == 'salida' else hora_entrada_str,
                    'hora_entrada': hora_entrada_str,
                    'hora_salida': hora_salida_str,
                    'permanencia': permanencia_str,
                })

            if resultado['exito']:
                messages.success(request, resultado['mensaje'])
            else:
                messages.warning(request, resultado['mensaje'])
            return redirect('asistencia:control_asistencia', id_evento=evento.pk)

        else:
            msg_error = "Solicitud incompleta: no se proporcionó código QR ni inscripción válida."
            if is_ajax:
                return JsonResponse({'exito': False, 'codigo': 'DATOS_FALTANTES', 'mensaje': msg_error}, status=400)
            messages.error(request, msg_error)
            return redirect('asistencia:control_asistencia', id_evento=evento.pk)

    # Vista GET: Panel móvil y listado de participantes
    q = request.GET.get('q', '').strip()
    filtro_asistencia = request.GET.get('filtro_asistencia', 'todos').strip().lower()
    if filtro_asistencia not in ['todos', 'asistieron', 'ausentes', 'sin_salida', 'salieron']:
        filtro_asistencia = 'todos'

    # Métricas consolidadas del evento (siempre sobre el universo activo del evento)
    total_inscritos = Inscripcion.objects.filter(evento=evento, estado=EstadoInscripcion.ACTIVA).count()
    total_asistieron = Asistencia.objects.filter(
        inscripcion__evento=evento,
        inscripcion__estado=EstadoInscripcion.ACTIVA,
        estado=EstadoAsistencia.REGISTRADA
    ).count()
    total_salidas = Asistencia.objects.filter(
        inscripcion__evento=evento,
        inscripcion__estado=EstadoInscripcion.ACTIVA,
        estado=EstadoAsistencia.REGISTRADA,
        hora_salida__isnull=False
    ).count()
    total_ausentes = max(0, total_inscritos - total_asistieron)
    total_sin_salida = max(0, total_asistieron - total_salidas)
    porcentaje = round((total_asistieron / total_inscritos * 100), 1) if total_inscritos > 0 else 0
    permanencia_promedio = calcular_permanencia_promedio(evento)
    salidas_habilitadas = es_salida_habilitada(evento)
    token_salida_evento = generar_token_salida_evento(evento)
    url_salida_evento = construir_url_salida_evento(request, evento)

    # Consulta base para la lista tabular
    inscripciones_qs = (
        Inscripcion.objects.filter(evento=evento)
        .select_related('participante', 'asistencia')
        .order_by('participante__apellidos', 'participante__nombres')
    )

    # Aplicar filtro de estado de asistencia
    if filtro_asistencia == 'asistieron':
        inscripciones_qs = inscripciones_qs.filter(
            estado=EstadoInscripcion.ACTIVA,
            asistencia__estado=EstadoAsistencia.REGISTRADA
        )
    elif filtro_asistencia == 'ausentes':
        inscripciones_qs = inscripciones_qs.filter(estado=EstadoInscripcion.ACTIVA).filter(
            Q(asistencia__isnull=True) | Q(asistencia__estado=EstadoAsistencia.ANULADA)
        )
    elif filtro_asistencia == 'sin_salida':
        inscripciones_qs = inscripciones_qs.filter(
            estado=EstadoInscripcion.ACTIVA,
            asistencia__estado=EstadoAsistencia.REGISTRADA,
            asistencia__hora_salida__isnull=True
        )
    elif filtro_asistencia == 'salieron':
        inscripciones_qs = inscripciones_qs.filter(
            estado=EstadoInscripcion.ACTIVA,
            asistencia__estado=EstadoAsistencia.REGISTRADA,
            asistencia__hora_salida__isnull=False
        )

    # Aplicar búsqueda textual si se proporcionó
    if q:
        inscripciones_qs = inscripciones_qs.filter(
            Q(participante__nombres__icontains=q) |
            Q(participante__apellidos__icontains=q) |
            Q(participante__documento__icontains=q) |
            Q(participante__correo__icontains=q)
        )

    inscripciones = list(inscripciones_qs)

    return render(request, 'asistencia/control_asistencia.html', {
        'evento': evento,
        'inscripciones': inscripciones,
        'total_inscritos': total_inscritos,
        'total_asistieron': total_asistieron,
        'total_salidas': total_salidas,
        'total_ausentes': total_ausentes,
        'total_sin_salida': total_sin_salida,
        'porcentaje': porcentaje,
        'permanencia_promedio': permanencia_promedio,
        'salidas_habilitadas': salidas_habilitadas,
        'token_salida_evento': token_salida_evento,
        'url_salida_evento': url_salida_evento,
        'filtro_asistencia': filtro_asistencia,
        'q': q,
    })


@login_required
def toggle_salidas_evento(request, id_evento):
    """
    Permite al organizador habilitar o deshabilitar el registro masivo de salidas
    para el evento correspondiente.
    """
    if request.method != 'POST':
        messages.error(request, "El cambio de estado de salidas debe realizarse mediante solicitud POST.")
        return redirect('asistencia:control_asistencia', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para modificar la configuración de este evento.")

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    habilitar_param = request.POST.get('habilitar')
    habilitar_bool = None
    if habilitar_param is not None:
        habilitar_bool = habilitar_param.lower() in ['true', '1', 'si', 'on']

    ip_cliente = get_client_ip(request)
    nuevo_estado = toggle_salidas_evento_service(
        evento,
        habilitar=habilitar_bool,
        operador=request.user,
        ip=ip_cliente
    )

    msg = f"Registro de salidas {'habilitado' if nuevo_estado else 'deshabilitado'} exitosamente para este evento."
    if is_ajax:
        return JsonResponse({
            'exito': True,
            'salidas_habilitadas': nuevo_estado,
            'mensaje': msg
        })

    if nuevo_estado:
        messages.success(request, msg)
    else:
        messages.warning(request, msg)
    return redirect('asistencia:control_asistencia', id_evento=evento.pk)


@login_required
def descargar_qr_salida_imagen(request, id_evento):
    """
    Genera y descarga en memoria la imagen PNG del código QR común de salida del evento.
    El QR contiene la URL pública de salida firmada con token.
    """
    evento = get_object_or_404(Evento, pk=id_evento)
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para acceder al QR de salida de este evento.")

    url_salida = construir_url_salida_evento(request, evento)
    qr_bytes = generar_imagen_qr_bytes(url_salida, formato='PNG')
    filename = f"qr_salida_evento_{evento.pk}.png"
    response = HttpResponse(qr_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def salida_evento_publica(request, id_evento):
    """
    Página pública de registro de salida escaneada por participantes mediante el QR común.
    Valida el token colectivo del evento como autorización temporal de salida y
    resuelve la identidad del participante EXCLUSIVAMENTE mediante contexto de sesión:
      - request.user para participantes institucionales.
      - request.session['acceso_externo_id'] para participantes externos con enlace vigente.
    Ningún dato enviado manualmente por formulario (documento, correo, ID) es admitido
    para prevenir cualquier tipo de suplantación de identidad (anti-IDOR).
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    # Validar token criptográfico del evento e integración con ControlSalidaEvento
    token_evento = (
        request.GET.get('token_evento')
        or request.POST.get('token_evento')
        or request.GET.get('token')
        or request.POST.get('token')
    )
    if not token_evento:
        raise PermissionDenied("Se requiere un código QR de salida válido para acceder a esta página.")

    valido, payload_evento, err_msg = validar_token_salida_evento(token_evento, evento)
    if not valido and payload_evento != 'SESION_CERRADA':
        raise PermissionDenied(err_msg)

    salidas_activas = es_salida_habilitada(evento) and (payload_evento != 'SESION_CERRADA')
    ip_cliente = get_client_ip(request)

    # Identificación estricta por sesión (Institucional o Externa)
    inscripcion_usuario = None
    if request.user.is_authenticated:
        inscripcion_usuario = Inscripcion.objects.filter(
            evento=evento,
            participante__usuario=request.user,
            estado=EstadoInscripcion.ACTIVA
        ).select_related('participante', 'asistencia').first()

    inscripcion_externa = None
    if request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(
            **filtros_acceso
        ).select_related('inscripcion', 'inscripcion__participante', 'inscripcion__asistencia').first()
        if acceso and acceso.es_valido and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
            inscripcion_externa = acceso.inscripcion

    if not inscripcion_externa and not request.user.is_authenticated:
        token_acceso = request.GET.get('token_acceso') or request.POST.get('token_acceso')
        if token_acceso:
            acceso = AccesoExternoInscripcion.validar_token(token_acceso)
            if acceso and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
                inscripcion_externa = acceso.inscripcion
                request.session['acceso_externo_id'] = acceso.pk
                request.session['acceso_externo_hash'] = acceso.token_hash

    inscripcion_target = inscripcion_usuario or inscripcion_externa
    resultado = None

    if request.method == 'POST':
        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or request.content_type == 'application/json'
        )

        if not salidas_activas:
            msg_bloqueo = "El registro de salidas para este evento se encuentra cerrado o no ha sido habilitado por el organizador."
            if is_ajax:
                return JsonResponse({'exito': False, 'codigo': 'SALIDAS_DESHABILITADAS', 'mensaje': msg_bloqueo}, status=400)
            resultado = {'exito': False, 'codigo': 'SALIDAS_DESHABILITADAS', 'mensaje': msg_bloqueo}
            return render(request, 'asistencia/salida_evento.html', {
                'evento': evento,
                'token_evento': token_evento,
                'salidas_activas': salidas_activas,
                'resultado': resultado,
                'inscripcion_usuario': inscripcion_target,
            })

        # Bloqueo total de identificación manual: sólo identidades verificadas en sesión
        if not inscripcion_target:
            msg_no_sesion = (
                "No se detectó una sesión activa ni un acceso de participante externo válido para este evento. "
                "Por motivos de seguridad institucional y prevención de suplantación, no está permitido "
                "el registro de salida mediante número de documento, correo o identificación manual. "
                "Debes iniciar sesión con tu cuenta institucional o ingresar mediante tu enlace personal de participante externo."
            )
            if is_ajax:
                return JsonResponse({
                    'exito': False,
                    'codigo': 'IDENTIDAD_NO_AUTENTICADA',
                    'mensaje': msg_no_sesion
                }, status=403)
            resultado = {
                'exito': False,
                'codigo': 'IDENTIDAD_NO_AUTENTICADA',
                'mensaje': msg_no_sesion
            }
            return render(request, 'asistencia/salida_evento.html', {
                'evento': evento,
                'token_evento': token_evento,
                'salidas_activas': salidas_activas,
                'resultado': resultado,
                'inscripcion_usuario': None,
            })

        # Registrar salida utilizando exclusivamente la identidad de la sesión validada
        resultado = registrar_asistencia_salida(
            inscripcion_target,
            metodo=MetodoAsistencia.QR,
            operador=request.user if request.user.is_authenticated else None,
            ip=ip_cliente,
            observaciones="Salida confirmada mediante QR colectivo con identidad de sesión validada"
        )
        if is_ajax:
            return JsonResponse({
                'exito': resultado['exito'],
                'codigo': resultado['codigo'],
                'mensaje': resultado['mensaje'],
                'permanencia': resultado.get('permanencia', {}).get('texto', '') if resultado.get('permanencia') else '',
                'participante': f"{inscripcion_target.participante.nombres} {inscripcion_target.participante.apellidos}",
            })

    return render(request, 'asistencia/salida_evento.html', {
        'evento': evento,
        'token_evento': token_evento,
        'salidas_activas': salidas_activas,
        'resultado': resultado,
        'inscripcion_usuario': inscripcion_target,
    })


@login_required
def anular_asistencia(request, id_asistencia):
    """
    Permite a un organizador autorizado anular un registro de asistencia erróneo.
    Requiere método POST y genera auditoría.
    """
    if request.method != 'POST':
        messages.error(request, "La anulación de asistencia debe realizarse mediante solicitud POST.")
        return redirect('eventos:mis_eventos')

    asistencia = get_object_or_404(
        Asistencia.objects.select_related('inscripcion', 'inscripcion__evento', 'inscripcion__participante'),
        pk=id_asistencia
    )

    evento = asistencia.inscripcion.evento
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para anular asistencias en este evento.")

    if asistencia.estado == EstadoAsistencia.ANULADA:
        messages.info(request, "Esta asistencia ya se encontraba en estado ANULADA.")
        return redirect('asistencia:control_asistencia', id_evento=evento.pk)

    asistencia.estado = EstadoAsistencia.ANULADA
    motivo = request.POST.get('motivo', '').strip()
    if motivo:
        asistencia.observaciones = f"{asistencia.observaciones or ''} [Anulado: {motivo}]".strip()
    asistencia.save()

    Auditoria.objects.create(
        usuario=request.user,
        accion='ANULAR_ASISTENCIA',
        modulo='ASISTENCIA',
        registro_afectado=f"Asistencia ID {asistencia.pk} anulada - Participante {asistencia.inscripcion.participante.documento} - Evento {evento.pk}",
        ip=get_client_ip(request)
    )

    messages.warning(request, f"La asistencia de {asistencia.inscripcion.participante} fue anulada correctamente.")
    return redirect('asistencia:control_asistencia', id_evento=evento.pk)


@login_required
def iniciar_sesion_salida(request, id_evento):
    """
    Inicia una sesión de salida colectiva formal para el evento (profesor u organizador).
    Genera sesion_id único y nonce vigente, invalidando códigos anteriores.
    """
    if request.method != 'POST':
        messages.error(request, "La habilitación de salidas debe realizarse mediante solicitud POST.")
        return redirect('asistencia:control_asistencia', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para gestionar la sesión de salidas de este evento.")

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    ip_cliente = get_client_ip(request)
    control = iniciar_sesion_salida_service(evento, operador=request.user, ip=ip_cliente)

    token_salida = generar_token_salida_evento(evento, control=control)
    url_salida = construir_url_salida_evento(request, evento)
    qr_bytes = generar_imagen_qr_bytes(url_salida)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    msg = f"Sesión de salida #{control.sesion_id} iniciada exitosamente. Registro de salidas habilitado."
    if is_ajax:
        return JsonResponse({
            'exito': True,
            'salidas_habilitadas': True,
            'sesion_id': control.sesion_id,
            'token_salida': token_salida,
            'url_salida': url_salida,
            'qr_base64': qr_base64,
            'mensaje': msg
        })

    messages.success(request, msg)
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('asistencia:control_asistencia', id_evento=evento.pk)


@login_required
def cerrar_sesion_salida(request, id_evento):
    """
    Cierra definitivamente la sesión de salida colectiva para el evento (profesor u organizador).
    Invalida de inmediato el nonce y bloquea cualquier registro posterior.
    """
    if request.method != 'POST':
        messages.error(request, "El cierre de sesión de salidas debe realizarse mediante solicitud POST.")
        return redirect('asistencia:control_asistencia', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para gestionar la sesión de salidas de este evento.")

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )
    ip_cliente = get_client_ip(request)
    control = cerrar_sesion_salida_service(evento, operador=request.user, ip=ip_cliente)

    msg = "Sesión de salida cerrada exitosamente. Códigos anteriores invalidados."
    if is_ajax:
        return JsonResponse({
            'exito': True,
            'salidas_habilitadas': False,
            'sesion_id': control.sesion_id,
            'mensaje': msg
        })

    messages.warning(request, msg)
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('asistencia:control_asistencia', id_evento=evento.pk)


@login_required
def rotar_nonce_salida(request, id_evento):
    """
    Rota el nonce vigente de la sesión de salida y retorna un nuevo código QR de proyección.
    Invalida los códigos QR emitidos previamente.
    """
    evento = get_object_or_404(Evento, pk=id_evento)
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para rotar la sesión de salidas de este evento.")

    ip_cliente = get_client_ip(request)
    try:
        nuevo_nonce = rotar_nonce_salida_service(evento, operador=request.user, ip=ip_cliente)
    except Exception as e:
        return JsonResponse({'exito': False, 'codigo': 'ROTACION_FALLIDA', 'mensaje': str(e)}, status=400)

    control = ControlSalidaEvento.objects.filter(evento=evento).first()
    token_salida = generar_token_salida_evento(evento, control=control)
    url_salida = construir_url_salida_evento(request, evento)
    qr_bytes = generar_imagen_qr_bytes(url_salida)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    return JsonResponse({
        'exito': True,
        'sesion_id': control.sesion_id,
        'token_salida': token_salida,
        'url_salida': url_salida,
        'qr_base64': qr_base64,
        'rotacion_segundos': 30,
        'mensaje': "Código QR de salida actualizado exitosamente."
    })


@login_required
def proyector_salida(request, id_evento):
    """
    Vista de proyección en pantalla completa del código QR colectivo de salida.
    Permite al profesor proyectar el QR en pantalla grande con actualización y contadores en vivo.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )
    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para acceder a la pantalla de proyección de salida de este evento.")

    control, _ = ControlSalidaEvento.objects.get_or_create(
        evento=evento,
        defaults={'salidas_habilitadas': False}
    )

    token_salida = generar_token_salida_evento(evento, control=control)
    url_salida = construir_url_salida_evento(request, evento)
    qr_bytes = generar_imagen_qr_bytes(url_salida)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    total_llegadas = Asistencia.objects.filter(
        inscripcion__evento=evento,
        estado=EstadoAsistencia.REGISTRADA,
        hora_entrada__isnull=False
    ).count()

    total_salidas = Asistencia.objects.filter(
        inscripcion__evento=evento,
        estado=EstadoAsistencia.REGISTRADA,
        hora_salida__isnull=False
    ).count()

    return render(request, 'asistencia/proyector_salida.html', {
        'evento': evento,
        'control': control,
        'token_salida': token_salida,
        'url_salida': url_salida,
        'qr_base64': qr_base64,
        'total_llegadas': total_llegadas,
        'total_salidas': total_salidas,
        'salidas_habilitadas': control.salidas_habilitadas,
    })


def registrar_salida_participante(request, id_evento):
    """
    Endpoint seguro para que un participante (institucional o externo) registre su salida
    al escanear el QR colectivo mostrado por el profesor.

    REGLAS DE IDENTIDAD Y SEGURIDAD:
    - La identidad se obtiene EXCLUSIVAMENTE de la sesión autenticada institucional o del
      contexto de AccesoExternoInscripcion en sesión.
    - NO se aceptan números de documento, correos ni identificadores enviados libremente en POST.
    - Valida firma, vigencia temporal y sesión activa del token_salida.
    - Requiere llegada registrada previa y bloquea salidas duplicadas.
    - Opera bajo transacción atómica y registra auditoría.
    """
    if request.method != 'POST':
        return JsonResponse({'exito': False, 'codigo': 'METODO_NO_PERMITIDO', 'mensaje': "Se requiere método POST."}, status=405)

    evento = get_object_or_404(Evento, pk=id_evento)
    ip_cliente = get_client_ip(request)

    # 1. Resolver identidad del participante de forma estricta desde la sesión
    inscripcion = None
    if request.user.is_authenticated:
        inscripcion = Inscripcion.objects.filter(
            evento=evento,
            participante__usuario=request.user,
            estado=EstadoInscripcion.ACTIVA
        ).select_related('participante', 'asistencia').first()
    elif request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(
            **filtros_acceso
        ).select_related('inscripcion', 'inscripcion__participante', 'inscripcion__asistencia').first()
        if acceso and acceso.es_valido and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
            inscripcion = acceso.inscripcion

    if not inscripcion and not request.user.is_authenticated:
        token_acceso = request.POST.get('token_acceso') or request.GET.get('token')
        if token_acceso:
            acceso = AccesoExternoInscripcion.validar_token(token_acceso)
            if acceso and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
                inscripcion = acceso.inscripcion
                request.session['acceso_externo_id'] = acceso.pk
                request.session['acceso_externo_hash'] = acceso.token_hash

    if not inscripcion:
        return JsonResponse({
            'exito': False,
            'codigo': 'NO_AUTORIZADO',
            'mensaje': "No se identificó una sesión activa de participante para este evento. "
                       "Debes iniciar sesión con tu cuenta institucional o abrir tu enlace personal de inscripción."
        }, status=403)

    # 2. Validar el token de salida escaneado
    token_salida = (
        request.POST.get('token_salida')
        or request.POST.get('token_evento')
        or request.POST.get('token')
    )
    if not token_salida and request.content_type == 'application/json':
        try:
            body = json.loads(request.body)
            token_salida = body.get('token_salida') or body.get('token_evento') or body.get('token')
        except Exception:
            pass

    if not token_salida:
        return JsonResponse({
            'exito': False,
            'codigo': 'TOKEN_FALTANTE',
            'mensaje': "No se proporcionó el código QR de salida escaneado."
        }, status=400)

    token_salida = token_salida.strip()
    if 'token_evento=' in token_salida or 'token_salida=' in token_salida or 'token=' in token_salida:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(token_salida)
        qs = parse_qs(parsed.query)
        token_salida = (
            (qs.get('token_salida') and qs['token_salida'][0])
            or (qs.get('token_evento') and qs['token_evento'][0])
            or (qs.get('token') and qs['token'][0])
            or token_salida
        )

    valido, payload, err_msg = validar_token_salida_evento(token_salida, evento)
    if not valido:
        return JsonResponse({
            'exito': False,
            'codigo': payload,
            'mensaje': err_msg
        }, status=400)

    # 3. Registrar salida atómica mediante el servicio
    resultado = registrar_asistencia_salida(
        inscripcion,
        metodo=MetodoAsistencia.QR,
        operador=request.user if request.user.is_authenticated else None,
        ip=ip_cliente,
        observaciones="Salida registrada mediante escaneo de QR colectivo"
    )

    status_code = 200 if resultado['exito'] else 400
    if resultado.get('codigo') == 'SALIDA_YA_REGISTRADA':
        status_code = 200

    return JsonResponse({
        'exito': resultado['exito'],
        'codigo': resultado['codigo'],
        'mensaje': resultado['mensaje'],
        'participante': f"{inscripcion.participante.nombres} {inscripcion.participante.apellidos}",
        'permanencia': resultado.get('permanencia', {}).get('texto', '') if resultado.get('permanencia') else '',
        'hora_salida': resultado['asistencia'].hora_salida.strftime('%H:%M:%S') if resultado.get('asistencia') and resultado['asistencia'].hora_salida else ''
    }, status=status_code)


def escanear_salida(request, id_evento):
    """
    Vista responsiva para que el participante active su cámara y escanee
    el código QR colectivo proyectado por el profesor.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    inscripcion = None
    if request.user.is_authenticated:
        inscripcion = Inscripcion.objects.filter(
            evento=evento,
            participante__usuario=request.user,
            estado=EstadoInscripcion.ACTIVA
        ).select_related('participante', 'asistencia').first()
    elif request.session.get('acceso_externo_id'):
        filtros_acceso = {
            'pk': request.session['acceso_externo_id'],
            'revocado': False,
            'fecha_expiracion__gte': timezone.now(),
        }
        if request.session.get('acceso_externo_hash'):
            filtros_acceso['token_hash'] = request.session['acceso_externo_hash']
        acceso = AccesoExternoInscripcion.objects.filter(
            **filtros_acceso
        ).select_related('inscripcion', 'inscripcion__participante', 'inscripcion__asistencia').first()
        if acceso and acceso.es_valido and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
            inscripcion = acceso.inscripcion

    if not inscripcion and not request.user.is_authenticated:
        token_acceso = request.GET.get('token')
        if token_acceso:
            acceso = AccesoExternoInscripcion.validar_token(token_acceso)
            if acceso and acceso.inscripcion.evento_id == evento.pk and acceso.inscripcion.estado == EstadoInscripcion.ACTIVA:
                inscripcion = acceso.inscripcion
                request.session['acceso_externo_id'] = acceso.pk
                request.session['acceso_externo_hash'] = acceso.token_hash

    if not inscripcion:
        if not request.user.is_authenticated:
            messages.info(request, "Para registrar tu salida debes identificarte con tu cuenta o acceder mediante tu enlace personal.")
            return redirect(f"/usuarios/login/?next=/asistencia/evento/{id_evento}/escanear-salida/")
        raise PermissionDenied("No cuentas con una inscripción activa en este evento.")

    asistencia = getattr(inscripcion, 'asistencia', None)
    llegada_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_entrada)
    salida_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_salida)

    control = ControlSalidaEvento.objects.filter(evento=evento).first()
    salidas_habilitadas = bool(control and control.salidas_habilitadas and control.fecha_cierre is None)

    return render(request, 'asistencia/escanear_salida.html', {
        'evento': evento,
        'inscripcion': inscripcion,
        'participante': inscripcion.participante,
        'asistencia': asistencia,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
        'salidas_habilitadas': salidas_habilitadas,
    })

