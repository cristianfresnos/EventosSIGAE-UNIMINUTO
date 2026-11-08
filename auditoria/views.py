"""
Vistas para la consulta y auditoría de seguridad del portal web.
Proyecto: EventosSIGAE-UNIMINUTO (RF-23)
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Auditoria


def get_client_ip(request):
    """Obtiene la dirección IP del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def es_administrador(user):
    """Verifica si el usuario cuenta con perfil de Administrador institucional."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre == 'Administrador':
        return True
    return False


@login_required
def consulta_auditoria(request):
    """
    Vista de solo lectura para la consulta y trazabilidad de la bitácora de auditoría (RF-23).
    Acceso estrictamente reservado a administradores del sistema.
    Garantiza inmutabilidad (sin acciones de edición o borrado en la interfaz).
    """
    if not es_administrador(request.user):
        raise PermissionDenied("No tienes autorización para consultar la bitácora de auditoría institucional.")

    logs_qs = Auditoria.objects.select_related('usuario').order_by('-fecha')

    # Filtros
    modulo_filtro = request.GET.get('modulo', '').strip()
    if modulo_filtro:
        logs_qs = logs_qs.filter(modulo__iexact=modulo_filtro)

    accion_filtro = request.GET.get('accion', '').strip()
    if accion_filtro:
        logs_qs = logs_qs.filter(accion__icontains=accion_filtro)

    usuario_filtro = request.GET.get('usuario', '').strip()
    if usuario_filtro:
        logs_qs = logs_qs.filter(
            Q(usuario__username__icontains=usuario_filtro) |
            Q(usuario__nombres__icontains=usuario_filtro) |
            Q(usuario__apellidos__icontains=usuario_filtro)
        )

    fecha_desde = request.GET.get('fecha_desde', '').strip()
    if fecha_desde:
        logs_qs = logs_qs.filter(fecha__date__gte=fecha_desde)

    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    if fecha_hasta:
        logs_qs = logs_qs.filter(fecha__date__lte=fecha_hasta)

    q = request.GET.get('q', '').strip()
    if q:
        logs_qs = logs_qs.filter(
            Q(registro_afectado__icontains=q) |
            Q(accion__icontains=q) |
            Q(ip__icontains=q)
        )

    # Auditoría de consulta (solo al abrir o buscar, sin saturar paginación)
    page_req = request.GET.get('page')
    if not page_req or page_req == '1':
        Auditoria.objects.create(
            usuario=request.user,
            accion='CONSULTA_AUDITORIA',
            modulo='AUDITORIA',
            registro_afectado=f"Consulta de bitácora ({logs_qs.count()} registros coincidentes)",
            ip=get_client_ip(request)
        )

    # Paginación segura (25 registros por página)
    paginator = Paginator(logs_qs, 25)
    page_obj = paginator.get_page(page_req)

    # Lista de módulos registrados en la bitácora para el filtro desplegable
    modulos = Auditoria.objects.values_list('modulo', flat=True).distinct().order_by('modulo')

    return render(request, 'auditoria/consulta.html', {
        'page_obj': page_obj,
        'modulos': modulos,
        'filtro_modulo': modulo_filtro,
        'filtro_accion': accion_filtro,
        'filtro_usuario': usuario_filtro,
        'filtro_fecha_desde': fecha_desde,
        'filtro_fecha_hasta': fecha_hasta,
        'filtro_q': q,
        'total_registros': paginator.count,
    })
