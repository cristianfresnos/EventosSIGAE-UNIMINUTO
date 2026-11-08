from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.contrib import messages
from django.utils import timezone

from auditoria.models import Auditoria
from participantes.models import Inscripcion, EstadoInscripcion
from asistencia.models import Asistencia, EstadoAsistencia, ControlSalidaEvento
from asistencia.services import es_salida_habilitada
from .models import Evento, CategoriaEvento, ModalidadEvento, EstadoEvento
from .forms import EventoForm


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

    # Verificar permisos de gestión sobre el evento
    puede_gestionar = False
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff or evento.organizador_id == request.user.id:
            puede_gestionar = True
        elif hasattr(request.user, 'rol') and request.user.rol and request.user.rol.nombre in ['Administrador', 'Coordinador']:
            puede_gestionar = True

    puede_inscribirse = (
        evento.estado == EstadoEvento.PUBLICADO and
        not esta_lleno and
        (inscripcion_usuario is None or inscripcion_usuario.estado == EstadoInscripcion.CANCELADA)
    )

    control_salida = None
    total_llegadas = 0
    total_salidas = 0
    salidas_habilitadas = False
    asistencia_usuario = None
    llegada_registrada = False
    salida_registrada = False

    if puede_gestionar:
        control_salida = ControlSalidaEvento.objects.filter(evento=evento).first()
        salidas_habilitadas = es_salida_habilitada(evento)
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
    else:
        salidas_habilitadas = es_salida_habilitada(evento)

    if inscripcion_usuario:
        asistencia_usuario = getattr(inscripcion_usuario, 'asistencia', None)
        llegada_registrada = bool(asistencia_usuario and asistencia_usuario.estado == EstadoAsistencia.REGISTRADA and asistencia_usuario.hora_entrada)
        salida_registrada = bool(asistencia_usuario and asistencia_usuario.estado == EstadoAsistencia.REGISTRADA and asistencia_usuario.hora_salida)

    return render(request, 'eventos/detalle.html', {
        'evento': evento,
        'total_activos': total_activos,
        'cupos_disponibles': cupos_disponibles,
        'esta_lleno': esta_lleno,
        'inscripcion_usuario': inscripcion_usuario,
        'puede_inscribirse': puede_inscribirse,
        'puede_gestionar': puede_gestionar,
        'control_salida': control_salida,
        'total_llegadas': total_llegadas,
        'total_salidas': total_salidas,
        'salidas_habilitadas': salidas_habilitadas,
        'asistencia_usuario': asistencia_usuario,
        'llegada_registrada': llegada_registrada,
        'salida_registrada': salida_registrada,
    })


@login_required
def mis_eventos(request):
    """
    Panel de gestión para organizadores y personal institucional.
    """
    if not (es_usuario_gestion(request.user) or Evento.objects.filter(organizador=request.user).exists()):
        raise PermissionDenied("No tienes permisos para acceder al panel de gestión de eventos.")

    if request.user.is_superuser or request.user.is_staff or (hasattr(request.user, 'rol') and request.user.rol and request.user.rol.nombre in ['Administrador', 'Coordinador']):
        eventos = (
            Evento.objects.select_related('categoria', 'organizador')
            .annotate(total_activos=Count('inscripciones', filter=Q(inscripciones__estado=EstadoInscripcion.ACTIVA)))
            .order_by('-fecha', '-hora_inicio')
        )
        modo_vista = 'todos'
    else:
        eventos = (
            Evento.objects.filter(organizador=request.user)
            .select_related('categoria', 'organizador')
            .annotate(total_activos=Count('inscripciones', filter=Q(inscripciones__estado=EstadoInscripcion.ACTIVA)))
            .order_by('-fecha', '-hora_inicio')
        )
        modo_vista = 'propios'

    return render(request, 'eventos/mis_eventos.html', {
        'eventos': eventos,
        'modo_vista': modo_vista,
    })


@login_required
def crear_evento(request):
    """
    Creación de nuevos eventos institucionales por parte de usuarios autorizados.
    """
    if not es_usuario_gestion(request.user):
        raise PermissionDenied("No cuentas con permisos para crear eventos institucionales.")

    if request.method == 'POST':
        form = EventoForm(request.POST)
        if form.is_valid():
            evento = form.save(commit=False)
            evento.organizador = request.user
            evento.save()

            Auditoria.objects.create(
                usuario=request.user,
                accion='CREAR_EVENTO',
                modulo='EVENTOS',
                registro_afectado=f"Evento ID {evento.pk} - {evento.nombre}",
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
    Edición de evento existente por su organizador o administradores.
    """
    evento = get_object_or_404(Evento, pk=id_evento)

    # Control de autorización
    es_organizador = (evento.organizador_id == request.user.id)
    es_admin = (request.user.is_superuser or request.user.is_staff or (hasattr(request.user, 'rol') and request.user.rol and request.user.rol.nombre in ['Administrador', 'Coordinador']))

    if not (es_organizador or es_admin):
        raise PermissionDenied("No tienes autorización para editar este evento.")

    if request.method == 'POST':
        form = EventoForm(request.POST, instance=evento)
        if form.is_valid():
            evento_actualizado = form.save()

            Auditoria.objects.create(
                usuario=request.user,
                accion='EDITAR_EVENTO',
                modulo='EVENTOS',
                registro_afectado=f"Evento ID {evento_actualizado.pk} - {evento_actualizado.nombre}",
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
    Autorización exclusiva para el organizador del evento o administradores institucionales.
    Preserva las inscripciones existentes en la base de datos para fines históricos y de trazabilidad.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    es_organizador = (evento.organizador_id == request.user.id)
    es_admin = (
        request.user.is_superuser
        or request.user.is_staff
        or (hasattr(request.user, 'rol') and request.user.rol and request.user.rol.nombre in ['Administrador', 'Coordinador'])
    )

    if not (es_organizador or es_admin):
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

