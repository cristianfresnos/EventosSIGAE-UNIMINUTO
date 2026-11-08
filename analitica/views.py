"""
Vistas para el módulo de Analítica y Dashboard Institucional.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone

from auditoria.models import Auditoria
from .forms import FiltroDashboardForm
from .services import (
    puede_ver_dashboard,
    tiene_alcance_global,
    obtener_eventos_permitidos,
    filtrar_eventos,
    calcular_metricas_dashboard,
    exportar_csv_analitica,
    exportar_excel_analitica,
)


def get_client_ip(request):
    """
    Obtiene la dirección IP real del cliente considerando posibles proxies intermedios.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@login_required
def dashboard(request):
    """
    Vista principal del Dashboard Analítico e Indicadores Institucionales.
    Aplica controles de seguridad y filtrado según el alcance del usuario.
    """
    if not puede_ver_dashboard(request.user):
        raise PermissionDenied("No tienes permisos para acceder al dashboard analítico institucional.")

    eventos_permitidos = obtener_eventos_permitidos(request.user)

    # Validación de seguridad: un organizador no puede forzar la consulta de un evento ajeno
    evento_param = request.GET.get('evento')
    if evento_param:
        try:
            evento_id = int(evento_param)
            if not eventos_permitidos.filter(pk=evento_id).exists():
                raise PermissionDenied("No tienes autorización para consultar las métricas de este evento.")
        except (ValueError, TypeError):
            pass

    # Inicializar y procesar formulario de filtros
    form = FiltroDashboardForm(request.GET or None, eventos_permitidos=eventos_permitidos)
    filtros = {}
    if form.is_valid():
        filtros = {k: v for k, v in form.cleaned_data.items() if v}

    # Filtrar el conjunto de eventos permitidos
    eventos_filtrados = filtrar_eventos(eventos_permitidos, filtros)

    # Calcular indicadores institucionales y datos de visualizaciones
    metricas = calcular_metricas_dashboard(eventos_filtrados)

    # Empaquetar series de datos para gráficas interactivas en formato JSON seguro
    graficas_json = json.dumps({
        'meses': metricas['grafica_meses'],
        'eventos': metricas['grafica_eventos'],
        'categoria': metricas['grafica_categoria'],
        'modalidad': metricas['grafica_modalidad'],
        'franjas': metricas['grafica_franjas'],
        'metodos': metricas['grafica_metodos'],
    })

    # Registro de auditoría institucional
    Auditoria.objects.create(
        usuario=request.user,
        accion='CONSULTA_DASHBOARD',
        modulo='ANALITICA',
        registro_afectado=f"Filtro aplicado ({metricas['total_eventos']} eventos analizados)",
        ip=get_client_ip(request)
    )

    context = {
        'form': form,
        'metricas': metricas,
        'graficas_json': graficas_json,
        'tiene_alcance_global': tiene_alcance_global(request.user),
        'total_eventos_permitidos': eventos_permitidos.count(),
        'querystring': request.GET.urlencode(),
    }
    return render(request, 'analitica/dashboard.html', context)


@login_required
def exportar_csv(request):
    """
    Exporta el reporte consolidado de analítica e inscripciones en formato CSV
    respetando los filtros activos y las políticas de seguridad del usuario.
    """
    if not puede_ver_dashboard(request.user):
        raise PermissionDenied("No tienes permisos para exportar datos analíticos.")

    eventos_permitidos = obtener_eventos_permitidos(request.user)

    evento_param = request.GET.get('evento')
    if evento_param:
        try:
            evento_id = int(evento_param)
            if not eventos_permitidos.filter(pk=evento_id).exists():
                raise PermissionDenied("No tienes autorización para exportar datos de este evento.")
        except (ValueError, TypeError):
            pass

    form = FiltroDashboardForm(request.GET or None, eventos_permitidos=eventos_permitidos)
    filtros = {}
    if form.is_valid():
        filtros = {k: v for k, v in form.cleaned_data.items() if v}

    eventos_filtrados = filtrar_eventos(eventos_permitidos, filtros)
    csv_bytes = exportar_csv_analitica(eventos_filtrados, usuario=request.user)

    # Registro de auditoría de exportación
    Auditoria.objects.create(
        usuario=request.user,
        accion='EXPORTACION_CSV_ANALITICA',
        modulo='ANALITICA',
        registro_afectado=f"{eventos_filtrados.count()} eventos exportados",
        ip=get_client_ip(request)
    )

    timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_analitica_sigae_{timestamp_str}.csv"

    response = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def exportar_excel(request):
    """
    Exporta el reporte analítico institucional en formato Excel (.xlsx) nativo
    respetando los filtros activos y las políticas de autorización del usuario (RF-20).
    """
    if not puede_ver_dashboard(request.user):
        raise PermissionDenied("No tienes permisos para exportar datos analíticos.")

    eventos_permitidos = obtener_eventos_permitidos(request.user)

    evento_param = request.GET.get('evento')
    if evento_param:
        try:
            evento_id = int(evento_param)
            if not eventos_permitidos.filter(pk=evento_id).exists():
                raise PermissionDenied("No tienes autorización para exportar datos de este evento.")
        except (ValueError, TypeError):
            pass

    form = FiltroDashboardForm(request.GET or None, eventos_permitidos=eventos_permitidos)
    filtros = {}
    if form.is_valid():
        filtros = {k: v for k, v in form.cleaned_data.items() if v}

    eventos_filtrados = filtrar_eventos(eventos_permitidos, filtros)
    excel_bytes = exportar_excel_analitica(eventos_filtrados, usuario=request.user)

    # Registro de auditoría institucional
    Auditoria.objects.create(
        usuario=request.user,
        accion='EXPORTACION_EXCEL_ANALITICA',
        modulo='ANALITICA',
        registro_afectado=f"{eventos_filtrados.count()} eventos exportados en formato Excel XLSX",
        ip=get_client_ip(request)
    )

    timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_analitica_sigae_{timestamp_str}.xlsx"

    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

