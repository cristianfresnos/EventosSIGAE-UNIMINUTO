"""
Pruebas automatizadas para el módulo de Reportes (PDF y Consultas).
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from usuarios.models import Rol, Usuario
from eventos.models import CategoriaEvento, Evento, ModalidadEvento, EstadoEvento
from participantes.models import Participante, Inscripcion, TipoParticipante, EstadoInscripcion
from asistencia.models import Asistencia, MetodoAsistencia, EstadoAsistencia
from auditoria.models import Auditoria
from reportes import services


class ReportesPDFTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Roles
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        # Usuarios
        self.usuario_organizador = Usuario.objects.create_user(
            username='organizador_user',
            email='organizador@uniminuto.edu',
            password='Password123*',
            documento='11111111',
            nombres='Carlos',
            apellidos='Organizador',
            rol=self.rol_docente,
            is_staff=False
        )

        self.usuario_admin = Usuario.objects.create_user(
            username='admin_user',
            email='admin@uniminuto.edu',
            password='Password123*',
            documento='22222222',
            nombres='Admin',
            apellidos='Sistema',
            rol=self.rol_admin,
            is_staff=True,
            is_superuser=True
        )

        self.usuario_ajeno = Usuario.objects.create_user(
            username='estudiante_ajeno',
            email='ajeno@uniminuto.edu',
            password='Password123*',
            documento='33333333',
            nombres='Pedro',
            apellidos='Ajeno',
            rol=self.rol_estudiante,
            is_staff=False
        )

        self.usuario_estudiante = Usuario.objects.create_user(
            username='estudiante_inscrito',
            email='estudiante@uniminuto.edu',
            password='Password123*',
            documento='44444444',
            nombres='Ana',
            apellidos='Alvarez',
            rol=self.rol_estudiante
        )

        # Categoría y Evento
        self.categoria = CategoriaEvento.objects.create(nombre='Congreso')
        self.evento = Evento.objects.create(
            nombre='Congreso de Innovación',
            descripcion='Congreso de investigación e innovación.',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Auditorio Central',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.usuario_organizador
        )

        # Participantes: 1 Institucional, 1 Externo
        self.part_institucional = Participante.objects.create(
            usuario=self.usuario_estudiante,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.usuario_estudiante.documento,
            nombres=self.usuario_estudiante.nombres,
            apellidos=self.usuario_estudiante.apellidos,
            correo=self.usuario_estudiante.email,
            programa='Ingeniería de Sistemas'
        )

        self.part_externo = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='99887766',
            nombres='Bernardo',
            apellidos='Bermúdez',
            correo='bernardo@externo.org',
            institucion='Empresa Aliada'
        )

        # Inscripciones Activas
        self.ins_institucional = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_institucional,
            estado=EstadoInscripcion.ACTIVA
        )

        self.ins_externo = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_externo,
            estado=EstadoInscripcion.ACTIVA
        )

    # 1. Generación de la planilla con inscritos activos
    def test_generacion_planilla_con_inscritos_activos(self):
        datos = services.obtener_datos_planilla_imprimible(self.evento.pk)
        self.assertEqual(datos['total_inscritos'], 2)
        # Orden alfabético por apellidos: Alvarez antes que Bermúdez
        self.assertEqual(datos['participantes'][0]['nombre_completo'], "Alvarez, Ana")
        self.assertEqual(datos['participantes'][1]['nombre_completo'], "Bermúdez, Bernardo")

        pdf_bytes = services.generar_pdf_planilla_asistencia(datos)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 1000)

    # 2. Exclusión de inscripciones canceladas
    def test_exclusion_inscripciones_canceladas(self):
        # Crear participante cancelado
        part_canc = Participante.objects.create(
            tipo=TipoParticipante.EXTERNO,
            documento='55555555',
            nombres='Cancelado',
            apellidos='Zúñiga',
            correo='cancelado@test.com'
        )
        Inscripcion.objects.create(
            evento=self.evento,
            participante=part_canc,
            estado=EstadoInscripcion.CANCELADA
        )
        datos = services.obtener_datos_planilla_imprimible(self.evento.pk)
        self.assertEqual(datos['total_inscritos'], 2)
        documentos = [p['documento'] for p in datos['participantes']]
        self.assertNotIn('55555555', documentos)

    # 3. Inclusión de participantes institucionales y externos
    def test_inclusion_participantes_institucionales_y_externos(self):
        datos = services.obtener_datos_planilla_imprimible(self.evento.pk)
        tipos = [p['tipo'] for p in datos['participantes']]
        self.assertIn('Estudiante', tipos)
        self.assertIn('Externo', tipos)

        # El externo sin usuario debe conservar sus datos propios
        ext_data = next(p for p in datos['participantes'] if p['documento'] == '99887766')
        self.assertEqual(ext_data['nombre_completo'], 'Bermúdez, Bernardo')
        self.assertIn('Empresa Aliada', ext_data['programa_institucion'])

    # 4. Generación del PDF cuando no hay inscritos
    def test_generacion_pdf_sin_inscritos(self):
        evento_vacio = Evento.objects.create(
            nombre='Seminario Vacío',
            descripcion='Sin inscritos',
            fecha=datetime.date(2026, 12, 15),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Virtual',
            modalidad=ModalidadEvento.VIRTUAL,
            categoria=self.categoria,
            organizador=self.usuario_organizador
        )
        datos_plan = services.obtener_datos_planilla_imprimible(evento_vacio.pk)
        self.assertEqual(datos_plan['total_inscritos'], 0)
        pdf_plan = services.generar_pdf_planilla_asistencia(datos_plan)
        self.assertTrue(pdf_plan.startswith(b'%PDF'))

        datos_rep = services.obtener_reporte_consolidado_evento(evento_vacio.pk)
        self.assertEqual(datos_rep['total_inscritos_activos'], 0)
        self.assertEqual(datos_rep['porcentaje_asistencia'], 0.0)
        pdf_rep = services.generar_pdf_reporte_consolidado(datos_rep, self.usuario_organizador)
        self.assertTrue(pdf_rep.startswith(b'%PDF'))

    # 5. Generación del reporte consolidado
    def test_generacion_reporte_consolidado(self):
        # Registrar una asistencia
        Asistencia.objects.create(
            inscripcion=self.ins_institucional,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 5),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        datos = services.obtener_reporte_consolidado_evento(self.evento.pk)
        self.assertEqual(datos['total_inscritos_activos'], 2)
        self.assertEqual(datos['total_asistentes_validos'], 1)
        self.assertEqual(datos['total_sin_asistencia_valida'], 1)

        pdf_bytes = services.generar_pdf_reporte_consolidado(datos, self.usuario_organizador)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 1000)

    # 6. Exclusión de asistencias anuladas de los totales
    def test_exclusion_asistencias_anuladas_de_totales(self):
        # Asistencia anulada para el externo
        Asistencia.objects.create(
            inscripcion=self.ins_externo,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 10),
            metodo=MetodoAsistencia.MANUAL,
            estado=EstadoAsistencia.ANULADA
        )
        datos = services.obtener_reporte_consolidado_evento(self.evento.pk)
        # Asistencias válidas debe ser 0 porque la única existente está ANULADA
        self.assertEqual(datos['total_asistentes_validos'], 0)
        self.assertEqual(datos['total_sin_asistencia_valida'], 2)
        self.assertEqual(datos['total_asistencias_anuladas'], 1)
        self.assertEqual(datos['porcentaje_asistencia'], 0.0)

    # 7. Identificación de inscritos sin asistencia válida
    def test_identificacion_inscritos_sin_asistencia_valida(self):
        # Solo institucional registra asistencia válida
        Asistencia.objects.create(
            inscripcion=self.ins_institucional,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        datos = services.obtener_reporte_consolidado_evento(self.evento.pk)
        participantes = datos['participantes']

        inst_part = next(p for p in participantes if p['documento'] == self.part_institucional.documento)
        ext_part = next(p for p in participantes if p['documento'] == self.part_externo.documento)

        self.assertTrue(inst_part['tiene_asistencia_valida'])
        self.assertEqual(inst_part['estado_asistencia'], 'Registrada')

        self.assertFalse(ext_part['tiene_asistencia_valida'])
        self.assertIn('Sin registro', ext_part['estado_asistencia'])

    # 8. Cálculo correcto del porcentaje de asistencia
    def test_calculo_porcentaje_asistencia(self):
        # Con 2 inscritos y 1 asistente -> 50.0%
        Asistencia.objects.create(
            inscripcion=self.ins_institucional,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        datos = services.obtener_reporte_consolidado_evento(self.evento.pk)
        self.assertEqual(datos['porcentaje_asistencia'], 50.0)

        # Al registrar al segundo -> 100.0%
        Asistencia.objects.create(
            inscripcion=self.ins_externo,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 20),
            metodo=MetodoAsistencia.MANUAL,
            estado=EstadoAsistencia.REGISTRADA
        )
        datos2 = services.obtener_reporte_consolidado_evento(self.evento.pk)
        self.assertEqual(datos2['porcentaje_asistencia'], 100.0)

    # 9. Respuesta 404 para un evento inexistente
    def test_respuesta_404_evento_inexistente(self):
        self.client.force_login(self.usuario_admin)
        url_inexistente = reverse('reportes:planilla_asistencia_pdf', args=[99999])
        response = self.client.get(url_inexistente)
        self.assertEqual(response.status_code, 404)

        url_rep_inexistente = reverse('reportes:reporte_consolidado_pdf', args=[99999])
        response_rep = self.client.get(url_rep_inexistente)
        self.assertEqual(response_rep.status_code, 404)

    # 10. Restricción de acceso para usuarios no autorizados
    def test_restriccion_acceso_no_autorizado(self):
        # Usuario no autenticado (anónimo) debe ser redirigido al login (302)
        url_planilla = reverse('reportes:planilla_asistencia_pdf', args=[self.evento.pk])
        response_anon = self.client.get(url_planilla)
        self.assertEqual(response_anon.status_code, 302)

        # Usuario autenticado pero sin rol administrativo ni organizador debe recibir 403
        self.client.force_login(self.usuario_ajeno)
        response_ajeno = self.client.get(url_planilla)
        self.assertEqual(response_ajeno.status_code, 403)

    # 11. Registro de auditoría en las descargas exitosas
    def test_registro_auditoria_en_descargas_exitosas(self):
        self.client.force_login(self.usuario_organizador)
        url_planilla = reverse('reportes:planilla_asistencia_pdf', args=[self.evento.pk])

        auditorias_antes = Auditoria.objects.filter(modulo='REPORTES').count()
        response = self.client.get(url_planilla)
        self.assertEqual(response.status_code, 200)

        auditorias_despues = Auditoria.objects.filter(modulo='REPORTES').count()
        self.assertEqual(auditorias_despues, auditorias_antes + 1)

        ultimo_registro = Auditoria.objects.filter(modulo='REPORTES').first()
        self.assertEqual(ultimo_registro.accion, 'DESCARGAR_PLANILLA_PDF')
        self.assertEqual(ultimo_registro.usuario, self.usuario_organizador)
        self.assertIn(str(self.evento.pk), ultimo_registro.registro_afectado)

    # 12. Funcionamiento de las rutas y respuestas PDF
    def test_rutas_y_respuestas_pdf(self):
        self.client.force_login(self.usuario_admin)

        # Planilla
        url_plan = reverse('reportes:planilla_asistencia_pdf', args=[self.evento.pk])
        res_plan = self.client.get(url_plan)
        self.assertEqual(res_plan.status_code, 200)
        self.assertEqual(res_plan['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', res_plan['Content-Disposition'])
        self.assertIn('Planilla_Asistencia_', res_plan['Content-Disposition'])
        self.assertTrue(res_plan.content.startswith(b'%PDF'))

        # Reporte
        url_rep = reverse('reportes:reporte_consolidado_pdf', args=[self.evento.pk])
        res_rep = self.client.get(url_rep)
        self.assertEqual(res_rep.status_code, 200)
        self.assertEqual(res_rep['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', res_rep['Content-Disposition'])
        self.assertIn('Reporte_Consolidado_', res_rep['Content-Disposition'])
        self.assertTrue(res_rep.content.startswith(b'%PDF'))
