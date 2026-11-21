import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone

from auditoria.models import Auditoria
from usuarios.models import Usuario
from participantes.models import Inscripcion, EstadoInscripcion
from participantes.services import diagnosticar_acceso_externo_sesion
from asistencia.models import Asistencia, EstadoAsistencia, ControlEntradaEvento, ControlSalidaEvento
from asistencia.services import (
    es_salida_habilitada,
    obtener_estado_sesiones_evento,
    inicializar_controles_sesiones_evento,
)
from .models import Evento, CategoriaEvento, ModalidadEvento, EstadoEvento, CalificacionEvento, DocenteEvento
from .forms import EventoForm
from .permissions import (
    es_admin_o_coordinador,
    puede_gestionar_evento,
    puede_editar_evento,
    puede_cancelar_evento,
    puede_asignar_docentes,
    obtener_eventos_gestionables,
    obtener_docentes_asociados_evento,
    obtener_nrcs_evento,
    asignar_docente_evento_service,
    remover_docente_evento_service,
)
from .services import (
    ETIQUETAS_ESTRELLAS,
    es_estudiante_elegible_rol,
    verificar_elegibilidad_calificacion,
    verificar_elegibilidad_calificacion_externa,
    obtener_evaluaciones_pendientes,
    registrar_o_actualizar_calificacion,
    registrar_o_actualizar_calificacion_externa,
    calcular_estadisticas_calificacion,
)


def get_client_ip(request):
    """Obtiene la IP del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def es_usuario_gestion(user):
    """Verifica si el usuario tiene rol de gestión institucional."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Administrador', 'Coordinador', 'Docente']:
        return True
    return False


def catalogo_eventos(request):
    """
    Catálogo público de eventos con filtros por categoría, modalidad, estado y búsqueda.
    """
    eventos_qs = (
        Evento.objects.select_related('categoria', 'organizador')
        .annotate(
            total_activos=Count('inscripciones', filter=Q(inscripciones__estado=EstadoInscripcion.ACTIVA))
        )
    )

    # Filtros
    estado_filtro = request.GET.get('estado')
    if estado_filtro:
        eventos_qs = eventos_qs.filter(estado=estado_filtro)
    else:
        # Por defecto muestra eventos publicados
        eventos_qs = eventos_qs.filter(estado=EstadoEvento.PUBLICADO)

    categoria_id = request.GET.get('categoria')
    if categoria_id and categoria_id.isdigit():
        eventos_qs = eventos_qs.filter(categoria_id=int(categoria_id))

    modalidad_filtro = request.GET.get('modalidad')
    if modalidad_filtro in ModalidadEvento.values:
        eventos_qs = eventos_qs.filter(modalidad=modalidad_filtro)

    q = request.GET.get('q')
    if q:
        eventos_qs = eventos_qs.filter(
            Q(nombre__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(lugar__icontains=q)
        )

    fecha_desde = request.GET.get('fecha_desde')
    if fecha_desde:
        eventos_qs = eventos_qs.filter(fecha__gte=fecha_desde)

    eventos = list(eventos_qs.order_by('fecha', 'hora_inicio'))

    # Agregar información de cupos disponibles
    for e in eventos:
        if e.cupo is not None:
            e.cupos_disponibles = max(0, e.cupo - e.total_activos)
            e.esta_lleno = e.cupos_disponibles == 0
        else:
            e.cupos_disponibles = None
            e.esta_lleno = False

    categorias = CategoriaEvento.objects.filter(activo=True)
    modalidades = ModalidadEvento.choices
    estados = EstadoEvento.choices

    return render(request, 'eventos/catalogo.html', {
        'eventos': eventos,
        'categorias': categorias,
        'modalidades': modalidades,
        'estados': estados,
        'filtro_categoria': categoria_id,
        'filtro_modalidad': modalidad_filtro,
        'filtro_estado': estado_filtro or EstadoEvento.PUBLICADO,
        'filtro_q': q or '',
        'filtro_fecha_desde': fecha_desde or '',
        'total_resultados': len(eventos),
    })


def detalle_evento(request, id_evento):
    """
    Vista detallada de un evento con información de cupo, organizador y estado de inscripción.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    total_activos = evento.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
    cupos_disponibles = max(0, evento.cupo - total_activos) if evento.cupo is not None else None
    esta_lleno = (cupos_disponibles == 0) if cupos_disponibles is not None else False

    # Verificar si el usuario autenticado ya está inscrito
    inscripcion_usuario = None
    if request.user.is_authenticated:
        inscripcion_usuario = (
            Inscripcion.objects
            .filter(evento=evento, participante__usuario=request.user)
            .first()
        )

    # Verificar permisos de gestión operativa y estructural sobre el evento
    puede_gestionar = puede_gestionar_evento(request.user, evento)
    puede_editar = puede_editar_evento(request.user, evento)
    puede_cancelar = puede_cancelar_evento(request.user, evento)
    puede_asignar = puede_asignar_docentes(request.user)
    docentes_asociados = list(obtener_docentes_asociados_evento(evento))
    nrcs_evento = obtener_nrcs_evento(evento)
    docentes_disponibles = []
    if puede_asignar:
        ids_asociados = [d.docente_id for d in docentes_asociados]
        docentes_disponibles = list(
            Usuario.objects
            .filter(rol__nombre='Docente', is_active=True)
            .exclude(pk__in=ids_asociados)
            .order_by('apellidos', 'nombres')
        )

    puede_inscribirse = (
        evento.estado == EstadoEvento.PUBLICADO and
        not esta_lleno and
        (inscripcion_usuario is None or inscripcion_usuario.estado == EstadoInscripcion.CANCELADA)
    )

    estado_sesiones = obtener_estado_sesiones_evento(evento)
    control_entrada = estado_sesiones['control_entrada']
    control_salida = estado_sesiones['control_salida']
    entradas_habilitadas = estado_sesiones['entradas_permitidas']
    salidas_habilitadas = estado_sesiones['salidas_permitidas']
    total_llegadas = 0
    total_salidas = 0
    asistencia_usuario = None
    llegada_registrada = False
    salida_registrada = False

    if puede_gestionar:
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

    if inscripcion_usuario:
        asistencia_usuario = getattr(inscripcion_usuario, 'asistencia', None)
        llegada_registrada = bool(asistencia_usuario and asistencia_usuario.estado == EstadoAsistencia.REGISTRADA and asistencia_usuario.hora_entrada)
        salida_registrada = bool(asistencia_usuario and asistencia_usuario.estado == EstadoAsistencia.REGISTRADA and asistencia_usuario.hora_salida)

    # Estadísticas de calificación del evento (RF-30) — nunca expone calificaciones individuales de terceros
    estadisticas_calificacion = calcular_estadisticas_calificacion(evento)

    calificacion_usuario = None
    puede_calificar_usuario = False
    calificacion_pendiente_usuario = False
    if request.user.is_authenticated and es_estudiante_elegible_rol(request.user):
        eleg = verificar_elegibilidad_calificacion(request.user, evento)
        puede_calificar_usuario = eleg['elegible']
        calificacion_usuario = eleg['calificacion_existente']
        calificacion_pendiente_usuario = bool(puede_calificar_usuario and calificacion_usuario is None)

    return render(request, 'eventos/detalle.html', {
        'evento': evento,
        'total_activos': total_activos,
        'cupos_disponibles': cupos_disponibles,
        'esta_lleno': esta_lleno,
        'inscripcion_usuario': inscripcion_usuario,
        'puede_inscribirse': puede_inscribirse,
        'puede_gestionar': puede_gestionar,
        'puede_editar_evento': puede_editar,
        'puede_cancelar_evento': puede_cancelar,
        'puede_asignar_docentes': puede_asignar,
        'docentes_asociados': docentes_asociados,
        'docentes_disponibles': docentes_disponibles,
        'nrcs_evento': nrcs_evento,
        'estado_sesiones': estado_sesiones,
        'control_entrada': control_entrada,
        'control_salida': control_salida,
        'entradas_habilitadas': entradas_habilitadas,
        'total_llegadas': total_llegadas,
        'total_salidas': total_salidas,
        'salidas_habilitadas': salidas_habilitadas,
        'asistencia_usuario': asistencia_usuario,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
        'estadisticas_calificacion': estadisticas_calificacion,
        'calificacion_usuario': calificacion_usuario,
        'puede_calificar_usuario': puede_calificar_usuario,
        'calificacion_pendiente_usuario': calificacion_pendiente_usuario,
    })


@login_required
def mis_eventos(request):
    """
    Panel de gestión para organizadores, docentes asociados y personal institucional.
    """
    if not (
        es_usuario_gestion(request.user)
        or Evento.objects.filter(organizador=request.user).exists()
        or DocenteEvento.objects.filter(docente=request.user, activo=True).exists()
    ):
        raise PermissionDenied("No tienes permisos para acceder al panel de gestión de eventos.")

    eventos_qs = (
        obtener_eventos_gestionables(request.user)
        .annotate(total_activos=Count('inscripciones', filter=Q(inscripciones__estado=EstadoInscripcion.ACTIVA), distinct=True))
        .order_by('-fecha', '-hora_inicio')
    )
    modo_vista = 'todos' if es_admin_o_coordinador(request.user) else 'propios'

    eventos = list(eventos_qs)
    if eventos:
        stats_map = {
            item['evento_id']: item
            for item in (
                CalificacionEvento.objects
                .filter(evento_id__in=[e.pk for e in eventos])
                .values('evento_id')
                .annotate(
                    promedio=Avg('puntuacion'),
                    total=Count('id_calificacion'),
                )
            )
        }
        for e in eventos:
            st = stats_map.get(e.pk)
            if st and st['total']:
                e.promedio_calificacion = round(float(st['promedio']), 1)
                e.total_calificaciones = st['total']
            else:
                e.promedio_calificacion = None
                e.total_calificaciones = 0
            e.puede_editar = puede_editar_evento(request.user, e)
            e.puede_cancelar = puede_cancelar_evento(request.user, e)

    return render(request, 'eventos/mis_eventos.html', {
        'eventos': eventos,
        'modo_vista': modo_vista,
    })


@login_required
def crear_evento(request):
    """
    Creación de nuevos eventos institucionales por parte de usuarios autorizados.
    Todo evento nuevo inicializa de forma atómica e idempotente tanto ControlEntradaEvento
    (entradas_habilitadas=False) como ControlSalidaEvento (salidas_habilitadas=False) para
    exigir activación formal de cada sesión compartida.
    """
    if not es_usuario_gestion(request.user):
        raise PermissionDenied("No cuentas con permisos para crear eventos institucionales.")

    if request.method == 'POST':
        form = EventoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                evento = form.save(commit=False)
                evento.organizador = request.user
                evento.save()

                # Todo evento nuevo inicializa ambas sesiones compartidas en estado cerrado
                inicializar_controles_sesiones_evento(evento)

                Auditoria.objects.create(
                    usuario=request.user,
                    accion='CREAR_EVENTO',
                    modulo='EVENTOS',
                    registro_afectado=f"Evento ID {evento.pk} - {evento.nombre}"[:100],
                    ip=get_client_ip(request)
                )

            messages.success(request, f"¡El evento '{evento.nombre}' fue creado exitosamente!")
            return redirect('eventos:detalle', id_evento=evento.pk)
        else:
            messages.error(request, "Por favor corrige los errores señalados en el formulario.")
    else:
        form = EventoForm(initial={
            'estado': EstadoEvento.PUBLICADO,
            'modalidad': ModalidadEvento.PRESENCIAL,
            'fecha': timezone.now().date(),
        })

    return render(request, 'eventos/form_evento.html', {
        'form': form,
        'titulo': 'Crear Nuevo Evento',
        'accion': 'Crear Evento',
    })


@login_required
def editar_evento(request, id_evento):
    """
    Edición estructural de evento existente reservada a Administradores, Coordinadores
    y al Organizador creador del evento. Los docentes asociados sin rol organizador
    conservan sus permisos operativos pero no pueden editar la estructura del evento.
    """
    evento = get_object_or_404(Evento, pk=id_evento)

    if not puede_editar_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para editar este evento.")

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento)
        if form.is_valid():
            evento_actualizado = form.save()

            Auditoria.objects.create(
                usuario=request.user,
                accion='EDITAR_EVENTO',
                modulo='EVENTOS',
                registro_afectado=f"Evento ID {evento_actualizado.pk} - {evento_actualizado.nombre}"[:100],
                ip=get_client_ip(request)
            )

            messages.success(request, f"¡El evento '{evento_actualizado.nombre}' fue actualizado correctamente!")
            return redirect('eventos:detalle', id_evento=evento_actualizado.pk)
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = EventoForm(instance=evento)

    return render(request, 'eventos/form_evento.html', {
        'form': form,
        'evento': evento,
        'titulo': f'Editar Evento: {evento.nombre}',
        'accion': 'Guardar Cambios',
    })


@login_required
def cancelar_evento(request, id_evento):
    """
    Cancelación formal de eventos institucionales con justificación y auditoría (RF-05).
    Autorización estructural reservada a Administradores, Coordinadores y al Organizador creador.
    Preserva las inscripciones existentes en la base de datos para fines históricos y de trazabilidad.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    if not puede_cancelar_evento(request.user, evento):
        raise PermissionDenied("No tienes autorización para cancelar este evento.")

    if evento.estado == EstadoEvento.CANCELADO:
        messages.info(request, f"El evento '{evento.nombre}' ya se encuentra formalmente cancelado.")
        return redirect('eventos:detalle', id_evento=evento.pk)

    if evento.estado == EstadoEvento.FINALIZADO:
        messages.error(request, f"No es posible cancelar el evento '{evento.nombre}' porque ya ha finalizado.")
        return redirect('eventos:detalle', id_evento=evento.pk)

    total_inscritos = evento.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()

    if request.method == 'POST':
        motivo = request.POST.get('motivo_cancelacion', '').strip()
        if not motivo:
            messages.error(request, "Debes proporcionar un motivo justificado para cancelar el evento.")
            return render(request, 'eventos/confirmar_cancelacion.html', {
                'evento': evento,
                'total_inscritos': total_inscritos,
            })

        evento.estado = EstadoEvento.CANCELADO
        evento.save()

        # Auditoría de la cancelación con el motivo registrado (respetando max_length=100)
        Auditoria.objects.create(
            usuario=request.user,
            accion='CANCELAR_EVENTO',
            modulo='EVENTOS',
            registro_afectado=f"Evento ID {evento.pk} - {evento.nombre} (Motivo: {motivo} | {total_inscritos} inscripciones)"[:100],
            ip=get_client_ip(request)
        )

        messages.warning(
            request,
            f"El evento '{evento.nombre}' fue cancelado formalmente. Se conservaron {total_inscritos} inscripciones en el historial."
        )
        return redirect('eventos:detalle', id_evento=evento.pk)

    return render(request, 'eventos/confirmar_cancelacion.html', {
        'evento': evento,
        'total_inscritos': total_inscritos,
    })


def calificar_evento(request, id_evento):
    """
    Vista obligatoria de calificación mediante 5 estrellas para participantes que completaron
    su asistencia (inscripción activa, entrada confirmada y salida registrada) (RF-24 a RF-31).

    Reglas de seguridad y negocio:
    - Estudiantes institucionales: requiere sesión autenticada y rol Estudiante (Docentes,
      Coordinadores y Administradores reciben 403).
    - Participantes externos: no requiere cuenta institucional; valida estrictamente la sesión
      externa criptográfica (acceso_externo_id + acceso_externo_hash) sin aceptar inscripcion_id
      ni participante_id desde el navegador.
    - Visitantes anónimos sin sesión externa son redirigidos al inicio de sesión institucional.
    - Cuando no existe calificación previa, la evaluación es obligatoria (sin opciones para omitir).
    - Cuando ya existe calificación previa del mismo sujeto, permite actualizar su propia puntuación.
    - No expone ni permite modificar calificaciones de otros participantes.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.content_type == 'application/json'
    )

    es_externo = False
    acceso_externo = None

    if request.user.is_authenticated:
        elegibilidad = verificar_elegibilidad_calificacion(request.user, evento)
    else:
        acceso_externo, codigo_ext, mensaje_ext = diagnosticar_acceso_externo_sesion(request, evento=evento)
        if codigo_ext == 'SIN_SESION':
            if is_ajax:
                return JsonResponse({
                    'exito': False,
                    'codigo': 'NO_AUTENTICADO',
                    'mensaje': 'Debes iniciar sesión o recuperar tu inscripción pública para calificar este evento.',
                }, status=403)
            return redirect(f"{reverse('usuarios:login')}?next={request.path}")

        if codigo_ext != 'VALIDO' or acceso_externo is None:
            if is_ajax:
                resp = JsonResponse({
                    'exito': False,
                    'codigo': codigo_ext,
                    'mensaje': mensaje_ext,
                }, status=403)
                resp['Referrer-Policy'] = 'no-referrer'
                return resp
            raise PermissionDenied(mensaje_ext)

        es_externo = True
        elegibilidad = verificar_elegibilidad_calificacion_externa(
            acceso_externo.inscripcion,
            evento=evento,
            acceso_externo=acceso_externo,
        )

    if not elegibilidad['elegible']:
        if is_ajax:
            resp = JsonResponse({
                'exito': False,
                'codigo': elegibilidad['codigo'],
                'mensaje': elegibilidad['mensaje'],
            }, status=403)
            if es_externo:
                resp['Referrer-Policy'] = 'no-referrer'
            return resp
        raise PermissionDenied(elegibilidad['mensaje'])

    asistencia = elegibilidad['asistencia']
    calificacion_existente = elegibilidad['calificacion_existente']
    es_obligatoria = (calificacion_existente is None)
    confirmada = (request.GET.get('confirmada') == '1' and calificacion_existente is not None)
    error_mensaje = None

    if request.method == 'POST':
        puntuacion_raw = request.POST.get('puntuacion')
        if puntuacion_raw is None and request.content_type == 'application/json':
            try:
                body_data = json.loads(request.body)
                puntuacion_raw = body_data.get('puntuacion')
            except Exception:
                puntuacion_raw = None

        if es_externo:
            resultado = registrar_o_actualizar_calificacion_externa(
                inscripcion=acceso_externo.inscripcion,
                acceso_externo=acceso_externo,
                evento=evento,
                puntuacion_raw=puntuacion_raw,
                ip=get_client_ip(request),
            )
        else:
            resultado = registrar_o_actualizar_calificacion(
                user=request.user,
                evento=evento,
                puntuacion_raw=puntuacion_raw,
                ip=get_client_ip(request),
            )

        if is_ajax:
            if es_externo:
                siguiente_pendiente = None
                siguiente_url = reverse('participantes:ver_inscripcion_externa')
            else:
                pendientes_restantes = obtener_evaluaciones_pendientes(request.user)
                siguiente_pendiente = pendientes_restantes.first()
                siguiente_url = (
                    reverse('eventos:calificar_evento', kwargs={'id_evento': siguiente_pendiente.evento_id})
                    if siguiente_pendiente else reverse('participantes:mis_inscripciones')
                )
            resp = JsonResponse({
                'exito': resultado['exito'],
                'codigo': resultado['codigo'],
                'mensaje': resultado['mensaje'],
                'puntuacion': resultado['calificacion'].puntuacion if resultado.get('calificacion') else None,
                'etiqueta': resultado['calificacion'].etiqueta_puntuacion if resultado.get('calificacion') else '',
                'creada': resultado['creada'],
                'actualizada': resultado['actualizada'],
                'tiene_pendientes': siguiente_pendiente is not None,
                'siguiente_url': siguiente_url,
            }, status=resultado['status_http'])
            if es_externo:
                resp['Referrer-Policy'] = 'no-referrer'
            return resp

        if resultado['exito']:
            messages.success(request, resultado['mensaje'])
            resp = redirect(f"{reverse('eventos:calificar_evento', kwargs={'id_evento': evento.pk})}?confirmada=1")
            if es_externo:
                resp['Referrer-Policy'] = 'no-referrer'
            return resp

        error_mensaje = resultado['mensaje']
        status_code = resultado['status_http']
        resp = render(request, 'eventos/calificar_evento.html', {
            'evento': evento,
            'asistencia': asistencia,
            'calificacion': calificacion_existente,
            'es_obligatoria': es_obligatoria,
            'ocultar_navegacion_obligatoria': es_obligatoria,
            'es_externo': es_externo,
            'confirmada': False,
            'error_mensaje': error_mensaje,
            'etiquetas_estrellas': ETIQUETAS_ESTRELLAS,
            'pendientes_restantes': [],
            'siguiente_pendiente': None,
        }, status=status_code)
        if es_externo:
            resp['Referrer-Policy'] = 'no-referrer'
        return resp

    if es_externo:
        pendientes_restantes = []
        siguiente_pendiente = None
    else:
        pendientes_restantes = list(obtener_evaluaciones_pendientes(request.user).exclude(evento_id=evento.pk))
        siguiente_pendiente = pendientes_restantes[0] if pendientes_restantes else None

    resp = render(request, 'eventos/calificar_evento.html', {
        'evento': evento,
        'asistencia': asistencia,
        'calificacion': calificacion_existente,
        'es_obligatoria': es_obligatoria,
        'ocultar_navegacion_obligatoria': es_obligatoria,
        'es_externo': es_externo,
        'confirmada': confirmada,
        'error_mensaje': error_mensaje,
        'etiquetas_estrellas': ETIQUETAS_ESTRELLAS,
        'pendientes_restantes': pendientes_restantes,
        'siguiente_pendiente': siguiente_pendiente,
    })
    if es_externo:
        resp['Referrer-Policy'] = 'no-referrer'
    return resp


@login_required
def gestionar_docentes_evento(request, id_evento):
    """
    Permite exclusivamente a Administradores y Coordinadores asociar docentes a un evento
    (con NRC/curso opcional), otorgándoles permisos operativos compartidos sobre el evento.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    if not puede_asignar_docentes(request.user):
        raise PermissionDenied("Solo Administradores o Coordinadores pueden gestionar los docentes asociados a un evento.")

    if request.method == 'POST':
        docente_id = request.POST.get('docente_id')
        nrc = (request.POST.get('nrc') or '').strip() or None

        if not docente_id or not str(docente_id).isdigit():
            messages.error(request, "Debes seleccionar un docente válido para asociar al evento.")
            return redirect('eventos:detalle', id_evento=evento.pk)

        docente = get_object_or_404(Usuario.objects.select_related('rol'), pk=int(docente_id))
        try:
            asignacion, creada = asignar_docente_evento_service(
                evento=evento,
                docente=docente,
                asignado_por=request.user,
                nrc=nrc,
                ip=get_client_ip(request),
            )
            if creada:
                messages.success(
                    request,
                    f"El docente {docente.get_full_name() or docente.username} fue asociado exitosamente al evento."
                )
            else:
                messages.info(
                    request,
                    f"La asociación del docente {docente.get_full_name() or docente.username} fue actualizada."
                )
        except ValidationError as exc:
            msg_err = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
            messages.error(request, msg_err)

        return redirect('eventos:detalle', id_evento=evento.pk)

    return redirect('eventos:detalle', id_evento=evento.pk)


@login_required
def remover_docente_evento(request, id_evento, id_docente):
    """
    Permite exclusivamente a Administradores y Coordinadores desasociar a un docente de un evento.
    """
    if request.method != 'POST':
        messages.error(request, "La desasociación de docentes debe realizarse mediante solicitud POST.")
        return redirect('eventos:detalle', id_evento=id_evento)

    evento = get_object_or_404(Evento, pk=id_evento)
    if not puede_asignar_docentes(request.user):
        raise PermissionDenied("Solo Administradores o Coordinadores pueden desasociar docentes de un evento.")

    docente = get_object_or_404(Usuario, pk=id_docente)
    removido = remover_docente_evento_service(
        evento=evento,
        docente=docente,
        responsable=request.user,
        ip=get_client_ip(request),
    )
    if removido:
        messages.warning(
            request,
            f"El docente {docente.get_full_name() or docente.username} fue desasociado del evento."
        )
    else:
        messages.info(request, "El docente indicado no tenía una asociación activa con este evento.")

    return redirect('eventos:detalle', id_evento=evento.pk)



