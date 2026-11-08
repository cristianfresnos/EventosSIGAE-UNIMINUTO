"""
Vistas de generación y descarga de reportes PDF para EventosSIGAE-UNIMINUTO.
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify

from eventos.models import Evento
from auditoria.models import Auditoria
from . import services


def get_client_ip(request):
    """
    Obtiene la dirección IP real del cliente considerando proxies.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def tiene_permiso_evento(user, evento):
    """
    Verifica si el usuario tiene autorización para descargar documentos del evento:
    1. Superusuarios y staff de administración.
    2. El usuario organizador responsable del evento.
    3. Usuarios con roles institucionales de gestión (Administrador, Coordinador, Docente).
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if evento.organizador_id == user.id:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Administrador', 'Coordinador', 'Docente']:
        return True
    return False


@login_required
def descargar_planilla_asistencia_pdf(request, id_evento):
    """
    Genera y descarga bajo demanda la Planilla de Asistencia Imprimible (PDF).
    Registra auditoría tras la generación exitosa.
    """
    evento = get_object_or_404(Evento, pk=id_evento)

    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No cuenta con permisos para descargar la planilla de este evento.")

    # 1. Obtención de datos y generación en memoria
    datos_planilla = services.obtener_datos_planilla_imprimible(evento.pk)
    pdf_bytes = services.generar_pdf_planilla_asistencia(datos_planilla)

    # 2. Registro de auditoría institucional (únicamente tras generación exitosa)
    Auditoria.objects.create(
        usuario=request.user,
        accion='DESCARGAR_PLANILLA_PDF',
        modulo='REPORTES',
        registro_afectado=f"Evento ID {evento.pk} - {evento.nombre}",
        ip=get_client_ip(request)
    )

    # 3. Retorno de respuesta binaria PDF
    slug_nombre = slugify(evento.nombre)[:30] or f"evento_{evento.pk}"
    fecha_str = evento.fecha.strftime("%Y%m%d") if evento.fecha else "sin_fecha"
    filename = f"Planilla_Asistencia_{slug_nombre}_{fecha_str}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def descargar_reporte_consolidado_pdf(request, id_evento):
    """
    Genera y descarga bajo demanda el Reporte Consolidado del Evento (PDF).
    Registra auditoría tras la generación exitosa.
    """
    evento = get_object_or_404(Evento, pk=id_evento)

    if not tiene_permiso_evento(request.user, evento):
        raise PermissionDenied("No cuenta con permisos para descargar el reporte de este evento.")

    # 1. Obtención de datos y generación en memoria
    datos_reporte = services.obtener_reporte_consolidado_evento(evento.pk)
    pdf_bytes = services.generar_pdf_reporte_consolidado(datos_reporte, usuario_generador=request.user)

    # 2. Registro de auditoría institucional (únicamente tras generación exitosa)
    Auditoria.objects.create(
        usuario=request.user,
        accion='DESCARGAR_REPORTE_PDF',
        modulo='REPORTES',
        registro_afectado=f"Evento ID {evento.pk} - {evento.nombre}",
        ip=get_client_ip(request)
    )

    # 3. Retorno de respuesta binaria PDF
    slug_nombre = slugify(evento.nombre)[:30] or f"evento_{evento.pk}"
    fecha_str = evento.fecha.strftime("%Y%m%d") if evento.fecha else "sin_fecha"
    filename = f"Reporte_Consolidado_{slug_nombre}_{fecha_str}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
