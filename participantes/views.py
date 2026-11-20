import datetime
import hashlib
import base64
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import Http404, HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone

from auditoria.models import Auditoria
from eventos.models import Evento, EstadoEvento, ModalidadInscripcion, CalificacionEvento
from eventos.permissions import puede_gestionar_evento as puede_gestionar_evento_unificado, obtener_nrcs_evento
from eventos.services import es_estudiante_elegible_rol
from asistencia.models import Asistencia, EstadoAsistencia
from asistencia.services import generar_token_qr, generar_imagen_qr_bytes, es_salida_habilitada
from .models import (
    Participante,
    Inscripcion,
    EstadoInscripcion,
    TipoParticipante,
    InvitacionEvento,
    EstadoInvitacion,
    AccesoExternoInscripcion,
)
from .forms import (
    InscripcionExternaForm,
    InscripcionPublicaForm,
    ConsultaInscripcionPublicaForm,
    InvitacionEventoForm,
)
from .services import (
    AccesoExternoRevocadoError,
    enviar_correo_invitacion,
    enviar_correo_confirmacion_externa,
    generar_qr_inscripcion_publica,
    obtener_ip_rate_limit,
    esta_bloqueada_consulta_inscripcion,
    registrar_intento_fallido_consulta,
    construir_registro_auditoria_recuperacion,
    limpiar_intentos_consulta,
    buscar_inscripcion_publica_verificada,
    obtener_o_restaurar_acceso_externo,
    establecer_sesion_acceso_externo,
    limpiar_sesion_acceso_externo,
    tiene_sesion_externa_activa_evento,
)


def get_client_ip(request):
    """Obtiene la IP del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def obtener_o_crear_perfil_participante(user):
    """Garantiza la existencia del perfil Participante para un usuario institucional."""
    participante = getattr(user, 'perfil_participante', None)
    if not participante:
        tipo = TipoParticipante.ESTUDIANTE
        if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Docente', 'Coordinador', 'Administrador']:
            tipo = TipoParticipante.DOCENTE if user.rol.nombre == 'Docente' else TipoParticipante.ADMINISTRATIVO

        participante, _ = Participante.objects.get_or_create(
            usuario=user,
            defaults={
                'tipo': tipo,
                'documento': user.documento,
                'nombres': user.nombres,
                'apellidos': user.apellidos,
                'correo': user.email,
                'telefono': user.telefono or '',
                'institucion': 'Corporación Universitaria Minuto de Dios - UNIMINUTO',
            }
        )
    return participante


def inscribirse_evento(request, id_evento):
    """
    Flujo de inscripción unificado:
    - Usuarios autenticados: confirmación directa de inscripción institucional.
    - Usuarios anónimos: formulario de registro para participantes externos.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    # 1. Validar estado del evento
    if evento.estado != EstadoEvento.PUBLICADO:
        messages.error(request, f"El evento '{evento.nombre}' se encuentra en estado '{evento.get_estado_display()}'. No admite inscripciones.")
        return redirect('eventos:detalle', id_evento=evento.pk)

    # 2. Validar cupo disponible
    total_activos = evento.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
    if evento.cupo is not None and total_activos >= evento.cupo:
        messages.error(request, f"Lo sentimos, el cupo de {evento.cupo} asistentes para este evento ya se encuentra agotado.")
        return redirect('eventos:detalle', id_evento=evento.pk)

    # CASO A: Usuario Autenticado (Institucional)
    if request.user.is_authenticated:
        participante = obtener_o_crear_perfil_participante(request.user)
        nrc_raw = (request.POST.get('nrc') or '').strip()
        nrcs_validos = obtener_nrcs_evento(evento)
        nrc_validado = None
        if nrc_raw:
            if nrcs_validos:
                if nrc_raw not in nrcs_validos:
                    messages.error(request, f"El NRC '{nrc_raw}' no corresponde a los cursos asociados a este evento.")
                    return redirect('eventos:detalle', id_evento=evento.pk)
                nrc_validado = nrc_raw
            else:
                nrc_validado = nrc_raw[:20]

        with transaction.atomic():
            inscripcion = Inscripcion.objects.filter(evento=evento, participante=participante).first()

            if inscripcion:
                if inscripcion.estado == EstadoInscripcion.ACTIVA:
                    messages.info(request, "Ya cuentas con una inscripción activa en este evento.")
                    return redirect('eventos:detalle', id_evento=evento.pk)
                else:
                    # Reactivar inscripción previamente cancelada
                    inscripcion.estado = EstadoInscripcion.ACTIVA
                    if nrc_validado:
                        inscripcion.nrc = nrc_validado
                    inscripcion.save()

                    Auditoria.objects.create(
                        usuario=request.user,
                        accion='REACTIVAR_INSCRIPCION',
                        modulo='PARTICIPANTES',
                        registro_afectado=f"Inscripción ID {inscripcion.pk} - Evento {evento.pk}",
                        ip=get_client_ip(request)
                    )
                    messages.success(request, f"¡Tu inscripción al evento '{evento.nombre}' ha sido reactivada exitosamente!")
                    return redirect('participantes:mis_inscripciones')
            else:
                nueva_inscripcion = Inscripcion.objects.create(
                    evento=evento,
                    participante=participante,
                    estado=EstadoInscripcion.ACTIVA,
                    nrc=nrc_validado
                )
                Auditoria.objects.create(
                    usuario=request.user,
                    accion='INSCRIBIR_PARTICIPANTE',
                    modulo='PARTICIPANTES',
                    registro_afectado=f"Inscripción ID {nueva_inscripcion.pk} - Evento {evento.pk}",
                    ip=get_client_ip(request)
                )
                messages.success(request, f"¡Felicitaciones! Te has inscrito correctamente en '{evento.nombre}'.")
                return redirect('participantes:mis_inscripciones')

    # CASO B: Usuario No Autenticado (Participante Externo)
    if evento.modalidad_inscripcion not in [ModalidadInscripcion.ABIERTA, ModalidadInscripcion.MIXTA]:
        messages.error(
            request,
            f"El evento '{evento.nombre}' está configurado como 'Solo por invitación' y no admite registros públicos."
        )
        return render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'SOLO_INVITACION',
            'evento': evento,
            'mensaje': f"El evento '{evento.nombre}' es de modalidad 'Solo por invitación'. No admite inscripciones públicas."
        }, status=403)

    if request.method == 'POST':
        form = InscripcionExternaForm(request.POST)
        if form.is_valid():
            doc = form.cleaned_data['documento'].strip()
            correo = form.cleaned_data['correo'].strip().lower()

            with transaction.atomic():
                # Reutilizar participante externo existente o crear uno nuevo
                participante_ext = Participante.objects.filter(documento=doc, usuario__isnull=True).first()
                if not participante_ext:
                    participante_ext = Participante.objects.filter(correo__iexact=correo, usuario__isnull=True).first()

                if not participante_ext:
                    participante_ext = form.save(commit=False)
                    participante_ext.tipo = TipoParticipante.EXTERNO
                    participante_ext.usuario = None
                    participante_ext.save()
                else:
                    participante_ext.documento = doc
                    participante_ext.nombres = form.cleaned_data['nombres']
                    participante_ext.apellidos = form.cleaned_data['apellidos']
                    participante_ext.correo = correo
                    participante_ext.telefono = form.cleaned_data['telefono']
                    participante_ext.institucion = form.cleaned_data['institucion']
                    participante_ext.save()

                # Verificar si ya está inscrito
                inscripcion_ext = Inscripcion.objects.filter(evento=evento, participante=participante_ext).first()
                if inscripcion_ext:
                    if inscripcion_ext.estado == EstadoInscripcion.ACTIVA:
                        # Asegurar existencia de acceso externo y enviar correo
                        acceso_ext = getattr(inscripcion_ext, 'acceso_externo', None)
                        if acceso_ext:
                            raw_token, nuevo_hash = AccesoExternoInscripcion.generar_token()
                            acceso_ext.token_hash = nuevo_hash
                            acceso_ext.fecha_expiracion = timezone.now() + datetime.timedelta(days=30)
                            acceso_ext.revocado = False
                            acceso_ext.fecha_revocacion = None
                            acceso_ext.save()
                        else:
                            acceso_ext, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(inscripcion_ext)
                        enviar_correo_confirmacion_externa(inscripcion_ext, acceso_ext, raw_token, request)

                        token_qr = generar_token_qr(inscripcion_ext)
                        messages.info(request, f"El participante con documento {doc} ya cuenta con una inscripción activa en este evento. Aquí está tu pase digital.")
                        url_pase = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': inscripcion_ext.pk}) + f"?token={token_qr}"
                        return redirect(url_pase)
                    else:
                        inscripcion_ext.estado = EstadoInscripcion.ACTIVA
                        inscripcion_ext.save()
                        Auditoria.objects.create(
                            usuario=None,
                            accion='REACTIVAR_INSCRIPCION_EXTERNO',
                            modulo='PARTICIPANTES',
                            registro_afectado=f"Inscripción ID {inscripcion_ext.pk} - Doc {doc} - Evento {evento.pk}",
                            ip=get_client_ip(request)
                        )
                        acceso_ext = getattr(inscripcion_ext, 'acceso_externo', None)
                        if acceso_ext:
                            raw_token, nuevo_hash = AccesoExternoInscripcion.generar_token()
                            acceso_ext.token_hash = nuevo_hash
                            acceso_ext.fecha_expiracion = timezone.now() + datetime.timedelta(days=30)
                            acceso_ext.revocado = False
                            acceso_ext.fecha_revocacion = None
                            acceso_ext.save()
                        else:
                            acceso_ext, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(inscripcion_ext)
                        enviar_correo_confirmacion_externa(inscripcion_ext, acceso_ext, raw_token, request)

                        token_qr = generar_token_qr(inscripcion_ext)
                        messages.success(request, f"¡Inscripción reactivada con éxito para {participante_ext.nombres} {participante_ext.apellidos}!")
                        url_pase = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': inscripcion_ext.pk}) + f"?token={token_qr}"
                        return redirect(url_pase)
                else:
                    nueva_insc = Inscripcion.objects.create(
                        evento=evento,
                        participante=participante_ext,
                        estado=EstadoInscripcion.ACTIVA
                    )
                    Auditoria.objects.create(
                        usuario=None,
                        accion='INSCRIBIR_EXTERNO',
                        modulo='PARTICIPANTES',
                        registro_afectado=f"Inscripción ID {nueva_insc.pk} - Doc {doc} - Evento {evento.pk}",
                        ip=get_client_ip(request)
                    )
                    acceso_ext, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(nueva_insc)
                    enviar_correo_confirmacion_externa(nueva_insc, acceso_ext, raw_token, request)

                    token_qr = generar_token_qr(nueva_insc)
                    messages.success(request, f"¡Inscripción exitosa! {participante_ext.nombres} {participante_ext.apellidos} ha quedado registrado(a) en '{evento.nombre}'.")
                    url_pase = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': nueva_insc.pk}) + f"?token={token_qr}"
                    return redirect(url_pase)
        else:
            messages.error(request, "Por favor revisa los datos ingresados en el formulario.")
    else:
        form = InscripcionExternaForm()

    return render(request, 'participantes/inscribirse_externo.html', {
        'evento': evento,
        'form': form,
    })


@login_required
def mis_inscripciones(request):
    """
    Panel de consulta de inscripciones e historial de calificaciones del usuario autenticado (RF-29).
    Identifica de manera confiable los eventos con entrada y salida confirmadas pendientes de calificación
    y muestra las puntuaciones ya registradas con opción de actualización propia.
    """
    participante = getattr(request.user, 'perfil_participante', None)
    es_estudiante = es_estudiante_elegible_rol(request.user)
    if participante:
        inscripciones = list(
            participante.inscripciones
            .select_related('evento', 'evento__categoria', 'asistencia')
            .order_by('-fecha_inscripcion')
        )
    else:
        inscripciones = []

    calificaciones_map = {}
    if es_estudiante and inscripciones:
        evento_ids = [ins.evento_id for ins in inscripciones]
        calificaciones_map = {
            c.evento_id: c
            for c in CalificacionEvento.objects.filter(
                estudiante=request.user,
                evento_id__in=evento_ids,
            )
        }

    evaluaciones_pendientes = []
    for ins in inscripciones:
        asist = getattr(ins, 'asistencia', None)
        ins.entrada_confirmada = bool(
            asist and asist.estado == EstadoAsistencia.REGISTRADA and asist.hora_entrada
        )
        ins.salida_confirmada = bool(
            asist and asist.estado == EstadoAsistencia.REGISTRADA and asist.hora_entrada and asist.hora_salida
        )
        ins.calificacion_usuario = calificaciones_map.get(ins.evento_id)
        ins.calificacion_pendiente = bool(
            es_estudiante
            and ins.estado == EstadoInscripcion.ACTIVA
            and ins.salida_confirmada
            and ins.calificacion_usuario is None
        )
        if ins.calificacion_pendiente:
            evaluaciones_pendientes.append(ins)

    return render(request, 'participantes/mis_inscripciones.html', {
        'inscripciones': inscripciones,
        'total_inscripciones': len(inscripciones),
        'evaluaciones_pendientes': evaluaciones_pendientes,
        'total_evaluaciones_pendientes': len(evaluaciones_pendientes),
        'es_estudiante': es_estudiante,
    })


@login_required
def cancelar_inscripcion(request, id_inscripcion):
    """
    Permite al usuario cancelar su propia inscripción si el evento aún no concluye ni se registró asistencia.
    """
    if request.method != 'POST':
        messages.warning(request, "La cancelación de inscripción debe solicitarse mediante el formulario correspondiente.")
        return redirect('participantes:mis_inscripciones')

    inscripcion = get_object_or_404(
        Inscripcion.objects.select_related('participante', 'evento'),
        pk=id_inscripcion
    )

    # Control de seguridad: solo el dueño de la inscripción o staff
    es_propietario = (inscripcion.participante.usuario_id == request.user.id)
    es_admin = request.user.is_superuser or request.user.is_staff

    if not (es_propietario or es_admin):
        raise PermissionDenied("No tienes autorización para cancelar esta inscripción.")

    # Reglas de negocio
    if inscripcion.asistio:
        messages.error(request, "No es posible cancelar una inscripción que ya cuenta con asistencia registrada.")
        return redirect('participantes:mis_inscripciones')

    if inscripcion.evento.estado in [EstadoEvento.FINALIZADO, EstadoEvento.CERRADO]:
        messages.error(request, "No es posible cancelar la inscripción de un evento que ya ha finalizado o cerrado.")
        return redirect('participantes:mis_inscripciones')

    if inscripcion.estado == EstadoInscripcion.CANCELADA:
        messages.info(request, "Esta inscripción ya se encuentra en estado CANCELADA.")
        return redirect('participantes:mis_inscripciones')

    # Ejecutar cancelación
    inscripcion.estado = EstadoInscripcion.CANCELADA
    inscripcion.save()

    Auditoria.objects.create(
        usuario=request.user,
        accion='CANCELAR_INSCRIPCION',
        modulo='PARTICIPANTES',
        registro_afectado=f"Inscripción ID {inscripcion.pk} - Evento {inscripcion.evento_id}",
        ip=get_client_ip(request)
    )

    messages.success(request, f"Tu inscripción al evento '{inscripcion.evento.nombre}' ha sido cancelada.")
    return redirect('participantes:mis_inscripciones')


def puede_gestionar_evento(user, evento):
    """Comprueba si un usuario cuenta con facultades de administración, organización o docencia asociada sobre el evento."""
    return puede_gestionar_evento_unificado(user, evento)


@login_required
def gestionar_invitaciones(request, id_evento):
    """
    Panel institucional para que profesores y organizadores gestionen invitaciones (RF-01).
    Permite emitir, listar, reenviar y cancelar invitaciones a eventos.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    if not puede_gestionar_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para gestionar las invitaciones de este evento.")

    admite_invitaciones = (evento.modalidad_inscripcion in [
        ModalidadInscripcion.SOLO_INVITACION,
        ModalidadInscripcion.MIXTA,
    ])

    if request.method == 'POST':
        if not admite_invitaciones:
            messages.error(
                request,
                "Este evento está configurado con modalidad de inscripción ABIERTA y no admite el envío de invitaciones individuales."
            )
            return redirect('participantes:gestionar_invitaciones', id_evento=evento.pk)

        form = InvitacionEventoForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data['correo']
            nombres = form.cleaned_data['nombres']
            apellidos = form.cleaned_data['apellidos']
            institucion = form.cleaned_data.get('institucion', '')

            # Validar si ya tiene inscripción activa en este evento
            ya_inscrito = Inscripcion.objects.filter(
                evento=evento,
                estado=EstadoInscripcion.ACTIVA
            ).filter(
                Q(participante__correo__iexact=correo) |
                Q(participante__usuario__email__iexact=correo)
            ).exists()

            if ya_inscrito:
                messages.warning(
                    request,
                    f"La persona con el correo '{correo}' ya cuenta con una inscripción activa en este evento."
                )
                return redirect('participantes:gestionar_invitaciones', id_evento=evento.pk)

            # Verificar si ya existía invitación previa pendiente para auditar correctamente
            inv_previa = InvitacionEvento.objects.filter(
                evento=evento,
                correo=correo,
                estado=EstadoInvitacion.PENDIENTE
            ).first()

            invitacion, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
                evento=evento,
                correo=correo,
                nombres=nombres,
                apellidos=apellidos,
                invitado_por=request.user,
                institucion=institucion,
                dias_vigencia=3
            )

            accion_audit = 'RENOVAR_INVITACION' if inv_previa else 'CREAR_INVITACION'
            Auditoria.objects.create(
                usuario=request.user,
                accion=accion_audit,
                modulo='PARTICIPANTES',
                registro_afectado=f"Invitación ID {invitacion.pk} - Evento {evento.pk} ({correo})",
                ip=get_client_ip(request)
            )

            enviado = enviar_correo_invitacion(invitacion, raw_token, request)
            if enviado:
                if inv_previa:
                    messages.success(request, f"Se ha renovado exitosamente la invitación pendiente para '{correo}' y se ha reenviado el correo.")
                else:
                    messages.success(request, f"Invitación enviada exitosamente a '{correo}'.")
            else:
                messages.warning(
                    request,
                    f"La invitación para '{correo}' fue registrada en el sistema, pero el servicio de correo electrónico no pudo entregar el mensaje. Por favor revise la configuración de correo."
                )

            return redirect('participantes:gestionar_invitaciones', id_evento=evento.pk)
        else:
            messages.error(request, "Por favor corrija los datos ingresados en el formulario de invitación.")
    else:
        form = InvitacionEventoForm()

    invitaciones = evento.invitaciones.select_related('invitado_por').order_by('-fecha_creacion')

    return render(request, 'participantes/gestionar_invitaciones.html', {
        'evento': evento,
        'form': form,
        'invitaciones': invitaciones,
        'total_invitaciones': invitaciones.count(),
        'admite_invitaciones': admite_invitaciones,
    })


@login_required
def reenviar_invitacion(request, id_evento, id_invitacion):
    """
    Renueva el token e invalida el anterior, reenviando el correo al invitado.
    """
    if request.method != 'POST':
        messages.warning(request, "La acción de reenvío debe solicitarse mediante el formulario correspondiente.")
        return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not puede_gestionar_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para reenviar invitaciones de este evento.")

    with transaction.atomic():
        invitacion = get_object_or_404(
            InvitacionEvento.objects.select_for_update(),
            pk=id_invitacion,
            evento_id=id_evento
        )

        if invitacion.estado == EstadoInvitacion.ACEPTADA:
            messages.info(request, "Esta invitación ya fue aceptada y no requiere reenvío.")
            return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)

        raw_token = invitacion.renovar_token(dias_vigencia=3)

        Auditoria.objects.create(
            usuario=request.user,
            accion='REENVIAR_INVITACION',
            modulo='PARTICIPANTES',
            registro_afectado=f"Invitación ID {invitacion.pk} - Evento {id_evento} ({invitacion.correo})",
            ip=get_client_ip(request)
        )

    enviado = enviar_correo_invitacion(invitacion, raw_token, request)
    if enviado:
        messages.success(request, f"La invitación para '{invitacion.correo}' fue renovada y reenviada exitosamente.")
    else:
        messages.warning(request, f"La invitación para '{invitacion.correo}' fue renovada, pero el servidor de correo no pudo entregar el mensaje.")

    return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)


@login_required
def cancelar_invitacion(request, id_evento, id_invitacion):
    """
    Cancela una invitación pendiente, invalidando su uso inmediato.
    """
    if request.method != 'POST':
        messages.warning(request, "La cancelación de invitación debe solicitarse mediante el formulario respectivo.")
        return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not puede_gestionar_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para cancelar invitaciones de este evento.")

    with transaction.atomic():
        invitacion = get_object_or_404(
            InvitacionEvento.objects.select_for_update(),
            pk=id_invitacion,
            evento_id=id_evento
        )

        if invitacion.estado != EstadoInvitacion.PENDIENTE:
            messages.error(request, f"No se puede cancelar una invitación en estado '{invitacion.get_estado_display()}'.")
            return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)

        invitacion.cancelar_invitacion(responsable=request.user)

        Auditoria.objects.create(
            usuario=request.user,
            accion='CANCELAR_INVITACION',
            modulo='PARTICIPANTES',
            registro_afectado=f"Invitación ID {invitacion.pk} - Evento {id_evento} ({invitacion.correo})",
            ip=get_client_ip(request)
        )

    # Si la sesión actual apuntaba a esta invitación, invalidarla inmediatamente
    if request.session.get('invitacion_id') == id_invitacion:
        limpiar_contexto_invitacion_sesion(request)

    messages.success(request, f"La invitación para '{invitacion.correo}' ha sido cancelada exitosamente.")
    return redirect('participantes:gestionar_invitaciones', id_evento=id_evento)


def limpiar_contexto_invitacion_sesion(request):
    """Invalida y elimina el contexto de invitación almacenado en la sesión del usuario."""
    for k in ['invitacion_id', 'invitacion_token_hash', 'invitacion_evento_id', 'invitacion_correo', 'invitacion_token']:
        request.session.pop(k, None)


def consultar_invitacion(request, token):
    """
    Punto de entrada de invitación mediante token seguro.
    Valida el token contra su hash SHA-256, almacena el contexto en sesión
    y redirige inmediatamente a una URL limpia sin exponer el token.
    Configura cabecera Referrer-Policy: no-referrer.
    """
    if not token or len(token.strip()) < 10:
        response = render(request, 'participantes/invitacion_resultado.html', {'estado': 'INVALIDA'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    token_hash = hashlib.sha256(token.strip().encode('utf-8')).hexdigest()
    invitacion = InvitacionEvento.objects.filter(token_hash=token_hash).first()

    if not invitacion:
        response = render(request, 'participantes/invitacion_resultado.html', {'estado': 'INVALIDA'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    # Guardar contexto seguro en la sesión y redirigir a URL limpia
    request.session['invitacion_id'] = invitacion.pk
    request.session['invitacion_token_hash'] = token_hash
    request.session['invitacion_evento_id'] = invitacion.evento_id
    request.session['invitacion_correo'] = invitacion.correo

    response = redirect('participantes:ver_invitacion')
    response['Referrer-Policy'] = 'no-referrer'
    return response


def ver_invitacion(request):
    """
    Vista limpia (sin token en la URL) que presenta la invitación utilizando
    el contexto validado previamente en la sesión.
    Protege contra fugas de URL con Referrer-Policy: no-referrer.
    """
    inv_id = request.session.get('invitacion_id')
    token_hash = request.session.get('invitacion_token_hash')

    if not inv_id or not token_hash:
        response = render(request, 'participantes/invitacion_resultado.html', {'estado': 'INVALIDA'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    invitacion = (
        InvitacionEvento.objects
        .select_related('evento', 'evento__categoria', 'evento__organizador', 'invitado_por')
        .filter(pk=inv_id, token_hash=token_hash)
        .first()
    )

    if not invitacion:
        limpiar_contexto_invitacion_sesion(request)
        response = render(request, 'participantes/invitacion_resultado.html', {'estado': 'INVALIDA'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    # Manejo de estados terminales o cancelados
    if invitacion.estado == EstadoInvitacion.CANCELADA:
        limpiar_contexto_invitacion_sesion(request)
        response = render(request, 'participantes/invitacion_resultado.html', {
            'estado': 'CANCELADA',
            'evento': invitacion.evento,
            'invitacion': invitacion,
        })
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if invitacion.ha_expirado or invitacion.estado == EstadoInvitacion.EXPIRADA:
        limpiar_contexto_invitacion_sesion(request)
        response = render(request, 'participantes/invitacion_resultado.html', {
            'estado': 'EXPIRADA',
            'evento': invitacion.evento,
            'invitacion': invitacion,
        })
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if invitacion.estado == EstadoInvitacion.ACEPTADA:
        limpiar_contexto_invitacion_sesion(request)
        response = render(request, 'participantes/invitacion_resultado.html', {
            'estado': 'ACEPTADA',
            'evento': invitacion.evento,
            'invitacion': invitacion,
        })
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if invitacion.estado == EstadoInvitacion.RECHAZADA:
        limpiar_contexto_invitacion_sesion(request)
        response = render(request, 'participantes/invitacion_resultado.html', {
            'estado': 'RECHAZADA',
            'evento': invitacion.evento,
            'invitacion': invitacion,
        })
        response['Referrer-Policy'] = 'no-referrer'
        return response

    coincide_correo = False
    correo_verificado = False
    if request.user.is_authenticated:
        coincide_correo = (request.user.email.strip().lower() == invitacion.correo.strip().lower())
        correo_verificado = getattr(request.user, 'email_verificado', False)

    response = render(request, 'participantes/invitacion_detalle.html', {
        'invitacion': invitacion,
        'evento': invitacion.evento,
        'organizador': invitacion.invitado_por,
        'coincide_correo': coincide_correo,
        'correo_verificado': correo_verificado,
    })
    response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
def responder_invitacion(request):
    """
    Acción transaccional y atómica para que el invitado autenticado acepte o rechace la invitación.
    Opera sobre la URL limpia utilizando el contexto de sesión verificado.
    Exige correo coincidente y verificado para la aceptación.
    """
    if request.method != 'POST':
        messages.warning(request, "La respuesta a la invitación debe realizarse mediante los botones del formulario.")
        return redirect('participantes:ver_invitacion')

    inv_id = request.session.get('invitacion_id')
    token_hash = request.session.get('invitacion_token_hash')

    if not inv_id or not token_hash:
        messages.error(request, "No se encontró una invitación activa en la sesión.")
        return redirect('inicio')

    accion = request.POST.get('accion')

    with transaction.atomic():
        invitacion = (
            InvitacionEvento.objects
            .select_for_update()
            .select_related('evento')
            .filter(pk=inv_id, token_hash=token_hash)
            .first()
        )

        if not invitacion:
            limpiar_contexto_invitacion_sesion(request)
            raise Http404("Invitación no encontrada.")

        # 1. Validación estricta de correo de la cuenta autenticada
        if request.user.email.strip().lower() != invitacion.correo.strip().lower():
            raise PermissionDenied("El correo de la cuenta autenticada no coincide con el destinatario de la invitación.")

        # 2. Validación de estado de la invitación
        if not invitacion.puede_ser_aceptada:
            limpiar_contexto_invitacion_sesion(request)
            if invitacion.estado == EstadoInvitacion.CANCELADA:
                messages.error(request, "Esta invitación ha sido cancelada por el organizador.")
            elif invitacion.ha_expirado:
                messages.error(request, "La invitación ha expirado y ya no puede ser procesada.")
            elif invitacion.estado == EstadoInvitacion.ACEPTADA:
                messages.info(request, "Esta invitación ya fue aceptada previamente.")
            elif invitacion.estado == EstadoInvitacion.RECHAZADA:
                messages.info(request, "Esta invitación ya fue rechazada previamente.")
            return redirect('participantes:ver_invitacion')

        # 3. Procesar aceptación
        if accion == 'aceptar':
            # Verificación obligatoria de posesión de correo (RF-01 / Etapa 7.2.1.1)
            if not getattr(request.user, 'email_verificado', False):
                messages.warning(
                    request,
                    "Debes verificar tu dirección de correo electrónico antes de poder aceptar la invitación. "
                    "Por favor revisa el correo de verificación enviado o solicita uno nuevo."
                )
                return redirect('participantes:ver_invitacion')

            participante = obtener_o_crear_perfil_participante(request.user)

            # Verificar si ya existe inscripción (bloqueo pesimista para evitar duplicidad)
            inscripcion = Inscripcion.objects.select_for_update().filter(
                evento=invitacion.evento,
                participante=participante
            ).first()

            if inscripcion:
                if inscripcion.estado == EstadoInscripcion.ACTIVA:
                    invitacion.marcar_como_aceptada()
                    messages.info(request, f"Ya cuentas con una inscripción activa en '{invitacion.evento.nombre}'.")
                else:
                    inscripcion.estado = EstadoInscripcion.ACTIVA
                    inscripcion.save(update_fields=['estado'])
                    invitacion.marcar_como_aceptada()
                    Auditoria.objects.create(
                        usuario=request.user,
                        accion='ACEPTAR_INVITACION',
                        modulo='PARTICIPANTES',
                        registro_afectado=f"Invitación ID {invitacion.pk} - Reactivación Inscripción ID {inscripcion.pk} - Evento {invitacion.evento_id}",
                        ip=get_client_ip(request)
                    )
                    messages.success(request, f"¡Has aceptado la invitación! Tu inscripción al evento '{invitacion.evento.nombre}' ha sido reactivada.")
            else:
                nueva_inscripcion = Inscripcion.objects.create(
                    evento=invitacion.evento,
                    participante=participante,
                    estado=EstadoInscripcion.ACTIVA
                )
                invitacion.marcar_como_aceptada()
                Auditoria.objects.create(
                    usuario=request.user,
                    accion='ACEPTAR_INVITACION',
                    modulo='PARTICIPANTES',
                    registro_afectado=f"Invitación ID {invitacion.pk} - Nueva Inscripción ID {nueva_inscripcion.pk} - Evento {invitacion.evento_id}",
                    ip=get_client_ip(request)
                )
                messages.success(request, f"¡Has aceptado la invitación! Te has inscrito exitosamente en '{invitacion.evento.nombre}'.")

            limpiar_contexto_invitacion_sesion(request)
            return redirect('participantes:mis_inscripciones')

        # 4. Procesar rechazo
        elif accion == 'rechazar':
            invitacion.marcar_como_rechazada()
            Auditoria.objects.create(
                usuario=request.user,
                accion='RECHAZAR_INVITACION',
                modulo='PARTICIPANTES',
                registro_afectado=f"Invitación ID {invitacion.pk} - Evento {invitacion.evento_id}",
                ip=get_client_ip(request)
            )
            limpiar_contexto_invitacion_sesion(request)
            messages.info(request, f"Has rechazado la invitación al evento '{invitacion.evento.nombre}'.")
            return redirect('eventos:catalogo')

        else:
            messages.error(request, "Acción de respuesta no reconocida.")
            return redirect('participantes:ver_invitacion')


# ==============================================================================
# FLUJO DE INSCRIPCIÓN PÚBLICA Y PARTICIPANTES EXTERNOS (ETAPA 7.2.2)
# ==============================================================================

def _construir_contexto_comprobante_externo(inscripcion):
    """Construye en memoria los datos de asistencia y el QR personal dinámico sin alterar registros."""
    asistencia = Asistencia.objects.filter(inscripcion=inscripcion).first()
    llegada_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_entrada)
    salida_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_salida)
    salidas_habilitadas = es_salida_habilitada(inscripcion.evento)
    token_qr = generar_token_qr(inscripcion)
    qr_bytes = generar_imagen_qr_bytes(token_qr)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')
    return {
        'asistencia': asistencia,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
        'salidas_habilitadas': salidas_habilitadas,
        'token_qr': token_qr,
        'qr_base64': qr_base64,
    }


def inscripcion_publica_view(request, id_evento):
    """
    Formulario y procesamiento de registro público para participantes externos (Etapa 7.2.2).
    Permite inscribirse a eventos con modalidad ABIERTA o MIXTA sin crear cuenta institucional,
    así como acceder a la pestaña de consulta/recuperación de inscripciones existentes.
    Valida rigurosamente en servidor:
    1. Modalidad del evento (ABIERTA o MIXTA obligatoria; rechaza SOLO_INVITACION con 403).
    2. Estado del evento (PUBLICADO obligatorio para nuevas inscripciones).
    3. Cupo disponible si tiene límite establecido.
    4. Normalización de correo y deduplicación de participantes externos.
    5. No duplicidad de inscripciones en el mismo evento ni invalidación de QR existentes.
    6. Creación atómica de AccesoExternoInscripcion y envío de correo de confirmación.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    # 1. Validar modalidad de inscripción
    if evento.modalidad_inscripcion not in [ModalidadInscripcion.ABIERTA, ModalidadInscripcion.MIXTA]:
        return render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'SOLO_INVITACION',
            'evento': evento,
            'mensaje': f"El evento '{evento.nombre}' está configurado como 'Solo por invitación' y no admite registros públicos."
        }, status=403)

    # 2. Validar estado del evento
    if evento.estado != EstadoEvento.PUBLICADO:
        return render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'NO_DISPONIBLE',
            'evento': evento,
            'mensaje': f"El evento '{evento.nombre}' se encuentra en estado '{evento.get_estado_display()}'. No admite inscripciones."
        }, status=400)

    # 3. Calcular cupos disponibles (sin bloquear aún para permitir recuperación de ya inscritos)
    total_activos = evento.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
    cupos_disponibles = max(0, evento.cupo - total_activos) if evento.cupo is not None else None
    esta_lleno = (cupos_disponibles == 0) if cupos_disponibles is not None else False
    sesion_activa_evento = tiene_sesion_externa_activa_evento(request, evento)
    consulta_form = ConsultaInscripcionPublicaForm()
    modo_activo = 'consultar' if request.GET.get('modo') == 'consultar' else 'inscribir'

    if request.method == 'POST':
        ip_rl = obtener_ip_rate_limit(request)
        doc_raw = request.POST.get('documento', '')
        bloqueada_reg, _ = esta_bloqueada_consulta_inscripcion(evento.pk, ip_rl, documento=doc_raw)
        if bloqueada_reg:
            limpiar_sesion_acceso_externo(request)
            Auditoria.objects.create(
                usuario=None,
                accion='CONSULTA_INSCRIPCION_BLOQUEADA_RATE_LIMIT',
                modulo='PARTICIPANTES',
                registro_afectado=f"Límite de intentos excedido en registro - Evento {evento.pk}"[:100],
                ip=ip_rl,
            )
            response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                'estado': 'RATE_LIMIT',
                'evento': evento,
                'mensaje': (
                    "Has realizado demasiados intentos fallidos en pocos minutos. "
                    "Por seguridad, espera unos minutos antes de intentarlo nuevamente."
                ),
            }, status=429)
            response['Referrer-Policy'] = 'no-referrer'
            return response

        form = InscripcionPublicaForm(request.POST)
        if form.is_valid():
            doc = form.cleaned_data['documento']
            correo = form.cleaned_data['correo']
            nombres = form.cleaned_data['nombres']
            apellidos = form.cleaned_data['apellidos']
            telefono = form.cleaned_data.get('telefono', '')
            institucion = form.cleaned_data.get('institucion', '')

            with transaction.atomic():
                evento_lock = Evento.objects.select_for_update().get(pk=evento.pk)

                # Buscar participante externo existente por documento o por correo
                part_por_doc = Participante.objects.select_for_update().filter(
                    documento=doc,
                    usuario__isnull=True
                ).first()
                part_por_correo = Participante.objects.select_for_update().filter(
                    correo__iexact=correo,
                    usuario__isnull=True
                ).first()

                # Verificar si ya existe alguna inscripción ACTIVA asociada al documento o al correo en este evento
                candidatas_activas = list(
                    Inscripcion.objects.select_for_update().select_related('participante').filter(
                        evento=evento_lock,
                        estado=EstadoInscripcion.ACTIVA
                    ).filter(
                        Q(participante__documento=doc) | Q(participante__correo__iexact=correo)
                    )
                )

                insc_activa = None
                for cand in candidatas_activas:
                    p_cand = cand.participante
                    if p_cand.documento.strip() == doc and p_cand.correo.strip().lower() == correo.lower():
                        insc_activa = cand
                        break
                if insc_activa is None and candidatas_activas:
                    insc_activa = candidatas_activas[0]

                if insc_activa:
                    part_inscrito = insc_activa.participante
                    # Seguridad anti-IDOR / anti-enumeración: exigir coincidencia exacta de documento Y correo registrado
                    coincide_doc = (part_inscrito.documento.strip() == doc)
                    coincide_correo = (part_inscrito.correo.strip().lower() == correo.lower())

                    if not (coincide_doc and coincide_correo):
                        # Limpiar cualquier sesión externa previa y registrar intento fallido con HMAC (sin PII en claro)
                        limpiar_sesion_acceso_externo(request)
                        registrar_intento_fallido_consulta(evento_lock.pk, ip_rl, documento=doc)

                        activos_actuales = evento_lock.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
                        if evento_lock.cupo is not None and activos_actuales >= evento_lock.cupo:
                            return render(request, 'participantes/inscripcion_publica_resultado.html', {
                                'estado': 'CUPO_AGOTADO',
                                'evento': evento_lock,
                                'mensaje': f"Lo sentimos, el cupo de {evento_lock.cupo} participantes para este evento ya se encuentra agotado."
                            }, status=400)

                        return render(request, 'participantes/inscripcion_publica_resultado.html', {
                            'estado': 'DATOS_NO_COINCIDEN',
                            'evento': evento_lock,
                            'mensaje': (
                                "No fue posible validar los datos ingresados para completar o recuperar la inscripción "
                                "en este evento. Verifica tu número de documento y correo electrónico, o utiliza la "
                                "opción de consulta de inscripción."
                            )
                        }, status=403)

                    # Si la inscripción corresponde a una cuenta institucional, redirigir a inicio de sesión sin error 500
                    if part_inscrito.usuario_id is not None:
                        limpiar_sesion_acceso_externo(request)
                        return render(request, 'participantes/inscripcion_publica_resultado.html', {
                            'estado': 'CUENTA_INSTITUCIONAL',
                            'evento': evento_lock,
                            'mensaje': (
                                "Ya cuentas con una inscripción activa asociada a tu cuenta institucional UNIMINUTO. "
                                "Inicia sesión para consultar tu pase digital y código QR."
                            ),
                        })

                    # Coincidencia verificada: conservar inscripción, asistencia y token vigente sin rehabilitar revocados
                    try:
                        acceso_ext, raw_token = obtener_o_restaurar_acceso_externo(insc_activa)
                    except AccesoExternoRevocadoError as exc:
                        limpiar_sesion_acceso_externo(request)
                        Auditoria.objects.create(
                            usuario=None,
                            accion='RECUPERACION_ACCESO_REVOCADO_BLOQUEADA',
                            modulo='PARTICIPANTES',
                            registro_afectado=f"Acceso revocado bloqueado - Inscripción {insc_activa.pk} - Evento {evento_lock.pk}"[:100],
                            ip=ip_rl,
                        )
                        response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                            'estado': 'ACCESO_REVOCADO',
                            'evento': evento_lock,
                            'mensaje': str(exc),
                        }, status=403)
                        response['Referrer-Policy'] = 'no-referrer'
                        return response
                    establecer_sesion_acceso_externo(request, acceso_ext, insc_activa)

                    enviado = False
                    if raw_token:
                        enviado = enviar_correo_confirmacion_externa(insc_activa, acceso_ext, raw_token, request)

                    ctx_comprobante = _construir_contexto_comprobante_externo(insc_activa)
                    response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                        'estado': 'YA_INSCRITO',
                        'evento': evento_lock,
                        'participante': part_inscrito,
                        'inscripcion': insc_activa,
                        'correo_enviado': enviado,
                        'token_reutilizado': (raw_token is None),
                        'acceso_disponible': (acceso_ext.inscripcion_id == insc_activa.pk),
                        'mensaje': f"Ya cuentas con una inscripción activa en '{evento_lock.nombre}'. Se conservó tu registro y código QR original.",
                        **ctx_comprobante,
                    })
                    response['Referrer-Policy'] = 'no-referrer'
                    return response

                # Si no tiene inscripción activa en este evento, validar cupo disponible antes de inscribir o reactivar
                activos_actuales = evento_lock.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
                if evento_lock.cupo is not None and activos_actuales >= evento_lock.cupo:
                    return render(request, 'participantes/inscripcion_publica_resultado.html', {
                        'estado': 'CUPO_AGOTADO',
                        'evento': evento_lock,
                        'mensaje': f"Lo sentimos, el cupo de {evento_lock.cupo} participantes para este evento ya se encuentra agotado."
                    }, status=400)

                # Reutilizar participante externo existente o crear uno nuevo sin cuenta institucional
                participante_ext = part_por_doc or part_por_correo
                if not participante_ext:
                    participante_ext = Participante.objects.create(
                        usuario=None,
                        tipo=TipoParticipante.EXTERNO,
                        documento=doc,
                        nombres=nombres,
                        apellidos=apellidos,
                        correo=correo,
                        telefono=telefono,
                        institucion=institucion,
                    )
                else:
                    participante_ext.documento = doc
                    participante_ext.nombres = nombres
                    participante_ext.apellidos = apellidos
                    participante_ext.correo = correo
                    participante_ext.telefono = telefono
                    participante_ext.institucion = institucion
                    participante_ext.save()

                # Verificar si existía inscripción previamente cancelada en este evento
                inscripcion_ext = Inscripcion.objects.select_for_update().filter(
                    evento=evento_lock,
                    participante=participante_ext
                ).first()

                if inscripcion_ext:
                    acceso_previo = AccesoExternoInscripcion.objects.select_for_update().filter(
                        inscripcion=inscripcion_ext
                    ).first()
                    if acceso_previo and acceso_previo.revocado:
                        limpiar_sesion_acceso_externo(request)
                        Auditoria.objects.create(
                            usuario=None,
                            accion='RECUPERACION_ACCESO_REVOCADO_BLOQUEADA',
                            modulo='PARTICIPANTES',
                            registro_afectado=f"Acceso revocado bloqueado - Inscripción {inscripcion_ext.pk} - Evento {evento_lock.pk}"[:100],
                            ip=ip_rl,
                        )
                        response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                            'estado': 'ACCESO_REVOCADO',
                            'evento': evento_lock,
                            'mensaje': (
                                "El acceso a esta inscripción no se encuentra disponible. "
                                "Por favor comunícate con el administrador o coordinador del evento para solicitar asistencia."
                            ),
                        }, status=403)
                        response['Referrer-Policy'] = 'no-referrer'
                        return response

                    inscripcion_ext.estado = EstadoInscripcion.ACTIVA
                    inscripcion_ext.save(update_fields=['estado'])
                    acceso_ext, raw_token = obtener_o_restaurar_acceso_externo(inscripcion_ext)
                    establecer_sesion_acceso_externo(request, acceso_ext, inscripcion_ext)

                    Auditoria.objects.create(
                        usuario=None,
                        accion='REACTIVAR_INSCRIPCION_EXTERNO',
                        modulo='PARTICIPANTES',
                        registro_afectado=f"Inscripción ID {inscripcion_ext.pk} reactivada - Doc {doc} - Evento {evento_lock.pk}"[:100],
                        ip=get_client_ip(request)
                    )
                    enviado = False
                    if raw_token:
                        enviado = enviar_correo_confirmacion_externa(inscripcion_ext, acceso_ext, raw_token, request)
                    ctx_comprobante = _construir_contexto_comprobante_externo(inscripcion_ext)
                    response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                        'estado': 'REACTIVADA',
                        'evento': evento_lock,
                        'participante': participante_ext,
                        'inscripcion': inscripcion_ext,
                        'correo_enviado': enviado,
                        'acceso_disponible': (acceso_ext.inscripcion_id == inscripcion_ext.pk),
                        'mensaje': f"¡Inscripción reactivada con éxito para {participante_ext.nombres} {participante_ext.apellidos}!",
                        **ctx_comprobante,
                    })
                    response['Referrer-Policy'] = 'no-referrer'
                    return response
                else:
                    nueva_insc = Inscripcion.objects.create(
                        evento=evento_lock,
                        participante=participante_ext,
                        estado=EstadoInscripcion.ACTIVA
                    )
                    acceso_ext, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(nueva_insc)
                    establecer_sesion_acceso_externo(request, acceso_ext, nueva_insc)

                    Auditoria.objects.create(
                        usuario=None,
                        accion='INSCRIBIR_EXTERNO',
                        modulo='PARTICIPANTES',
                        registro_afectado=f"Inscripción ID {nueva_insc.pk} - Doc {doc} - Evento {evento_lock.pk}"[:100],
                        ip=get_client_ip(request)
                    )
                    enviado = enviar_correo_confirmacion_externa(nueva_insc, acceso_ext, raw_token, request)
                    ctx_comprobante = _construir_contexto_comprobante_externo(nueva_insc)
                    response = render(request, 'participantes/inscripcion_publica_resultado.html', {
                        'estado': 'EXITOSA',
                        'evento': evento_lock,
                        'participante': participante_ext,
                        'inscripcion': nueva_insc,
                        'correo_enviado': enviado,
                        'acceso_disponible': (acceso_ext.inscripcion_id == nueva_insc.pk),
                        'mensaje': f"¡Inscripción exitosa! {participante_ext.nombres} {participante_ext.apellidos} ha quedado registrado(a) en '{evento_lock.nombre}'.",
                        **ctx_comprobante,
                    })
                    response['Referrer-Policy'] = 'no-referrer'
                    return response
    else:
        form = InscripcionPublicaForm()

    return render(request, 'participantes/inscripcion_publica.html', {
        'evento': evento,
        'form': form,
        'consulta_form': consulta_form,
        'modo_activo': modo_activo,
        'sesion_activa_evento': sesion_activa_evento,
        'total_activos': total_activos,
        'cupos_disponibles': cupos_disponibles,
        'esta_lleno': esta_lleno,
    })


def consultar_inscripcion_publica(request, id_evento):
    """
    Consulta y recuperación pública de una inscripción existente asociada estrictamente al evento indicado.
    Permite a un participante sin cuenta institucional recuperar su comprobante y código QR personal
    tras cerrar el navegador o cambiar de dispositivo validando documento + correo o teléfono.

    Controles de seguridad:
    - Aislamiento estricto por evento (no consulta inscripciones de otros eventos).
    - Limitación de intentos por IP y evento (HTTP 429 ante fuerza bruta).
    - Mensajes de error genéricos anti-enumeración sin exponer datos personales.
    - No crea nuevas inscripciones, no modifica asistencia y no rota tokens vigentes innecesariamente.
    - Redirige a URL limpia (/participantes/externo/mi-inscripcion/) sin tokens ni IDs en la URL.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    if evento.modalidad_inscripcion not in [ModalidadInscripcion.ABIERTA, ModalidadInscripcion.MIXTA]:
        return render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'SOLO_INVITACION',
            'evento': evento,
            'mensaje': f"El evento '{evento.nombre}' está configurado como 'Solo por invitación' y no admite consultas públicas."
        }, status=403)

    if evento.estado in [EstadoEvento.BORRADOR, EstadoEvento.CANCELADO]:
        return render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'NO_DISPONIBLE',
            'evento': evento,
            'mensaje': f"El evento '{evento.nombre}' se encuentra en estado '{evento.get_estado_display()}'."
        }, status=400)

    if request.method != 'POST':
        return redirect(f"{reverse('participantes:inscripcion_publica', kwargs={'id_evento': evento.pk})}?modo=consultar")

    total_activos = evento.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
    cupos_disponibles = max(0, evento.cupo - total_activos) if evento.cupo is not None else None
    esta_lleno = (cupos_disponibles == 0) if cupos_disponibles is not None else False
    sesion_activa_evento = tiene_sesion_externa_activa_evento(request, evento)
    ip_cliente = obtener_ip_rate_limit(request)
    doc_raw = request.POST.get('documento', '')

    # 1. Protección persistente contra fuerza bruta por (evento, documento HMAC) y (evento, IP HMAC)
    bloqueada, _ = esta_bloqueada_consulta_inscripcion(evento.pk, ip_cliente, documento=doc_raw)
    if bloqueada:
        limpiar_sesion_acceso_externo(request)
        Auditoria.objects.create(
            usuario=None,
            accion='CONSULTA_INSCRIPCION_BLOQUEADA_RATE_LIMIT',
            modulo='PARTICIPANTES',
            registro_afectado=f"Límite de intentos excedido - Evento {evento.pk}"[:100],
            ip=ip_cliente,
        )
        response = render(request, 'participantes/inscripcion_publica.html', {
            'evento': evento,
            'form': InscripcionPublicaForm(),
            'consulta_form': ConsultaInscripcionPublicaForm(),
            'modo_activo': 'consultar',
            'sesion_activa_evento': False,
            'consulta_bloqueada': True,
            'consulta_error': (
                "Has realizado demasiados intentos de consulta en pocos minutos. "
                "Por seguridad, espera unos minutos antes de intentarlo nuevamente."
            ),
            'total_activos': total_activos,
            'cupos_disponibles': cupos_disponibles,
            'esta_lleno': esta_lleno,
        }, status=429)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    # 2. Validación de formulario
    consulta_form = ConsultaInscripcionPublicaForm(request.POST)
    if not consulta_form.is_valid():
        response = render(request, 'participantes/inscripcion_publica.html', {
            'evento': evento,
            'form': InscripcionPublicaForm(),
            'consulta_form': consulta_form,
            'modo_activo': 'consultar',
            'sesion_activa_evento': sesion_activa_evento,
            'total_activos': total_activos,
            'cupos_disponibles': cupos_disponibles,
            'esta_lleno': esta_lleno,
        }, status=400)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    doc = consulta_form.cleaned_data['documento']
    dato_verif = consulta_form.cleaned_data['dato_verificacion']

    # 3. Búsqueda verificada estrictamente ligada al evento actual (sin modificar inscripción ni asistencia)
    inscripcion = buscar_inscripcion_publica_verificada(evento, doc, dato_verif)

    if not inscripcion:
        registrar_intento_fallido_consulta(evento.pk, ip_cliente, documento=doc)
        limpiar_sesion_acceso_externo(request)
        # Mensaje estrictamente genérico: nunca confirma si el documento existe ni revela datos personales
        response = render(request, 'participantes/inscripcion_publica.html', {
            'evento': evento,
            'form': InscripcionPublicaForm(),
            'consulta_form': consulta_form,
            'modo_activo': 'consultar',
            'sesion_activa_evento': False,
            'consulta_error': (
                "No se encontró una inscripción activa para este evento con los datos proporcionados. "
                "Verifica tu número de documento y el correo electrónico o teléfono registrado, "
                "o realiza una nueva inscripción."
            ),
            'total_activos': total_activos,
            'cupos_disponibles': cupos_disponibles,
            'esta_lleno': esta_lleno,
        }, status=200)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    limpiar_intentos_consulta(evento.pk, ip_cliente, documento=doc)

    # 4. Si la inscripción pertenece a un usuario con cuenta institucional, dirigir a inicio de sesión seguro
    if inscripcion.participante.usuario_id is not None:
        limpiar_sesion_acceso_externo(request)
        response = render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'CUENTA_INSTITUCIONAL',
            'evento': evento,
            'mensaje': (
                "Tu inscripción en este evento está vinculada a tu cuenta institucional UNIMINUTO. "
                "Inicia sesión para consultar tu pase digital y código QR."
            ),
        })
        response['Referrer-Policy'] = 'no-referrer'
        return response

    # 5. Restaurar acceso externo sin crear nueva inscripción, sin invalidar QR y respetando revocación administrativa
    try:
        acceso_ext, _ = obtener_o_restaurar_acceso_externo(inscripcion)
    except AccesoExternoRevocadoError as exc:
        limpiar_sesion_acceso_externo(request)
        Auditoria.objects.create(
            usuario=None,
            accion='RECUPERACION_ACCESO_REVOCADO_BLOQUEADA',
            modulo='PARTICIPANTES',
            registro_afectado=f"Acceso revocado bloqueado - Inscripción {inscripcion.pk} - Evento {evento.pk}"[:100],
            ip=ip_cliente,
        )
        response = render(request, 'participantes/inscripcion_publica_resultado.html', {
            'estado': 'ACCESO_REVOCADO',
            'evento': evento,
            'mensaje': str(exc),
        }, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    establecer_sesion_acceso_externo(request, acceso_ext, inscripcion)

    Auditoria.objects.create(
        usuario=None,
        accion='RECUPERAR_INSCRIPCION_PUBLICA',
        modulo='PARTICIPANTES',
        registro_afectado=construir_registro_auditoria_recuperacion(inscripcion, ip=ip_cliente),
        ip=ip_cliente,
    )

    messages.success(
        request,
        "¡Inscripción recuperada correctamente! Aquí tienes tu comprobante y tu código QR personal de asistencia."
    )
    response = redirect('participantes:ver_inscripcion_externa')
    response['Referrer-Policy'] = 'no-referrer'
    return response


def consultar_acceso_externo(request, token):
    """
    Punto de entrada para el acceso seguro de un participante externo mediante token (Etapa 7.2.2).
    Valida el token contra su hash SHA-256 en AccesoExternoInscripcion, registra último acceso,
    guarda el contexto en la sesión y redirige inmediatamente a la URL limpia /externo/mi-inscripcion/.
    Configura cabecera Referrer-Policy: no-referrer para prevenir fugas en URLs.
    """
    if not token or len(token.strip()) < 10:
        response = render(request, 'participantes/acceso_externo_resultado.html', {'estado': 'INVALIDO'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    token_hash = hashlib.sha256(token.strip().encode('utf-8')).hexdigest()
    acceso = (
        AccesoExternoInscripcion.objects
        .select_related('inscripcion', 'inscripcion__evento', 'inscripcion__participante')
        .filter(token_hash=token_hash)
        .first()
    )

    if not acceso:
        response = render(request, 'participantes/acceso_externo_resultado.html', {'estado': 'INVALIDO'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if acceso.revocado:
        response = render(request, 'participantes/acceso_externo_resultado.html', {
            'estado': 'REVOCADO',
            'evento': acceso.inscripcion.evento,
        }, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if not acceso.es_valido or (acceso.fecha_expiracion and timezone.now() > acceso.fecha_expiracion):
        response = render(request, 'participantes/acceso_externo_resultado.html', {
            'estado': 'EXPIRADO',
            'evento': acceso.inscripcion.evento,
        }, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    # Registrar fecha de último acceso
    acceso.ultimo_acceso = timezone.now()
    acceso.save(update_fields=['ultimo_acceso'])

    Auditoria.objects.create(
        usuario=None,
        accion='CONSULTAR_ACCESO_EXTERNO',
        modulo='PARTICIPANTES',
        registro_afectado=f"AccesoExterno ID {acceso.pk} - Inscripción {acceso.inscripcion_id}",
        ip=get_client_ip(request)
    )

    # Establecer contexto seguro en sesión y redirigir a URL limpia
    request.session['acceso_externo_id'] = acceso.pk
    request.session['acceso_externo_hash'] = token_hash
    request.session['acceso_externo_inscripcion_id'] = acceso.inscripcion_id
    request.session['acceso_externo_evento_id'] = acceso.inscripcion.evento_id

    response = redirect('participantes:ver_inscripcion_externa')
    response['Referrer-Policy'] = 'no-referrer'
    return response


def ver_inscripcion_externa(request):
    """
    Vista limpia (sin token en la URL) para la página individual del participante externo (Etapa 7.2.2).
    Muestra:
    - Datos del evento: nombre, fecha, horas, lugar, descripción, modalidad.
    - Datos de la inscripción: estado, fecha de registro.
    - Indicaciones para el día del evento.
    Protección contra IDOR mediante validación criptográfica en sesión.
    Protección contra fugas mediante Referrer-Policy: no-referrer.
    """
    acceso_id = request.session.get('acceso_externo_id')
    token_hash = request.session.get('acceso_externo_hash')

    if not acceso_id or not token_hash:
        response = render(request, 'participantes/acceso_externo_resultado.html', {'estado': 'NO_AUTORIZADO'}, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    acceso = (
        AccesoExternoInscripcion.objects
        .select_related(
            'inscripcion',
            'inscripcion__evento',
            'inscripcion__evento__categoria',
            'inscripcion__evento__organizador',
            'inscripcion__participante'
        )
        .filter(pk=acceso_id, token_hash=token_hash)
        .first()
    )

    if not acceso:
        request.session.pop('acceso_externo_id', None)
        request.session.pop('acceso_externo_hash', None)
        response = render(request, 'participantes/acceso_externo_resultado.html', {'estado': 'INVALIDO'}, status=404)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if acceso.revocado:
        response = render(request, 'participantes/acceso_externo_resultado.html', {
            'estado': 'REVOCADO',
            'evento': acceso.inscripcion.evento,
        }, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    if not acceso.es_valido or (acceso.fecha_expiracion and timezone.now() > acceso.fecha_expiracion):
        response = render(request, 'participantes/acceso_externo_resultado.html', {
            'estado': 'EXPIRADO',
            'evento': acceso.inscripcion.evento,
        }, status=403)
        response['Referrer-Policy'] = 'no-referrer'
        return response

    inscripcion = acceso.inscripcion
    evento = inscripcion.evento
    participante = inscripcion.participante

    asistencia = Asistencia.objects.filter(inscripcion=inscripcion).first()
    llegada_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_entrada)
    salida_registrada = bool(asistencia and asistencia.estado == EstadoAsistencia.REGISTRADA and asistencia.hora_salida)
    salidas_habilitadas = es_salida_habilitada(evento)

    token_qr = generar_token_qr(inscripcion)
    qr_bytes = generar_imagen_qr_bytes(token_qr)
    qr_base64 = base64.b64encode(qr_bytes).decode('utf-8')

    response = render(request, 'participantes/acceso_externo_detalle.html', {
        'acceso': acceso,
        'inscripcion': inscripcion,
        'evento': evento,
        'participante': participante,
        'asistencia': asistencia,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
        'salidas_habilitadas': salidas_habilitadas,
        'token_qr': token_qr,
        'qr_base64': qr_base64,
    })
    response['Referrer-Policy'] = 'no-referrer'
    return response


def qr_inscripcion_publica(request, id_evento):
    """
    Entrega la imagen binaria PNG del código QR que apunta
    al formulario público de inscripción del evento (Etapa 7.2.2).
    Soporta descarga directa con ?descargar=1.
    """
    evento = get_object_or_404(Evento, pk=id_evento)
    qr_bytes = generar_qr_inscripcion_publica(evento, request)

    response = HttpResponse(qr_bytes, content_type='image/png')
    if request.GET.get('descargar') == '1':
        response['Content-Disposition'] = f'attachment; filename="QR_Inscripcion_{evento.pk}.png"'
    else:
        response['Content-Disposition'] = f'inline; filename="QR_Inscripcion_{evento.pk}.png"'
    return response
