"""
Servicio centralizado de autorización por evento y gestión de docentes asociados.
Fuente única de verdad compartida entre eventos, asistencia, participantes, reportes y analítica.
Proyecto: EventosSIGAE-UNIMINUTO
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from auditoria.models import Auditoria
from .models import Evento, DocenteEvento


def es_admin_o_coordinador(user):
    """
    Determina si el usuario tiene privilegios administrativos o de coordinación institucional
    con alcance sobre la gestión general de eventos y asignación de docentes.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    rol = getattr(user, 'rol', None)
    return bool(rol and getattr(rol, 'nombre', None) in ('Administrador', 'Coordinador'))


def es_docente_rol(user):
    """Determina si el usuario autenticado posee rol institucional Docente."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    rol = getattr(user, 'rol', None)
    return bool(rol and getattr(rol, 'nombre', None) == 'Docente')


def es_docente_asociado(user, evento):
    """
    Determina si el usuario está autorizado operativamente sobre un evento específico
    ya sea como organizador creador o como docente asociado activo en DocenteEvento.
    """
    if not user or not getattr(user, 'is_authenticated', False) or evento is None:
        return False
    if evento.organizador_id == user.id:
        return True
    return DocenteEvento.objects.filter(
        evento=evento,
        docente=user,
        activo=True,
    ).exists()


def puede_gestionar_evento(user, evento):
    """
    Regla unificada de permisos operativos compartidos sobre un evento:
    - Administradores, Coordinadores, staff y superusuarios: acceso autorizado.
    - Organizador del evento: acceso autorizado.
    - Docentes asociados activos (DocenteEvento): mismos permisos operativos compartidos
      (asistencia, sesiones QR, participantes, reportes PDF y estadísticas).
    - Docentes NO asociados y Estudiantes: acceso denegado (False).
    """
    if not user or not getattr(user, 'is_authenticated', False) or evento is None:
        return False
    if es_admin_o_coordinador(user):
        return True
    return es_docente_asociado(user, evento)


def puede_editar_evento(user, evento):
    """
    Regla centralizada de permiso estructural para editar un evento:
    - Administradores, Coordinadores, staff y superusuarios: permitido según su alcance institucional.
    - Organizador del evento: permitido sobre sus propios eventos.
    - Docentes asociados que NO sean el organizador: denegado (solo permisos operativos).
    - Docentes NO asociados y Estudiantes: denegado.
    """
    if not user or not getattr(user, 'is_authenticated', False) or evento is None:
        return False
    if es_admin_o_coordinador(user):
        return True
    return evento.organizador_id == user.id


def puede_cancelar_evento(user, evento):
    """
    Regla centralizada de permiso estructural para cancelar formalmente un evento:
    - Administradores, Coordinadores, staff y superusuarios: permitido según su alcance institucional.
    - Organizador del evento: permitido sobre sus propios eventos.
    - Docentes asociados que NO sean el organizador: denegado (solo permisos operativos).
    - Docentes NO asociados y Estudiantes: denegado.
    """
    return puede_editar_evento(user, evento)


def puede_asignar_docentes(user):
    """
    La asignación y remoción de docentes asociados a un evento está reservada
    exclusivamente a Administradores y Coordinadores (y staff/superusuarios).
    """
    return es_admin_o_coordinador(user)


def obtener_eventos_gestionables(user):
    """
    Retorna el QuerySet de eventos que el usuario está autorizado a consultar y gestionar:
    - Administrador / Coordinador / staff / superuser: todos los eventos.
    - Docente u organizador: únicamente eventos donde es organizador o docente asociado activo.
    - Otros roles (Estudiante / anónimo): QuerySet vacío.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return Evento.objects.none()

    if es_admin_o_coordinador(user):
        return Evento.objects.all().select_related('categoria', 'organizador')

    if (
        es_docente_rol(user)
        or Evento.objects.filter(organizador=user).exists()
        or DocenteEvento.objects.filter(docente=user, activo=True).exists()
    ):
        return (
            Evento.objects
            .filter(
                Q(organizador=user)
                | Q(docentes_asociados_rel__docente=user, docentes_asociados_rel__activo=True)
            )
            .select_related('categoria', 'organizador')
            .distinct()
        )

    return Evento.objects.none()


def obtener_docentes_asociados_evento(evento):
    """Retorna las asignaciones activas de docentes asociados al evento."""
    return (
        DocenteEvento.objects
        .filter(evento=evento, activo=True)
        .select_related('docente', 'asignado_por')
        .order_by('docente__apellidos', 'docente__nombres')
    )


def obtener_nrcs_evento(evento):
    """Retorna la lista ordenada y sin duplicados de NRCs configurados para el evento."""
    nrcs = (
        DocenteEvento.objects
        .filter(evento=evento, activo=True)
        .exclude(nrc__isnull=True)
        .exclude(nrc__exact='')
        .values_list('nrc', flat=True)
        .distinct()
    )
    return sorted({n.strip() for n in nrcs if n and n.strip()})


def asignar_docente_evento_service(evento, docente, asignado_por, nrc=None, ip=None):
    """
    Asocia (o reactiva) un usuario con rol Docente a un evento con trazabilidad en auditoría.
    Solo puede ser ejecutado por un Administrador o Coordinador.
    """
    if not puede_asignar_docentes(asignado_por):
        raise PermissionDenied("Solo Administradores o Coordinadores pueden asociar docentes a un evento.")

    rol = getattr(docente, 'rol', None)
    if not rol or getattr(rol, 'nombre', None) != 'Docente':
        raise ValidationError("Solo se pueden asociar usuarios con rol institucional Docente.")
    if not docente.is_active:
        raise ValidationError("No se puede asociar un usuario docente inactivo.")

    nrc_limpio = nrc.strip() if isinstance(nrc, str) and nrc.strip() else None

    with transaction.atomic():
        asignacion = (
            DocenteEvento.objects
            .select_for_update()
            .filter(evento=evento, docente=docente)
            .first()
        )
        if asignacion:
            ya_activo = asignacion.activo
            asignacion.activo = True
            asignacion.asignado_por = asignado_por
            if nrc_limpio is not None:
                asignacion.nrc = nrc_limpio
            asignacion.full_clean()
            asignacion.save()
            creada = not ya_activo
        else:
            asignacion = DocenteEvento(
                evento=evento,
                docente=docente,
                asignado_por=asignado_por,
                nrc=nrc_limpio,
                activo=True,
            )
            asignacion.full_clean()
            asignacion.save()
            creada = True

        nrc_info = f" (NRC {nrc_limpio})" if nrc_limpio else ""
        Auditoria.objects.create(
            usuario=asignado_por,
            accion='ASIGNAR_DOCENTE_EVENTO',
            modulo='EVENTOS',
            registro_afectado=f"Docente {docente.username} asociado a Evento ID {evento.pk}{nrc_info}"[:100],
            ip=ip,
        )
        return asignacion, creada


def remover_docente_evento_service(evento, docente, responsable, ip=None):
    """
    Desasocia de forma segura (soft-delete activo=False) a un docente de un evento con auditoría.
    Solo puede ser ejecutado por un Administrador o Coordinador.
    """
    if not puede_asignar_docentes(responsable):
        raise PermissionDenied("Solo Administradores o Coordinadores pueden remover docentes de un evento.")

    with transaction.atomic():
        asignacion = (
            DocenteEvento.objects
            .select_for_update()
            .filter(evento=evento, docente=docente, activo=True)
            .first()
        )
        if not asignacion:
            return False
        asignacion.activo = False
        asignacion.save(update_fields=['activo'])

        Auditoria.objects.create(
            usuario=responsable,
            accion='REMOVER_DOCENTE_EVENTO',
            modulo='EVENTOS',
            registro_afectado=f"Docente {docente.username} desasociado de Evento ID {evento.pk}"[:100],
            ip=ip,
        )
        return True
