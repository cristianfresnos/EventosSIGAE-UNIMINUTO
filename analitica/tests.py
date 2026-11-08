"""
Pruebas automatizadas para el módulo de Analítica y Dashboard Institucional.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Rol, Usuario
from eventos.models import Evento, CategoriaEvento, ModalidadEvento, EstadoEvento
from participantes.models import Participante, Inscripcion, EstadoInscripcion, TipoParticipante
from asistencia.models import Asistencia, EstadoAsistencia, MetodoAsistencia
from auditoria.models import Auditoria
import io
import openpyxl
from analitica.services import (
    puede_ver_dashboard,
    tiene_alcance_global,
    obtener_eventos_permitidos,
    calcular_metricas_dashboard,
    filtrar_eventos,
    exportar_csv_analitica,
    exportar_excel_analitica,
)


class AnaliticaDashboardTests(TestCase):
    """
    Suite de pruebas integrales para el Dashboard Analítico, métricas, filtros y exportación.
    """

    def setUp(self):
        # 1. Configuración de Roles
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        # 2. Configuración de Usuarios
        self.admin_user = Usuario.objects.create_user(
            username='admin_sigae',
            email='admin@uniminuto.edu.co',
            password='Password123!',
            documento='10000001',
            nombres='Administrador',
            apellidos='General',
            rol=self.rol_admin,
            is_staff=True,
            is_superuser=True
        )

        self.organizador_1 = Usuario.objects.create_user(
            username='profesor_carlos',
            email='carlos@uniminuto.edu.co',
            password='Password123!',
            documento='10000002',
            nombres='Carlos',
            apellidos='Docente',
            rol=self.rol_docente
        )

        self.organizador_2 = Usuario.objects.create_user(
            username='profesora_elena',
            email='elena@uniminuto.edu.co',
            password='Password123!',
            documento='10000003',
            nombres='Elena',
            apellidos='Docente',
            rol=self.rol_docente
        )

        self.estudiante_user = Usuario.objects.create_user(
            username='estudiante_juan',
            email='juan@uniminuto.edu.co',
            password='Password123!',
            documento='10000004',
            nombres='Juan',
            apellidos='Estudiante',
            rol=self.rol_estudiante
        )

        # 3. Categorías
        self.cat_tecnologia = CategoriaEvento.objects.create(nombre='Tecnología')
        self.cat_academico = CategoriaEvento.objects.create(nombre='Académico')

        # 4. Eventos
        self.today = timezone.localdate()

        # Evento 1: Organizado por organizador_1, Próximo, Presencial
        self.evento_1 = Evento.objects.create(
            nombre='Seminario de Inteligencia Artificial',
            descripcion='Evento sobre avances en IA y machine learning.',
            fecha=self.today + datetime.timedelta(days=5),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.cat_tecnologia,
            organizador=self.organizador_1
        )

        # Evento 2: Organizado por organizador_2, Finalizado, Virtual
        self.evento_2 = Evento.objects.create(
            nombre='Congreso de Innovación Pedagógica',
            descripcion='Estrategias de enseñanza digital.',
            fecha=self.today - datetime.timedelta(days=5),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Teams',
            modalidad=ModalidadEvento.VIRTUAL,
            cupo=200,
            estado=EstadoEvento.FINALIZADO,
            categoria=self.cat_academico,
            organizador=self.organizador_2
        )

        # Evento 3: Organizado por organizador_1, Sin inscritos (caso vacío)
        self.evento_vacio = Evento.objects.create(
            nombre='Taller Experimental Futuro',
            descripcion='Taller sin participantes para validar casos borde.',
            fecha=self.today + datetime.timedelta(days=20),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Laboratorio 3',
            modalidad=ModalidadEvento.HIBRIDA,
            cupo=50,
            estado=EstadoEvento.BORRADOR,
            categoria=self.cat_tecnologia,
            organizador=self.organizador_1
        )

        # 5. Participantes
        self.part_1 = Participante.objects.create(
            nombres='Andrés',
            apellidos='Pérez',
            documento='11111111',
            correo='andres.perez@uniminuto.edu.co',
            tipo=TipoParticipante.ESTUDIANTE,
            programa='Ingeniería de Sistemas'
        )

        self.part_2 = Participante.objects.create(
            nombres='Beatriz',
            apellidos='Gómez',
            documento='22222222',
            correo='beatriz.gomez@uniminuto.edu.co',
            tipo=TipoParticipante.DOCENTE,
            programa='Licenciatura'
        )

        self.part_3 = Participante.objects.create(
            nombres='Camilo',
            apellidos='Torres',
            documento='33333333',
            correo='camilo.torres@uniminuto.edu.co',
            tipo=TipoParticipante.ESTUDIANTE,
            programa='Comunicación'
        )

        # 6. Inscripciones
        # Evento 1 tiene 2 inscripciones activas (part_1, part_2) y 1 cancelada (part_3)
        self.ins_1_1 = Inscripcion.objects.create(
            evento=self.evento_1,
            participante=self.part_1,
            estado=EstadoInscripcion.ACTIVA
        )
        self.ins_1_2 = Inscripcion.objects.create(
            evento=self.evento_1,
            participante=self.part_2,
            estado=EstadoInscripcion.ACTIVA
        )
        self.ins_1_3 = Inscripcion.objects.create(
            evento=self.evento_1,
            participante=self.part_3,
            estado=EstadoInscripcion.CANCELADA
        )

        # Evento 2 tiene a part_1 inscrito (el mismo part_1 que ya está en evento_1)
        self.ins_2_1 = Inscripcion.objects.create(
            evento=self.evento_2,
            participante=self.part_1,
            estado=EstadoInscripcion.ACTIVA
        )

        # 7. Asistencias
        # ins_1_1: Asistencia REGISTRADA vía QR a las 09:15
        self.asist_1 = Asistencia.objects.create(
            inscripcion=self.ins_1_1,
            fecha=self.evento_1.fecha,
            hora_entrada=datetime.time(9, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )

        # ins_1_2: Asistencia ANULADA (no debe contabilizarse en efectivas)
        self.asist_2 = Asistencia.objects.create(
            inscripcion=self.ins_1_2,
            fecha=self.evento_1.fecha,
            hora_entrada=datetime.time(10, 30),
            metodo=MetodoAsistencia.MANUAL,
            estado=EstadoAsistencia.ANULADA,
            observaciones='Registro anulado por error de operador.'
        )

    # --------------------------------------------------------------------------
    # PRUEBAS DE SEGURIDAD Y PERMISOS
    # --------------------------------------------------------------------------

    def test_acceso_anonimo_redirecciona_a_login(self):
        client = Client()
        resp = client.get(reverse('analitica:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/usuarios/login/', resp.url)

        resp_csv = client.get(reverse('analitica:exportar_csv'))
        self.assertEqual(resp_csv.status_code, 302)
        self.assertIn('/usuarios/login/', resp_csv.url)

    def test_acceso_estudiante_sin_eventos_retorna_403(self):
        client = Client()
        client.force_login(self.estudiante_user)

        resp = client.get(reverse('analitica:dashboard'))
        self.assertEqual(resp.status_code, 403)

        resp_csv = client.get(reverse('analitica:exportar_csv'))
        self.assertEqual(resp_csv.status_code, 403)

    def test_acceso_administrador_alcance_global(self):
        client = Client()
        client.force_login(self.admin_user)

        resp = client.get(reverse('analitica:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Alcance Institucional Global')
        self.assertContains(resp, self.evento_1.nombre)
        self.assertContains(resp, self.evento_2.nombre)
        self.assertContains(resp, self.evento_vacio.nombre)

    def test_acceso_organizador_limitado_a_sus_propios_eventos(self):
        client = Client()
        client.force_login(self.organizador_1)

        resp = client.get(reverse('analitica:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Alcance de Organizador')
        # Organizador 1 debe ver evento_1 y evento_vacio
        self.assertContains(resp, self.evento_1.nombre)
        self.assertContains(resp, self.evento_vacio.nombre)
        # Organizador 1 NO debe ver evento_2
        self.assertNotContains(resp, self.evento_2.nombre)

    def test_organizador_intenta_consultar_evento_ajeno_retorna_403(self):
        client = Client()
        client.force_login(self.organizador_1)

        # Intentar forzar la consulta de evento_2 (organizado por organizador_2)
        resp = client.get(reverse('analitica:dashboard'), {'evento': self.evento_2.pk})
        self.assertEqual(resp.status_code, 403)

        # Intentar forzar la exportación de evento_2
        resp_csv = client.get(reverse('analitica:exportar_csv'), {'evento': self.evento_2.pk})
        self.assertEqual(resp_csv.status_code, 403)

    # --------------------------------------------------------------------------
    # PRUEBAS DE CÁLCULO DE MÉTRICAS E INDICADORES
    # --------------------------------------------------------------------------

    def test_calculo_metricas_globales(self):
        eventos_qs = Evento.objects.all()
        metricas = calcular_metricas_dashboard(eventos_qs)

        # 3 eventos en total
        self.assertEqual(metricas['total_eventos'], 3)
        # 2 próximos (evento_1 y evento_vacio), 1 finalizado (evento_2)
        self.assertEqual(metricas['eventos_proximos'], 2)
        self.assertEqual(metricas['eventos_finalizados'], 1)

        # Inscripciones activas: ins_1_1, ins_1_2, ins_2_1 = 3 (ins_1_3 cancelada se excluye)
        self.assertEqual(metricas['total_inscripciones_activas'], 3)

        # Participantes únicos: part_1 (inscrito en evento 1 y 2) y part_2 = 2 participantes únicos
        self.assertEqual(metricas['total_participantes_unicos'], 2)

        # Asistencias efectivas: solo asist_1 (asist_2 está ANULADA)
        self.assertEqual(metricas['total_asistencias_efectivas'], 1)
        self.assertEqual(metricas['total_asistencias_anuladas'], 1)

        # Porcentaje: 1 asistencia efectiva / 3 inscripciones activas = 33.3%
        self.assertEqual(metricas['porcentaje_asistencia_efectiva'], 33.3)

    def test_calculo_metricas_evento_especifico(self):
        eventos_qs = Evento.objects.filter(pk=self.evento_1.pk)
        metricas = calcular_metricas_dashboard(eventos_qs)

        self.assertEqual(metricas['total_eventos'], 1)
        # 2 inscripciones activas (part_1, part_2)
        self.assertEqual(metricas['total_inscripciones_activas'], 2)
        self.assertEqual(metricas['total_participantes_unicos'], 2)
        # 1 asistencia válida, 1 anulada
        self.assertEqual(metricas['total_asistencias_efectivas'], 1)
        self.assertEqual(metricas['total_asistencias_anuladas'], 1)
        # Porcentaje: 1 / 2 = 50.0%
        self.assertEqual(metricas['porcentaje_asistencia_efectiva'], 50.0)

    def test_evento_sin_inscripciones_manejo_seguro(self):
        eventos_qs = Evento.objects.filter(pk=self.evento_vacio.pk)
        metricas = calcular_metricas_dashboard(eventos_qs)

        self.assertEqual(metricas['total_eventos'], 1)
        self.assertEqual(metricas['total_inscripciones_activas'], 0)
        self.assertEqual(metricas['total_participantes_unicos'], 0)
        self.assertEqual(metricas['total_asistencias_efectivas'], 0)
        self.assertEqual(metricas['total_asistencias_anuladas'], 0)
        self.assertEqual(metricas['porcentaje_asistencia_efectiva'], 0.0)

    # --------------------------------------------------------------------------
    # PRUEBAS DE FILTROS MULTIDIMENSIONALES
    # --------------------------------------------------------------------------

    def test_filtrar_por_categoria(self):
        eventos_qs = Evento.objects.all()
        filtrados = filtrar_eventos(eventos_qs, {'categoria': self.cat_academico.pk})
        self.assertEqual(filtrados.count(), 1)
        self.assertEqual(filtrados.first(), self.evento_2)

    def test_filtrar_por_modalidad(self):
        eventos_qs = Evento.objects.all()
        filtrados_virt = filtrar_eventos(eventos_qs, {'modalidad': ModalidadEvento.VIRTUAL})
        self.assertEqual(filtrados_virt.count(), 1)
        self.assertEqual(filtrados_virt.first(), self.evento_2)

        filtrados_pres = filtrar_eventos(eventos_qs, {'modalidad': ModalidadEvento.PRESENCIAL})
        self.assertEqual(filtrados_pres.count(), 1)
        self.assertEqual(filtrados_pres.first(), self.evento_1)

    def test_filtrar_por_estado(self):
        eventos_qs = Evento.objects.all()
        filtrados = filtrar_eventos(eventos_qs, {'estado': EstadoEvento.FINALIZADO})
        self.assertEqual(filtrados.count(), 1)
        self.assertEqual(filtrados.first(), self.evento_2)

    def test_filtrar_por_rango_fechas(self):
        eventos_qs = Evento.objects.all()
        # Filtro de fecha desde hoy en adelante (debe retornar evento_1 y evento_vacio)
        filtrados_futuros = filtrar_eventos(eventos_qs, {'fecha_desde': self.today})
        self.assertEqual(filtrados_futuros.count(), 2)

        # Filtro de fecha anterior a hoy (debe retornar evento_2)
        filtrados_pasados = filtrar_eventos(eventos_qs, {'fecha_hasta': self.today - datetime.timedelta(days=1)})
        self.assertEqual(filtrados_pasados.count(), 1)
        self.assertEqual(filtrados_pasados.first(), self.evento_2)

    # --------------------------------------------------------------------------
    # PRUEBAS DE VISUALIZACIONES Y SERIES DE DATOS
    # --------------------------------------------------------------------------

    def test_estructura_datos_visualizaciones(self):
        eventos_qs = Evento.objects.all()
        metricas = calcular_metricas_dashboard(eventos_qs)

        # 1. Gráfica de Meses
        self.assertTrue(metricas['grafica_meses']['tiene_datos'])
        self.assertGreaterEqual(len(metricas['grafica_meses']['labels']), 1)

        # 2. Gráfica de Eventos
        self.assertTrue(metricas['grafica_eventos']['tiene_datos'])
        self.assertEqual(len(metricas['grafica_eventos']['labels']), 3)

        # 3. Categoría y Modalidad
        self.assertTrue(metricas['grafica_categoria']['tiene_datos'])
        self.assertTrue(metricas['grafica_modalidad']['tiene_datos'])

        # 4. Métodos: debe reportar QR (asist_1)
        self.assertTrue(metricas['grafica_metodos']['tiene_datos'])
        self.assertIn('QR', metricas['grafica_metodos']['labels'])

        # 5. Franjas Horarias: asist_1 fue a las 09:15, debe registrar en '08:00 - 09:59'
        self.assertTrue(metricas['grafica_franjas']['tiene_datos'])
        idx_franja = metricas['grafica_franjas']['labels'].index('08:00 - 09:59')
        self.assertEqual(metricas['grafica_franjas']['data'][idx_franja], 1)

    # --------------------------------------------------------------------------
    # PRUEBAS DE EXPORTACIÓN CSV
    # --------------------------------------------------------------------------

    def test_exportar_csv_contenido_y_encoding(self):
        client = Client()
        client.force_login(self.admin_user)

        resp = client.get(reverse('analitica:exportar_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="reporte_analitica_sigae_', resp['Content-Disposition'])

        # Verificar BOM UTF-8 (para compatibilidad en Microsoft Excel)
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))

        # Decodificar y verificar contenido de columnas y filas
        csv_texto = resp.content.decode('utf-8-sig')
        self.assertIn('SISTEMA INTEGRADO DE GESTION DE ASISTENCIA Y EVENTOS', csv_texto)
        self.assertIn('ID Evento,Nombre Evento,Categoria,Modalidad', csv_texto)
        self.assertIn('Andrés', csv_texto)
        self.assertIn('Beatriz', csv_texto)
        # La asistencia anulada debe figurar con su estado
        self.assertIn('Anulada', csv_texto)

    # --------------------------------------------------------------------------
    # PRUEBAS DE REGISTRO DE AUDITORÍA
    # --------------------------------------------------------------------------

    def test_auditoria_registrada_al_consultar_y_exportar(self):
        client = Client()
        client.force_login(self.admin_user)

        conteo_inicial = Auditoria.objects.count()

        # 1. Consulta del Dashboard
        client.get(reverse('analitica:dashboard'))
        self.assertEqual(Auditoria.objects.count(), conteo_inicial + 1)
        ultimo_log = Auditoria.objects.first()
        self.assertEqual(ultimo_log.modulo, 'ANALITICA')
        self.assertEqual(ultimo_log.accion, 'CONSULTA_DASHBOARD')
        self.assertEqual(ultimo_log.usuario, self.admin_user)

        # 2. Exportación a CSV
        client.get(reverse('analitica:exportar_csv'))
        self.assertEqual(Auditoria.objects.count(), conteo_inicial + 2)
        log_csv = Auditoria.objects.first()
        self.assertEqual(log_csv.modulo, 'ANALITICA')
        self.assertEqual(log_csv.accion, 'EXPORTACION_CSV_ANALITICA')
        self.assertEqual(log_csv.usuario, self.admin_user)

    # --------------------------------------------------------------------------
    # PRUEBAS DE EXPORTACIÓN EXCEL (.XLSX) NATIVA (RF-20)
    # --------------------------------------------------------------------------

    def test_exportar_excel_formato_xlsx_valido_en_memoria(self):
        """(RF-20) La exportación genera un archivo .xlsx válido con hojas y tipado nativo."""
        client = Client()
        client.force_login(self.admin_user)

        response = client.get(reverse('analitica:exportar_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('attachment; filename="reporte_analitica_sigae_', response['Content-Disposition'])

        # Cargar el libro desde el buffer en memoria
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        self.assertIn('Resumen Institucional', wb.sheetnames)
        self.assertIn('Eventos', wb.sheetnames)
        self.assertIn('Participantes y Asistencia', wb.sheetnames)

        # Verificar hoja de resumen
        ws_resumen = wb['Resumen Institucional']
        self.assertIn('SIGAE - UNIMINUTO', str(ws_resumen['A1'].value))

        # Verificar hoja de eventos
        ws_eventos = wb['Eventos']
        # Cabeceras en fila 1
        headers = [cell.value for cell in ws_eventos[1]]
        self.assertIn('Nombre del Evento', headers)
        self.assertIn('Inscritos', headers)
        self.assertIn('% Asistencia', headers)

        # Verificar auditoría
        log_excel = Auditoria.objects.filter(accion='EXPORTACION_EXCEL_ANALITICA').first()
        self.assertIsNotNone(log_excel)
        self.assertEqual(log_excel.modulo, 'ANALITICA')
        self.assertEqual(log_excel.usuario, self.admin_user)

    def test_exportar_excel_aplica_alcance_restringido_organizador(self):
        """(RF-20) Un organizador solo exporta en Excel los eventos que tiene autorización para consultar."""
        client = Client()
        client.force_login(self.organizador_1)

        response = client.get(reverse('analitica:exportar_excel'))
        self.assertEqual(response.status_code, 200)

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_eventos = wb['Eventos']

        nombres_eventos_exportados = [
            ws_eventos.cell(row=r, column=2).value
            for r in range(2, ws_eventos.max_row + 1)
        ]

        # Debe contener su evento (Seminario de Inteligencia Artificial) pero NO el del organizador 2
        self.assertIn('Seminario de Inteligencia Artificial', nombres_eventos_exportados)
        self.assertNotIn('Congreso de Innovación Pedagógica', nombres_eventos_exportados)

    def test_exportar_excel_denegado_a_estudiante(self):
        """(RF-20) Un usuario sin privilegios analíticos recibe 403 al intentar exportar en Excel."""
        client = Client()
        client.force_login(self.estudiante_user)

        response = client.get(reverse('analitica:exportar_excel'))
        self.assertEqual(response.status_code, 403)
