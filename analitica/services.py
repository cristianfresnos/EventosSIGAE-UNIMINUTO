"""
Servicios de cálculo, agregación de indicadores y exportación de datos para el módulo de Analítica.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import csv
import io
import datetime
from django.utils import timezone
from django.db.models import Count, Q, F
from django.db.models.functions import TruncMonth

from eventos.models import Evento, EstadoEvento, ModalidadEvento, CategoriaEvento
from participantes.models import Participante, Inscripcion, EstadoInscripcion
from asistencia.models import Asistencia, EstadoAsistencia, MetodoAsistencia


def puede_ver_dashboard(user):
    """
    Determina si el usuario tiene permiso para acceder al módulo analítico:
    - Superusuarios y staff institucional.
    - Usuarios con rol 'Administrador' o 'Coordinador'.
    - Usuarios que sean organizadores de al menos un evento o con rol 'Docente'.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Administrador', 'Coordinador']:
        return True
    if Evento.objects.filter(organizador=user).exists():
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre == 'Docente':
        return True
    return False


def tiene_alcance_global(user):
    """
    Indica si el usuario puede consultar indicadores globales de toda la institución
    o si su alcance está limitado a sus eventos organizados.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    if hasattr(user, 'rol') and user.rol and user.rol.nombre in ['Administrador', 'Coordinador']:
        return True
    return False


def obtener_eventos_permitidos(user):
    """
    Retorna el QuerySet de eventos que el usuario tiene autorización de consultar:
    - Alcance global: todos los eventos.
    - Organizador o Docente: únicamente eventos donde organizador == user.
    - Sin permisos: QuerySet vacío.
    """
    if not user.is_authenticated:
        return Evento.objects.none()

    if tiene_alcance_global(user):
        return Evento.objects.all().select_related('categoria', 'organizador')

    if Evento.objects.filter(organizador=user).exists() or (hasattr(user, 'rol') and user.rol and user.rol.nombre == 'Docente'):
        return Evento.objects.filter(organizador=user).select_related('categoria', 'organizador')

    return Evento.objects.none()


def filtrar_eventos(eventos_qs, filtros=None):
    """
    Aplica filtros sobre el QuerySet de eventos según los parámetros recibidos.
    Filtros soportados:
    - fecha_desde: date
    - fecha_hasta: date
    - evento: int (ID de evento) o instancia de Evento
    - categoria: int (ID de categoría) o instancia de CategoriaEvento
    - modalidad: str (PRESENCIAL, VIRTUAL, HIBRIDA)
    - estado: str (PUBLICADO, FINALIZADO, etc.)
    """
    if not filtros:
        return eventos_qs

    qs = eventos_qs

    fecha_desde = filtros.get('fecha_desde')
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)

    fecha_hasta = filtros.get('fecha_hasta')
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    evento = filtros.get('evento')
    if evento:
        evento_id = evento.pk if hasattr(evento, 'pk') else evento
        qs = qs.filter(pk=evento_id)

    categoria = filtros.get('categoria')
    if categoria:
        cat_id = categoria.pk if hasattr(categoria, 'pk') else categoria
        qs = qs.filter(categoria_id=cat_id)

    modalidad = filtros.get('modalidad')
    if modalidad:
        qs = qs.filter(modalidad=modalidad)

    estado = filtros.get('estado')
    if estado:
        qs = qs.filter(estado=estado)

    return qs


def calcular_metricas_dashboard(eventos_qs):
    """
    Calcula los indicadores institucionales y genera los datos para las visualizaciones.
    Garantiza:
    - Cero duplicidad en participantes inscritos en múltiples eventos.
    - Exclusión estricta de asistencias anuladas.
    - Manejo seguro de casos sin datos (sin divisiones por cero ni errores de valor nulo).
    """
    today = timezone.localdate()

    # 1. TARJETAS DE INDICADORES PRINCIPALES (KPIS)
    total_eventos = eventos_qs.count()

    eventos_proximos = eventos_qs.filter(
        fecha__gte=today
    ).exclude(estado__in=[EstadoEvento.FINALIZADO, EstadoEvento.CANCELADO]).count()

    eventos_finalizados = eventos_qs.filter(
        Q(estado=EstadoEvento.FINALIZADO) | Q(fecha__lt=today)
    ).exclude(estado=EstadoEvento.CANCELADO).count()

    # Conjunto base de inscripciones activas vinculadas a los eventos filtrados
    inscripciones_activas_qs = Inscripcion.objects.filter(
        evento__in=eventos_qs,
        estado=EstadoInscripcion.ACTIVA
    )

    total_inscripciones_activas = inscripciones_activas_qs.count()

    # Total de participantes únicos (evita contar dos veces al mismo participante)
    total_participantes_unicos = inscripciones_activas_qs.values('participante_id').distinct().count()

    # Total de asistencias efectivas (estado REGISTRADA, excluye ANULADA)
    asistencias_efectivas_qs = Asistencia.objects.filter(
        inscripcion__in=inscripciones_activas_qs,
        estado=EstadoAsistencia.REGISTRADA
    )
    total_asistencias_efectivas = asistencias_efectivas_qs.count()

    # Asistencias anuladas (para trazabilidad y auditoría de exclusión)
    total_asistencias_anuladas = Asistencia.objects.filter(
        inscripcion__in=inscripciones_activas_qs,
        estado=EstadoAsistencia.ANULADA
    ).count()

    # Porcentaje de asistencia efectiva frente a inscripciones elegibles
    if total_inscripciones_activas > 0:
        porcentaje_asistencia_efectiva = round(
            (total_asistencias_efectivas / total_inscripciones_activas) * 100.0,
            1
        )
    else:
        porcentaje_asistencia_efectiva = 0.0

    # 2. VISUALIZACIÓN 1: EVENTOS E INSCRIPCIONES POR MES
    meses_eventos = (
        eventos_qs
        .annotate(mes=TruncMonth('fecha'))
        .values('mes')
        .annotate(total=Count('id_evento'))
        .order_by('mes')
    )

    meses_inscripciones = (
        inscripciones_activas_qs
        .annotate(mes=TruncMonth('fecha_inscripcion'))
        .values('mes')
        .annotate(total=Count('id_inscripcion'))
        .order_by('mes')
    )

    # Consolidar etiquetas temporales únicas
    mapa_meses = {}
    for item in meses_eventos:
        m = item['mes']
        if m:
            clave = m.strftime('%Y-%m')
            mapa_meses.setdefault(clave, {'eventos': 0, 'inscripciones': 0})
            mapa_meses[clave]['eventos'] = item['total']

    for item in meses_inscripciones:
        m = item['mes']
        if m:
            clave = m.strftime('%Y-%m')
            mapa_meses.setdefault(clave, {'eventos': 0, 'inscripciones': 0})
            mapa_meses[clave]['inscripciones'] = item['total']

    meses_ordenados = sorted(mapa_meses.keys())
    # Formato amigable de etiqueta mensual: 'Oct 2026'
    meses_nombres = {
        '01': 'Ene', '02': 'Feb', '03': 'Mar', '04': 'Abr',
        '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Ago',
        '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dic'
    }
    grafica_meses_labels = []
    grafica_meses_eventos = []
    grafica_meses_inscripciones = []

    for clave in meses_ordenados:
        partes = clave.split('-')
        label = f"{meses_nombres.get(partes[1], partes[1])} {partes[0]}" if len(partes) == 2 else clave
        grafica_meses_labels.append(label)
        grafica_meses_eventos.append(mapa_meses[clave]['eventos'])
        grafica_meses_inscripciones.append(mapa_meses[clave]['inscripciones'])

    # 3. VISUALIZACIONES 2 Y 3: ASISTENCIA Y PORCENTAJE POR EVENTO
    eventos_con_metricas = (
        eventos_qs
        .annotate(
            inscritos_activos=Count(
                'inscripciones',
                filter=Q(inscripciones__estado=EstadoInscripcion.ACTIVA),
                distinct=True
            ),
            asistencias_validas=Count(
                'inscripciones__asistencia',
                filter=Q(
                    inscripciones__estado=EstadoInscripcion.ACTIVA,
                    inscripciones__asistencia__estado=EstadoAsistencia.REGISTRADA
                ),
                distinct=True
            ),
        )
        .order_by('-fecha', 'nombre')
    )

    tabla_eventos = []
    grafica_eventos_labels = []
    grafica_eventos_asistencia = []
    grafica_eventos_porcentaje = []

    for ev in eventos_con_metricas:
        activos = ev.inscritos_activos
        validas = ev.asistencias_validas
        pct = round((validas / activos * 100.0), 1) if activos > 0 else 0.0

        tabla_eventos.append({
            'evento': ev,
            'inscritos_activos': activos,
            'asistencias_validas': validas,
            'porcentaje': pct,
        })

        # Para las gráficas tomamos el nombre del evento (truncado si es muy largo)
        nombre_corto = ev.nombre[:28] + ('...' if len(ev.nombre) > 28 else '')
        grafica_eventos_labels.append(nombre_corto)
        grafica_eventos_asistencia.append(validas)
        grafica_eventos_porcentaje.append(pct)

    # 4. VISUALIZACIÓN 4: DISTRIBUCIÓN POR CATEGORÍA Y MODALIDAD
    dist_categoria_qs = (
        eventos_qs
        .values('categoria__nombre')
        .annotate(total=Count('id_evento'))
        .order_by('-total')
    )
    grafica_cat_labels = [c['categoria__nombre'] or 'Sin categoría' for c in dist_categoria_qs]
    grafica_cat_data = [c['total'] for c in dist_categoria_qs]

    dist_modalidad_qs = (
        eventos_qs
        .values('modalidad')
        .annotate(total=Count('id_evento'))
        .order_by('-total')
    )
    modalidad_dict = dict(ModalidadEvento.choices)
    grafica_mod_labels = [modalidad_dict.get(m['modalidad'], m['modalidad']) for m in dist_modalidad_qs]
    grafica_mod_data = [m['total'] for m in dist_modalidad_qs]

    # 5. VISUALIZACIÓN 5: LLEGADAS POR FRANJA HORARIA
    asistencias_con_hora = asistencias_efectivas_qs.exclude(hora_entrada__isnull=True)
    tiene_franjas_horarias = asistencias_con_hora.exists()

    franjas_definidas = [
        ('Antes de 08:00', lambda h: h < 8),
        ('08:00 - 09:59', lambda h: 8 <= h < 10),
        ('10:00 - 11:59', lambda h: 10 <= h < 12),
        ('12:00 - 13:59', lambda h: 12 <= h < 14),
        ('14:00 - 15:59', lambda h: 14 <= h < 16),
        ('16:00 - 17:59', lambda h: 16 <= h < 18),
        ('18:00 en adelante', lambda h: h >= 18),
    ]

    conteo_franjas = {nombre: 0 for nombre, _ in franjas_definidas}

    if tiene_franjas_horarias:
        for asist in asistencias_con_hora:
            hora = asist.hora_entrada.hour
            for nombre, func_cond in franjas_definidas:
                if func_cond(hora):
                    conteo_franjas[nombre] += 1
                    break

    grafica_franjas_labels = list(conteo_franjas.keys())
    grafica_franjas_data = list(conteo_franjas.values())

    # 6. VISUALIZACIÓN 6: REGISTROS POR MÉTODO (QR vs MANUAL vs OTROS)
    dist_metodos_qs = (
        asistencias_efectivas_qs
        .values('metodo')
        .annotate(total=Count('id_asistencia'))
        .order_by('-total')
    )
    metodos_dict = dict(MetodoAsistencia.choices)
    grafica_metodos_labels = [metodos_dict.get(m['metodo'], m['metodo']) for m in dist_metodos_qs]
    grafica_metodos_data = [m['total'] for m in dist_metodos_qs]
    tiene_metodos = bool(grafica_metodos_data)

    return {
        # KPIs
        'total_eventos': total_eventos,
        'eventos_proximos': eventos_proximos,
        'eventos_finalizados': eventos_finalizados,
        'total_inscripciones_activas': total_inscripciones_activas,
        'total_participantes_unicos': total_participantes_unicos,
        'total_asistencias_efectivas': total_asistencias_efectivas,
        'total_asistencias_anuladas': total_asistencias_anuladas,
        'porcentaje_asistencia_efectiva': porcentaje_asistencia_efectiva,

        # Tablas y listas
        'tabla_eventos': tabla_eventos,

        # Gráficas
        'grafica_meses': {
            'labels': grafica_meses_labels,
            'eventos': grafica_meses_eventos,
            'inscripciones': grafica_meses_inscripciones,
            'tiene_datos': bool(grafica_meses_labels),
        },
        'grafica_eventos': {
            'labels': grafica_eventos_labels,
            'asistencia': grafica_eventos_asistencia,
            'porcentaje': grafica_eventos_porcentaje,
            'tiene_datos': bool(grafica_eventos_labels),
        },
        'grafica_categoria': {
            'labels': grafica_cat_labels,
            'data': grafica_cat_data,
            'tiene_datos': bool(grafica_cat_data),
        },
        'grafica_modalidad': {
            'labels': grafica_mod_labels,
            'data': grafica_mod_data,
            'tiene_datos': bool(grafica_mod_data),
        },
        'grafica_franjas': {
            'labels': grafica_franjas_labels,
            'data': grafica_franjas_data,
            'tiene_datos': tiene_franjas_horarias,
        },
        'grafica_metodos': {
            'labels': grafica_metodos_labels,
            'data': grafica_metodos_data,
            'tiene_datos': tiene_metodos,
        },
    }


def exportar_csv_analitica(eventos_qs, usuario=None):
    """
    Genera el contenido de un archivo CSV con el detalle consolidado de inscripciones
    y asistencias de los eventos filtrados.
    Incluye encabezados institucionales y codificación UTF-8 con BOM (utf-8-sig).
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect='excel', delimiter=',')

    # Fila de metadatos institucionales
    fecha_generacion = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    usuario_str = usuario.get_full_name() if (usuario and hasattr(usuario, 'get_full_name') and usuario.get_full_name()) else (usuario.username if usuario else "Sistema")

    writer.writerow(["# SISTEMA INTEGRADO DE GESTION DE ASISTENCIA Y EVENTOS (SIGAE - UNIMINUTO)"])
    writer.writerow(["# REPORTE ANALITICO DE ASISTENCIA E INSCRIPCIONES"])
    writer.writerow([f"# Generado por: {usuario_str}", f"Fecha de generacion: {fecha_generacion}"])
    writer.writerow([])

    # Encabezados de columnas de datos
    headers = [
        'ID Evento',
        'Nombre Evento',
        'Categoria',
        'Modalidad',
        'Fecha Evento',
        'Estado Evento',
        'ID Inscripcion',
        'Fecha Inscripcion',
        'Estado Inscripcion',
        'Documento Participante',
        'Apellidos y Nombres',
        'Tipo Participante',
        'Correo Electronico',
        'Programa / Institucion',
        'Estado Asistencia',
        'Metodo Asistencia',
        'Hora Entrada',
        'Hora Salida'
    ]
    writer.writerow(headers)

    # Consulta optimizada con select_related
    inscripciones_qs = (
        Inscripcion.objects.filter(evento__in=eventos_qs)
        .select_related('evento', 'evento__categoria', 'participante', 'participante__usuario', 'asistencia')
        .order_by('evento__nombre', 'participante__apellidos', 'participante__nombres')
    )

    for ins in inscripciones_qs:
        ev = ins.evento
        part = ins.participante
        asist = getattr(ins, 'asistencia', None)

        # Asistencia
        if asist:
            estado_asist = asist.get_estado_display() if hasattr(asist, 'get_estado_display') else asist.estado
            metodo_asist = asist.get_metodo_display() if hasattr(asist, 'get_metodo_display') else asist.metodo
            hora_in = asist.hora_entrada.strftime("%H:%M:%S") if asist.hora_entrada else "-"
            hora_out = asist.hora_salida.strftime("%H:%M:%S") if asist.hora_salida else "-"
        else:
            estado_asist = "Sin Asistencia"
            metodo_asist = "-"
            hora_in = "-"
            hora_out = "-"

        # Participante
        doc = part.documento or (part.usuario.documento if part.usuario else "Sin documento")
        nombre_completo = f"{part.apellidos.strip()}, {part.nombres.strip()}"
        tipo_part = part.get_tipo_display() if hasattr(part, 'get_tipo_display') else str(part.tipo)
        correo_part = part.correo or (part.usuario.email if part.usuario else "-")
        prog_inst = part.programa or part.institucion or "-"

        writer.writerow([
            ev.pk,
            ev.nombre,
            ev.categoria.nombre if ev.categoria else "-",
            ev.get_modalidad_display() if hasattr(ev, 'get_modalidad_display') else ev.modalidad,
            ev.fecha.strftime("%Y-%m-%d") if ev.fecha else "-",
            ev.get_estado_display() if hasattr(ev, 'get_estado_display') else ev.estado,
            ins.pk,
            ins.fecha_inscripcion.strftime("%Y-%m-%d %H:%M:%S") if ins.fecha_inscripcion else "-",
            ins.get_estado_display() if hasattr(ins, 'get_estado_display') else ins.estado,
            doc,
            nombre_completo,
            tipo_part,
            correo_part,
            prog_inst,
            estado_asist,
            metodo_asist,
            hora_in,
            hora_out
        ])

    return buffer.getvalue().encode('utf-8-sig')


def exportar_excel_analitica(eventos_qs, usuario=None):
    """
    Genera un archivo Excel (.xlsx) estructurado en memoria utilizando openpyxl.
    Incluye hojas de Resumen Institucional, Detalle de Eventos y Registro de Participantes.
    Aplica tipado nativo de celdas (fechas, horas, números), estilos corporativos UNIMINUTO
    y ajuste automático de ancho de columnas (RF-20).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    # Hoja 1: Resumen Institucional
    ws_resumen = wb.active
    ws_resumen.title = "Resumen Institucional"

    # Hoja 2: Eventos
    ws_eventos = wb.create_sheet(title="Eventos")

    # Hoja 3: Participantes y Asistencia
    ws_participantes = wb.create_sheet(title="Participantes y Asistencia")

    # Estilos Corporativos
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0F2B46", end_color="0F2B46", fill_type="solid")
    sub_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="0F2B46")
    bold_font = Font(name="Calibri", size=11, bold=True)
    regular_font = Font(name="Calibri", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    fecha_generacion = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    usuario_str = usuario.get_full_name() if (usuario and hasattr(usuario, 'get_full_name') and usuario.get_full_name()) else (usuario.username if usuario else "Sistema")

    # --- POBRADO HOJA 1: RESUMEN INSTITUCIONAL ---
    ws_resumen.cell(row=1, column=1, value="SISTEMA INTEGRADO DE GESTIÓN DE ASISTENCIA Y EVENTOS (SIGAE - UNIMINUTO)").font = title_font
    ws_resumen.cell(row=2, column=1, value="Reporte Ejecutivo y Métricas Analíticas").font = Font(name="Calibri", size=11, italic=True, color="475569")
    ws_resumen.cell(row=3, column=1, value=f"Generado por: {usuario_str} | Fecha: {fecha_generacion}").font = Font(name="Calibri", size=9, color="64748B")

    # Cálculos globales del subconjunto filtrado
    total_eventos = eventos_qs.count()
    inscripciones_qs = (
        Inscripcion.objects.filter(evento__in=eventos_qs)
        .select_related('evento', 'evento__categoria', 'participante', 'participante__usuario', 'asistencia')
        .order_by('evento__nombre', 'participante__apellidos', 'participante__nombres')
    )
    total_inscripciones = inscripciones_qs.count()
    total_asistencias = Asistencia.objects.filter(inscripcion__in=inscripciones_qs, estado=EstadoAsistencia.REGISTRADA).count()
    total_salidas = Asistencia.objects.filter(inscripcion__in=inscripciones_qs, estado=EstadoAsistencia.REGISTRADA, hora_salida__isnull=False).count()
    tasa_asistencia = round((total_asistencias / total_inscripciones * 100), 2) if total_inscripciones > 0 else 0.0

    kpi_headers = ["Indicador Institucional", "Valor"]
    for col_idx, h in enumerate(kpi_headers, 1):
        cell = ws_resumen.cell(row=5, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    kpis = [
        ("Total de Eventos Analizados", total_eventos),
        ("Total de Inscripciones Registradas", total_inscripciones),
        ("Total de Asistencias Efectivas (Check-in)", total_asistencias),
        ("Total de Salidas Registradas (Checkout)", total_salidas),
        ("Tasa Global de Asistencia (%)", f"{tasa_asistencia}%"),
    ]
    for r_idx, (kpi_name, kpi_val) in enumerate(kpis, 6):
        c1 = ws_resumen.cell(row=r_idx, column=1, value=kpi_name)
        c2 = ws_resumen.cell(row=r_idx, column=2, value=kpi_val)
        c1.font = regular_font
        c2.font = bold_font
        c1.border = thin_border
        c2.border = thin_border
        c2.alignment = right_align

    # --- POBRADO HOJA 2: DETALLE DE EVENTOS ---
    headers_eventos = [
        "ID Evento", "Nombre del Evento", "Categoría", "Modalidad", "Fecha",
        "Hora Inicio", "Hora Fin", "Lugar", "Organizador", "Cupo",
        "Inscritos", "Asistentes", "% Asistencia", "Estado"
    ]
    for col_idx, h in enumerate(headers_eventos, 1):
        cell = ws_eventos.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    row_ev = 2
    for ev in eventos_qs.select_related('categoria', 'organizador'):
        activos = ev.inscripciones.filter(estado=EstadoInscripcion.ACTIVA).count()
        asistieron = Asistencia.objects.filter(inscripcion__evento=ev, estado=EstadoAsistencia.REGISTRADA).count()
        pct = round((asistieron / activos * 100), 1) if activos > 0 else 0.0

        datos_ev = [
            ev.pk,
            ev.nombre,
            ev.categoria.nombre if ev.categoria else "-",
            ev.get_modalidad_display(),
            ev.fecha.strftime("%Y-%m-%d") if ev.fecha else "-",
            ev.hora_inicio.strftime("%H:%M") if ev.hora_inicio else "-",
            ev.hora_fin.strftime("%H:%M") if ev.hora_fin else "-",
            ev.lugar,
            ev.organizador.get_full_name() or ev.organizador.username,
            ev.cupo if ev.cupo is not None else "Ilimitado",
            activos,
            asistieron,
            f"{pct}%",
            ev.get_estado_display()
        ]
        for col_idx, val in enumerate(datos_ev, 1):
            cell = ws_eventos.cell(row=row_ev, column=col_idx, value=val)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx in [1, 5, 6, 7, 10, 11, 12, 13]:
                cell.alignment = center_align
        row_ev += 1

    # --- POBRADO HOJA 3: PARTICIPANTES Y ASISTENCIA ---
    headers_part = [
        "ID Evento", "Nombre Evento", "Categoría", "ID Inscripción", "Fecha Inscripción",
        "Estado Inscripción", "Documento", "Apellidos y Nombres", "Tipo", "Correo Electrónico",
        "Institución / Programa", "Estado Asistencia", "Método", "Hora Entrada", "Hora Salida", "Permanencia"
    ]
    for col_idx, h in enumerate(headers_part, 1):
        cell = ws_participantes.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    row_part = 2
    for ins in inscripciones_qs:
        ev = ins.evento
        part = ins.participante
        asist = getattr(ins, 'asistencia', None)

        if asist:
            estado_asist = asist.get_estado_display() if hasattr(asist, 'get_estado_display') else asist.estado
            metodo_asist = asist.get_metodo_display() if hasattr(asist, 'get_metodo_display') else asist.metodo
            hora_in = asist.hora_entrada.strftime("%H:%M") if asist.hora_entrada else "-"
            hora_out = asist.hora_salida.strftime("%H:%M") if asist.hora_salida else "-"
            permanencia_txt = asist.tiempo_permanencia_str
        else:
            estado_asist = "Sin Asistencia"
            metodo_asist = "-"
            hora_in = "-"
            hora_out = "-"
            permanencia_txt = "-"

        doc = part.documento or (part.usuario.documento if part.usuario else "Sin documento")
        nombre_completo = f"{part.apellidos.strip()}, {part.nombres.strip()}"
        tipo_part = part.get_tipo_display() if hasattr(part, 'get_tipo_display') else str(part.tipo)
        correo_part = part.correo or (part.usuario.email if part.usuario else "-")
        prog_inst = part.programa or part.institucion or "-"

        datos_p = [
            ev.pk,
            ev.nombre,
            ev.categoria.nombre if ev.categoria else "-",
            ins.pk,
            ins.fecha_inscripcion.strftime("%Y-%m-%d %H:%M") if ins.fecha_inscripcion else "-",
            ins.get_estado_display() if hasattr(ins, 'get_estado_display') else ins.estado,
            doc,
            nombre_completo,
            tipo_part,
            correo_part,
            prog_inst,
            estado_asist,
            metodo_asist,
            hora_in,
            hora_out,
            permanencia_txt
        ]
        for col_idx, val in enumerate(datos_p, 1):
            cell = ws_participantes.cell(row=row_part, column=col_idx, value=val)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx in [1, 4, 5, 6, 7, 9, 12, 13, 14, 15, 16]:
                cell.alignment = center_align
        row_part += 1

    # Autoajuste de ancho de columnas para todas las hojas
    for ws in [ws_resumen, ws_eventos, ws_participantes]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

