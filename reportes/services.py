"""
Servicios de consultas y generación de documentos PDF para el módulo de Reportes.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import io
import datetime
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from eventos.models import Evento, EstadoEvento
from participantes.models import Participante, Inscripcion, EstadoInscripcion
from asistencia.models import Asistencia, EstadoAsistencia


# ==============================================================================
# CANVASES PERSONALIZADOS PARA NUMERACIÓN Y ENCABEZADOS/PIES DE PÁGINA
# ==============================================================================

class NumberedCanvasLandscape(canvas.Canvas):
    """
    Canvas de doble pasada para calcular el número total de páginas en formato apaisado.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        page_w, page_h = self._pagesize
        # Línea divisoria superior del pie
        self.setStrokeColor(colors.HexColor("#D0D5DD"))
        self.setLineWidth(0.5)
        self.line(30, 28, page_w - 30, 28)
        # Textos de pie
        self.drawString(30, 16, "SIGAE — UNIMINUTO | Sistema Integrado de Gestión de Asistencia y Eventos")
        texto_pag = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(page_w - 30, 16, texto_pag)
        self.restoreState()


class NumberedCanvasPortrait(canvas.Canvas):
    """
    Canvas de doble pasada para calcular el número total de páginas en formato vertical.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        page_w, page_h = self._pagesize
        # Línea divisoria superior del pie
        self.setStrokeColor(colors.HexColor("#D0D5DD"))
        self.setLineWidth(0.5)
        self.line(36, 28, page_w - 36, 28)
        # Textos de pie
        self.drawString(36, 16, "SIGAE — UNIMINUTO | Reporte Oficial Generado Automáticamente")
        texto_pag = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(page_w - 36, 16, texto_pag)
        self.restoreState()


# ==============================================================================
# SERVICIOS DE CONSULTA DE DATOS (ORM OPTIMIZADO)
# ==============================================================================

def obtener_datos_planilla_imprimible(id_evento):
    """
    Recupera los datos necesarios para construir la planilla de asistencia imprimible.
    Incluye únicamente participantes con inscripción ACTIVA, ordenados alfabéticamente.
    Soporta participantes institucionales y externos (usuario=NULL).
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    # Filtrar únicamente inscripciones activas (excluye canceladas)
    inscripciones_qs = (
        evento.inscripciones
        .filter(estado=EstadoInscripcion.ACTIVA)
        .select_related('participante', 'participante__usuario')
        .order_by('participante__apellidos', 'participante__nombres')
    )

    participantes_data = []
    for idx, ins in enumerate(inscripciones_qs, start=1):
        part = ins.participante
        nombre_completo = f"{part.apellidos.strip()}, {part.nombres.strip()}"
        doc = part.documento or (part.usuario.documento if part.usuario else "Sin documento")
        tipo = part.get_tipo_display() if hasattr(part, 'get_tipo_display') else str(part.tipo)

        # Determinar programa académico o institución de procedencia
        procedencia = []
        if part.programa:
            procedencia.append(part.programa)
        if part.institucion and part.institucion != 'Corporación Universitaria Minuto de Dios - UNIMINUTO':
            procedencia.append(part.institucion)
        elif not part.programa and part.institucion:
            procedencia.append(part.institucion)

        proc_str = " / ".join(procedencia) if procedencia else "-"

        participantes_data.append({
            'numero': idx,
            'documento': doc,
            'nombre_completo': nombre_completo,
            'tipo': tipo,
            'programa_institucion': proc_str,
            'id_inscripcion': ins.id_inscripcion,
        })

    return {
        'evento': evento,
        'participantes': participantes_data,
        'total_inscritos': len(participantes_data),
    }


def obtener_reporte_consolidado_evento(id_evento):
    """
    Recupera los datos completos del evento, sus indicadores de asistencia y el
    detalle discriminado de cada inscrito, diferenciando asistencias válidas,
    anuladas y ausencias de registro.
    """
    evento = get_object_or_404(
        Evento.objects.select_related('categoria', 'organizador'),
        pk=id_evento
    )

    # Recuperar inscripciones activas ordenadas alfabéticamente
    inscripciones_activas = list(
        evento.inscripciones
        .filter(estado=EstadoInscripcion.ACTIVA)
        .select_related('participante', 'participante__usuario', 'asistencia')
        .order_by('participante__apellidos', 'participante__nombres')
    )

    total_canceladas = evento.inscripciones.filter(estado=EstadoInscripcion.CANCELADA).count()

    # Evaluar si el evento ya concluyó o tiene control cerrado
    evento_cerrado = evento.estado in [EstadoEvento.FINALIZADO, EstadoEvento.CERRADO]

    participantes_detalle = []
    asistentes_validos = []
    sin_asistencia = []
    asistencias_anuladas = []

    for idx, ins in enumerate(inscripciones_activas, start=1):
        part = ins.participante
        asistencia_obj = getattr(ins, 'asistencia', None)

        tiene_asistencia_valida = (
            asistencia_obj is not None and asistencia_obj.es_valida
        )

        if tiene_asistencia_valida:
            asistentes_validos.append(ins)
            estado_asist_display = "Registrada"
            hora_in = asistencia_obj.hora_entrada.strftime("%H:%M") if asistencia_obj.hora_entrada else "-"
            hora_out = asistencia_obj.hora_salida.strftime("%H:%M") if asistencia_obj.hora_salida else "-"
            metodo = asistencia_obj.get_metodo_display() if hasattr(asistencia_obj, 'get_metodo_display') else str(asistencia_obj.metodo)
        elif asistencia_obj is not None and asistencia_obj.estado == EstadoAsistencia.ANULADA:
            asistencias_anuladas.append(ins)
            sin_asistencia.append(ins)
            estado_asist_display = "Anulada (No cuenta)"
            hora_in = "-"
            hora_out = "-"
            metodo = asistencia_obj.get_metodo_display() if hasattr(asistencia_obj, 'get_metodo_display') else str(asistencia_obj.metodo)
        else:
            sin_asistencia.append(ins)
            if evento_cerrado:
                estado_asist_display = "No asistió"
            else:
                estado_asist_display = "Sin registro (Evento abierto)"
            hora_in = "-"
            hora_out = "-"
            metodo = "-"

        participantes_detalle.append({
            'numero': idx,
            'documento': part.documento,
            'nombres': part.nombres,
            'apellidos': part.apellidos,
            'nombre_completo': f"{part.apellidos.strip()}, {part.nombres.strip()}",
            'tipo': part.get_tipo_display() if hasattr(part, 'get_tipo_display') else str(part.tipo),
            'programa_institucion': part.programa or part.institucion or "-",
            'estado_inscripcion': ins.get_estado_display() if hasattr(ins, 'get_estado_display') else ins.estado,
            'tiene_asistencia_valida': tiene_asistencia_valida,
            'estado_asistencia': estado_asist_display,
            'hora_entrada': hora_in,
            'hora_salida': hora_out,
            'metodo': metodo,
        })

    total_activos = len(inscripciones_activas)
    total_asistentes = len(asistentes_validos)
    total_sin_asist = len(sin_asistencia)
    porcentaje_asistencia = (total_asistentes / total_activos * 100.0) if total_activos > 0 else 0.0

    return {
        'evento': evento,
        'evento_cerrado': evento_cerrado,
        'participantes': participantes_detalle,
        'total_inscritos_activos': total_activos,
        'total_asistentes_validos': total_asistentes,
        'total_sin_asistencia_valida': total_sin_asist,
        'total_asistencias_anuladas': len(asistencias_anuladas),
        'total_canceladas': total_canceladas,
        'porcentaje_asistencia': round(porcentaje_asistencia, 1),
    }


# ==============================================================================
# GENERADORES DE DOCUMENTOS PDF (REPORTLAB)
# ==============================================================================

def generar_pdf_planilla_asistencia(datos):
    """
    Construye en memoria el archivo PDF de la Planilla de Asistencia Imprimible.
    Formato: Apaisado (Landscape Letter), preparado para diligenciamiento manual en campo.
    Incluye casillas para firma, verificación [ ] y filas en blanco para walk-ins.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
        topMargin=25,
        bottomMargin=35,
    )

    styles = getSampleStyleSheet()

    # Estilos tipográficos
    style_inst = ParagraphStyle(
        'InstTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=13,
        textColor=colors.HexColor('#0F2042'),
        alignment=1,  # Centrado
    )
    style_sub = ParagraphStyle(
        'InstSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#475467'),
        alignment=1,
    )
    style_doc_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=colors.HexColor('#0F2042'),
        alignment=1,
    )
    style_meta_label = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1D2939'),
    )
    style_meta_val = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#344054'),
    )
    style_th = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,
    )
    style_td = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1D2939'),
    )
    style_td_center = ParagraphStyle(
        'TableBodyCenter',
        parent=style_td,
        alignment=1,
    )
    style_instruction = ParagraphStyle(
        'Instruction',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor('#475467'),
    )

    story = []

    # 1. ENCABEZADO INSTITUCIONAL
    story.append(Paragraph("CORPORACIÓN UNIVERSITARIA MINUTO DE DIOS — UNIMINUTO", style_inst))
    story.append(Paragraph("SISTEMA INTEGRADO DE GESTIÓN DE ASISTENCIA Y EVENTOS (SIGAE)", style_sub))
    story.append(Spacer(1, 4))
    story.append(Paragraph("PLANILLA DE CONTROL Y REGISTRO DE ASISTENCIA", style_doc_title))
    story.append(Spacer(1, 8))

    # 2. FICHA TÉCNICA DEL EVENTO
    evento = datos['evento']
    organizador_str = evento.organizador.get_full_name() if hasattr(evento.organizador, 'get_full_name') else str(evento.organizador)
    fecha_str = evento.fecha.strftime("%d/%m/%Y") if evento.fecha else "Por definir"
    horario_str = f"{evento.hora_inicio.strftime('%H:%M')} - {evento.hora_fin.strftime('%H:%M')}" if evento.hora_inicio and evento.hora_fin else "Sin horario"

    tabla_meta_data = [
        [
            Paragraph("<b>Evento:</b>", style_meta_label),
            Paragraph(evento.nombre, style_meta_val),
            Paragraph("<b>Fecha:</b>", style_meta_label),
            Paragraph(fecha_str, style_meta_val),
            Paragraph("<b>Horario:</b>", style_meta_label),
            Paragraph(horario_str, style_meta_val),
        ],
        [
            Paragraph("<b>Lugar:</b>", style_meta_label),
            Paragraph(evento.lugar, style_meta_val),
            Paragraph("<b>Modalidad:</b>", style_meta_label),
            Paragraph(evento.get_modalidad_display() if hasattr(evento, 'get_modalidad_display') else evento.modalidad, style_meta_val),
            Paragraph("<b>Organizador:</b>", style_meta_label),
            Paragraph(organizador_str, style_meta_val),
        ]
    ]

    tabla_meta = Table(tabla_meta_data, colWidths=[55, 250, 65, 95, 65, 202])
    tabla_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#EAECF0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(tabla_meta)
    story.append(Spacer(1, 6))

    # Instrucción operativa
    story.append(Paragraph(
        "<b>Instrucciones:</b> Marque con una 'X' la casilla de asistencia <b>[&nbsp;&nbsp;&nbsp;&nbsp;]</b> y solicite la firma del participante. "
        "Los renglones vacíos al final están destinados al registro manual de personas que asistan sin inscripción previa.",
        style_instruction
    ))
    story.append(Spacer(1, 6))

    # 3. TABLA DE ASISTENCIA
    # Ancho total imprimible disponible en landscape letter: 732 pt
    # ColWidths: N°(24), Documento(75), Apellidos y Nombres(175), Tipo/Procedencia(148), Firma(160), Asist.(50), Observaciones(100) = 732 pt
    col_widths = [24, 75, 175, 148, 160, 50, 100]

    header_row = [
        Paragraph("N°", style_th),
        Paragraph("Documento", style_th),
        Paragraph("Apellidos y Nombres", style_th),
        Paragraph("Tipo / Procedencia", style_th),
        Paragraph("Firma del Asistente", style_th),
        Paragraph("Asistencia", style_th),
        Paragraph("Observaciones", style_th),
    ]

    filas_tabla = [header_row]

    # Agregar filas de inscritos reales
    participantes = datos['participantes']
    if participantes:
        for p in participantes:
            filas_tabla.append([
                Paragraph(str(p['numero']), style_td_center),
                Paragraph(str(p['documento']), style_td),
                Paragraph(p['nombre_completo'], style_td),
                Paragraph(f"{p['tipo']} — {p['programa_institucion']}", style_td),
                Paragraph("", style_td),  # Espacio para firma
                Paragraph("<b>[&nbsp;&nbsp;&nbsp;&nbsp;]</b>", style_td_center),
                Paragraph("", style_td),
            ])
    else:
        filas_tabla.append([
            Paragraph("-", style_td_center),
            Paragraph("Sin inscritos", style_td),
            Paragraph("No se registran participantes con inscripción activa para este evento.", style_td),
            Paragraph("-", style_td_center),
            Paragraph("", style_td),
            Paragraph("<b>[&nbsp;&nbsp;&nbsp;&nbsp;]</b>", style_td_center),
            Paragraph("", style_td),
        ])

    # Filas en blanco adicionales para walk-ins (personas no inscritas previamente)
    num_inicio = len(participantes) + 1 if participantes else 1
    total_filas_blanco = 7  # Entre 5 y 10 reglones en blanco
    for idx_blanco in range(num_inicio, num_inicio + total_filas_blanco):
        filas_tabla.append([
            Paragraph(str(idx_blanco), style_td_center),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("<b>[&nbsp;&nbsp;&nbsp;&nbsp;]</b>", style_td_center),
            Paragraph("", style_td),
        ])

    tabla_asistencia = Table(filas_tabla, colWidths=col_widths, repeatRows=1)
    tabla_asistencia.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F2042')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#1D2939')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tabla_asistencia)
    story.append(Spacer(1, 14))

    # 4. CIERRE Y FIRMA DEL RESPONSABLE DE JORNADA
    firma_data = [
        [
            Paragraph("<b>Responsable de la Jornada / Mesa de Registro:</b>", style_meta_label),
            Paragraph("<b>Observaciones de Cierre de Jornada:</b>", style_meta_label),
        ],
        [
            Paragraph("Nombre: __________________________________________________<br/><br/>"
                      "Documento de Identidad: ___________________________________<br/><br/>"
                      "Firma: ___________________________________________________", style_meta_val),
            Paragraph("Hora de inicio de registro: ___________ | Hora de cierre: ___________<br/><br/>"
                      "Total asistentes que firmaron: __________<br/><br/>"
                      "Novedades: _______________________________________________", style_meta_val),
        ]
    ]
    tabla_firma = Table(firma_data, colWidths=[360, 372])
    tabla_firma.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))

    story.append(KeepTogether([tabla_firma]))

    # Construir el documento
    doc.build(story, canvasmaker=NumberedCanvasLandscape)
    buffer.seek(0)
    return buffer.getvalue()


def generar_pdf_reporte_consolidado(datos, usuario_generador=None):
    """
    Construye en memoria el archivo PDF del Reporte Consolidado del Evento.
    Formato: Vertical (Portrait Letter), estructurado para consulta gerencial y archivo.
    Incluye ficha técnica, indicadores con aviso de estado y tabla discriminada de participantes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=30,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Estilos tipográficos
    style_inst = ParagraphStyle(
        'InstTitlePort',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=13,
        textColor=colors.HexColor('#0F2042'),
        alignment=1,
    )
    style_sub = ParagraphStyle(
        'InstSubPort',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#475467'),
        alignment=1,
    )
    style_doc_title = ParagraphStyle(
        'DocTitlePort',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=colors.HexColor('#0F2042'),
        alignment=1,
    )
    style_section = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#0F2042'),
    )
    style_label = ParagraphStyle(
        'LabelPort',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#1D2939'),
    )
    style_val = ParagraphStyle(
        'ValPort',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#344054'),
    )
    style_th = ParagraphStyle(
        'ThPort',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=1,
    )
    style_td = ParagraphStyle(
        'TdPort',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#1D2939'),
    )
    style_td_center = ParagraphStyle(
        'TdPortCenter',
        parent=style_td,
        alignment=1,
    )
    style_kpi_title = ParagraphStyle(
        'KpiTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#475467'),
        alignment=1,
    )
    style_kpi_val = ParagraphStyle(
        'KpiVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.HexColor('#0F2042'),
        alignment=1,
    )
    style_alert = ParagraphStyle(
        'AlertNote',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#B54708'),
        alignment=1,
    )

    story = []

    # 1. ENCABEZADO
    story.append(Paragraph("CORPORACIÓN UNIVERSITARIA MINUTO DE DIOS — UNIMINUTO", style_inst))
    story.append(Paragraph("SISTEMA INTEGRADO DE GESTIÓN DE ASISTENCIA Y EVENTOS (SIGAE)", style_sub))
    story.append(Spacer(1, 4))
    story.append(Paragraph("INFORME CONSOLIDADO DE ASISTENCIA Y PARTICIPACIÓN", style_doc_title))
    story.append(Spacer(1, 8))

    # 2. FICHA TÉCNICA DEL EVENTO
    evento = datos['evento']
    organizador_str = evento.organizador.get_full_name() if hasattr(evento.organizador, 'get_full_name') else str(evento.organizador)
    fecha_str = evento.fecha.strftime("%d/%m/%Y") if evento.fecha else "Por definir"
    horario_str = f"{evento.hora_inicio.strftime('%H:%M')} - {evento.hora_fin.strftime('%H:%M')}" if evento.hora_inicio and evento.hora_fin else "Sin horario"
    cupo_str = str(evento.cupo) if evento.cupo is not None else "Ilimitado"

    story.append(Paragraph("Ficha Técnica del Evento", style_section))
    story.append(Spacer(1, 3))

    ficha_data = [
        [
            Paragraph("<b>Nombre:</b>", style_label),
            Paragraph(evento.nombre, style_val),
            Paragraph("<b>Estado:</b>", style_label),
            Paragraph(f"<b>{evento.get_estado_display() if hasattr(evento, 'get_estado_display') else evento.estado}</b>", style_val),
        ],
        [
            Paragraph("<b>Categoría:</b>", style_label),
            Paragraph(evento.categoria.nombre, style_val),
            Paragraph("<b>Modalidad:</b>", style_label),
            Paragraph(evento.get_modalidad_display() if hasattr(evento, 'get_modalidad_display') else evento.modalidad, style_val),
        ],
        [
            Paragraph("<b>Fecha:</b>", style_label),
            Paragraph(fecha_str, style_val),
            Paragraph("<b>Horario:</b>", style_label),
            Paragraph(horario_str, style_val),
        ],
        [
            Paragraph("<b>Lugar:</b>", style_label),
            Paragraph(evento.lugar, style_val),
            Paragraph("<b>Cupo:</b>", style_label),
            Paragraph(cupo_str, style_val),
        ],
        [
            Paragraph("<b>Organizador:</b>", style_label),
            Paragraph(organizador_str, style_val),
            Paragraph("<b>Inscripciones Canc.:</b>", style_label),
            Paragraph(str(datos.get('total_canceladas', 0)), style_val),
        ],
        [
            Paragraph("<b>Descripción:</b>", style_label),
            Paragraph(evento.descripcion or "Sin descripción detallada.", style_val),
            Paragraph("", style_label),
            Paragraph("", style_val),
        ]
    ]

    tabla_ficha = Table(ficha_data, colWidths=[70, 200, 100, 170])
    tabla_ficha.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8F9FA')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#EAECF0')),
        ('SPAN', (1, 5), (3, 5)),  # Descripción abarca las columnas finales
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(tabla_ficha)
    story.append(Spacer(1, 8))

    # 3. INDICADORES CLAVE (DASHBOARD)
    story.append(Paragraph("Métricas de Asistencia y Participación", style_section))
    story.append(Spacer(1, 3))

    kpi_data = [
        [
            Paragraph("Inscritos Activos", style_kpi_title),
            Paragraph("Asistencias Válidas", style_kpi_title),
            Paragraph("Sin Asistencia Válida", style_kpi_title),
            Paragraph("% Asistencia Efectiva", style_kpi_title),
        ],
        [
            Paragraph(str(datos['total_inscritos_activos']), style_kpi_val),
            Paragraph(str(datos['total_asistentes_validos']), style_kpi_val),
            Paragraph(str(datos['total_sin_asistencia_valida']), style_kpi_val),
            Paragraph(f"{datos['porcentaje_asistencia']}%", style_kpi_val),
        ]
    ]
    tabla_kpi = Table(kpi_data, colWidths=[135, 135, 135, 135])
    tabla_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EAECF0')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F8F9FA')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D0D5DD')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(tabla_kpi)

    # Aviso contextual si el evento no está concluido
    if not datos['evento_cerrado']:
        story.append(Spacer(1, 4))
        aviso_text = (
            "<b>(*) Nota aclaratoria:</b> Este evento se encuentra en estado <b>"
            f"{evento.get_estado_display() if hasattr(evento, 'get_estado_display') else evento.estado}</b>. "
            "La columna 'Sin Asistencia' corresponde a participantes pendientes de registro y no debe interpretarse como inasistencia definitiva."
        )
        aviso_table = Table([[Paragraph(aviso_text, style_alert)]], colWidths=[540])
        aviso_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFAEB')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#FEDF89')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(aviso_table)

    story.append(Spacer(1, 8))

    # 4. TABLA DETALLADA DE PARTICIPANTES
    story.append(Paragraph("Detalle Individual de Participantes", style_section))
    story.append(Spacer(1, 3))

    # Ancho total disponible en portrait letter: 540 pt
    # ColWidths: N°(22), Documento(65), Participante(143), Tipo(65), Asistencia(95), Entrada/Salida(85), Método(65) = 540 pt
    col_widths = [22, 65, 143, 65, 95, 85, 65]

    header_row = [
        Paragraph("N°", style_th),
        Paragraph("Documento", style_th),
        Paragraph("Participante", style_th),
        Paragraph("Tipo", style_th),
        Paragraph("Estado Asistencia", style_th),
        Paragraph("Entrada / Salida", style_th),
        Paragraph("Método", style_th),
    ]

    filas_tabla = [header_row]

    participantes = datos['participantes']
    if participantes:
        for p in participantes:
            # Color sutil según estado de asistencia
            if p['tiene_asistencia_valida']:
                estado_str = f"<font color='#027A48'><b>{p['estado_asistencia']}</b></font>"
            elif "Anulada" in p['estado_asistencia']:
                estado_str = f"<font color='#B42318'><b>{p['estado_asistencia']}</b></font>"
            else:
                estado_str = f"<font color='#475467'>{p['estado_asistencia']}</font>"

            horario_io = f"{p['hora_entrada']} / {p['hora_salida']}" if p['hora_entrada'] != '-' else "-"

            filas_tabla.append([
                Paragraph(str(p['numero']), style_td_center),
                Paragraph(str(p['documento']), style_td),
                Paragraph(p['nombre_completo'], style_td),
                Paragraph(p['tipo'], style_td),
                Paragraph(estado_str, style_td_center),
                Paragraph(horario_io, style_td_center),
                Paragraph(p['metodo'], style_td_center),
            ])
    else:
        filas_tabla.append([
            Paragraph("-", style_td_center),
            Paragraph("-", style_td_center),
            Paragraph("No se registran participantes activos para este evento.", style_td),
            Paragraph("-", style_td_center),
            Paragraph("-", style_td_center),
            Paragraph("-", style_td_center),
            Paragraph("-", style_td_center),
        ])

    tabla_part = Table(filas_tabla, colWidths=col_widths, repeatRows=1)
    tabla_part.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F2042')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#1D2939')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#EAECF0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tabla_part)
    story.append(Spacer(1, 10))

    # 5. METADATOS DE EMISIÓN DEL REPORTE
    gen_user_str = usuario_generador.get_full_name() if (usuario_generador and hasattr(usuario_generador, 'get_full_name')) else (usuario_generador.username if usuario_generador else "Sistema")
    fecha_emision_str = timezone.now().strftime("%d/%m/%Y %H:%M:%S")

    info_emision = (
        f"<b>Documento emitido por:</b> {gen_user_str} | "
        f"<b>Fecha de emisión:</b> {fecha_emision_str} | "
        f"<b>Hash de integridad:</b> SIGAE-EVT{evento.pk}-{evento.fecha.strftime('%Y%m%d')}"
    )
    story.append(Paragraph(info_emision, style_sub))

    # Construir documento
    doc.build(story, canvasmaker=NumberedCanvasPortrait)
    buffer.seek(0)
    return buffer.getvalue()
