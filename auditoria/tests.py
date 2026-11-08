"""
Pruebas automatizadas para el módulo de Auditoría Institucional y Trazabilidad (RF-23).
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from usuarios.models import Rol, Usuario
from auditoria.models import Auditoria


class ConsultaAuditoriaPortalTests(TestCase):
    """
    Suite de pruebas para la vista de consulta de bitácora institucional (RF-23).
    Verifica control de acceso riguroso, inmutabilidad, filtrado y paginación.
    """

    def setUp(self):
        self.client = Client()

        # Roles
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        # Usuarios
        self.admin_user = Usuario.objects.create_user(
            username='admin_auditor',
            email='auditor@uniminuto.edu.co',
            password='Password123*',
            documento='10101010',
            rol=self.rol_admin
        )

        self.staff_user = Usuario.objects.create_user(
            username='staff_auditor',
            email='staff@uniminuto.edu.co',
            password='Password123*',
            documento='20202020',
            rol=self.rol_admin,
            is_staff=True
        )

        self.docente_user = Usuario.objects.create_user(
            username='docente_simple',
            email='docente@uniminuto.edu.co',
            password='Password123*',
            documento='30303030',
            rol=self.rol_docente
        )

        self.estudiante_user = Usuario.objects.create_user(
            username='estudiante_simple',
            email='estudiante@uniminuto.edu.co',
            password='Password123*',
            documento='40404040',
            rol=self.rol_estudiante
        )

        # Crear registros de auditoría de prueba
        self.log_evento = Auditoria.objects.create(
            usuario=self.docente_user,
            modulo='EVENTOS',
            accion='CREAR_EVENTO',
            registro_afectado='Evento Conferencia Internacional',
            ip='192.168.1.10'
        )

        self.log_asistencia = Auditoria.objects.create(
            usuario=self.docente_user,
            modulo='ASISTENCIA',
            accion='REGISTRAR_LLEGADA_QR',
            registro_afectado='Inscripción 12345',
            ip='192.168.1.20'
        )

        self.log_cancelacion = Auditoria.objects.create(
            usuario=self.admin_user,
            modulo='EVENTOS',
            accion='CANCELAR_EVENTO',
            registro_afectado='Cancelación formal por contingencia',
            ip='10.0.0.1'
        )

    def test_consulta_auditoria_anonimo_redirige_a_login(self):
        """Un usuario anónimo debe ser redirigido al formulario de inicio de sesión."""
        response = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('usuarios:login'), response.url)

    def test_consulta_auditoria_denegada_a_docente(self):
        """Un docente sin rol de Administrador recibe error 403 (PermissionDenied)."""
        self.client.login(username='docente_simple', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(response.status_code, 403)

    def test_consulta_auditoria_denegada_a_estudiante(self):
        """Un estudiante sin privilegios recibe error 403 (PermissionDenied)."""
        self.client.login(username='estudiante_simple', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(response.status_code, 403)

    def test_consulta_auditoria_permitida_a_administrador(self):
        """El administrador institucional tiene acceso pleno de solo lectura a la bitácora."""
        self.client.login(username='admin_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bitácora Institucional de Auditoría')
        self.assertContains(response, 'Modo Solo Lectura')
        self.assertContains(response, 'CREAR_EVENTO')
        self.assertContains(response, 'CANCELAR_EVENTO')
        self.assertContains(response, '192.168.1.10')

        # Verificar que la consulta genera su propio registro de auditoría
        log_consulta = Auditoria.objects.filter(accion='CONSULTA_AUDITORIA').first()
        self.assertIsNotNone(log_consulta)
        self.assertEqual(log_consulta.usuario, self.admin_user)

    def test_consulta_auditoria_permitida_a_staff(self):
        """Un usuario con bandera is_staff puede consultar la bitácora."""
        self.client.login(username='staff_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bitácora Institucional de Auditoría')

    def test_filtrado_por_modulo(self):
        """El filtro por módulo limita los resultados estrictamente al módulo seleccionado."""
        self.client.login(username='admin_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'), {'modulo': 'ASISTENCIA'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'REGISTRAR_LLEGADA_QR')
        self.assertNotContains(response, 'CREAR_EVENTO')

    def test_filtrado_por_accion(self):
        """El filtro por acción busca coincidencias en el código de acción."""
        self.client.login(username='admin_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'), {'accion': 'CANCELAR'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CANCELAR_EVENTO')
        self.assertNotContains(response, 'REGISTRAR_LLEGADA_QR')

    def test_filtrado_por_usuario(self):
        """El filtro por usuario permite localizar acciones realizadas por un usuario específico."""
        self.client.login(username='admin_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'), {'usuario': 'docente_simple'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CREAR_EVENTO')
        self.assertContains(response, 'REGISTRAR_LLEGADA_QR')

    def test_filtrado_por_busqueda_general_o_ip(self):
        """La búsqueda libre (q) filtra por descripción o dirección IP."""
        self.client.login(username='admin_auditor', password='Password123*')
        response = self.client.get(reverse('auditoria:consulta_auditoria'), {'q': '10.0.0.1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CANCELAR_EVENTO')
        self.assertNotContains(response, '192.168.1.10')

    def test_paginacion_de_registros(self):
        """La bitácora página adecuadamente cuando hay más de 25 registros."""
        self.client.login(username='admin_auditor', password='Password123*')

        # Crear 30 registros adicionales
        for i in range(30):
            Auditoria.objects.create(
                usuario=self.admin_user,
                modulo='AUDITORIA_TEST',
                accion=f'ACCION_TEST_{i}',
                registro_afectado=f'Registro de prueba número {i}',
                ip='127.0.0.1'
            )

        response_p1 = self.client.get(reverse('auditoria:consulta_auditoria'), {'page': 1})
        self.assertEqual(response_p1.status_code, 200)
        self.assertEqual(len(response_p1.context['page_obj']), 25)
        self.assertTrue(response_p1.context['page_obj'].has_next())

        response_p2 = self.client.get(reverse('auditoria:consulta_auditoria'), {'page': 2})
        self.assertEqual(response_p2.status_code, 200)
        self.assertTrue(response_p2.context['page_obj'].has_previous())


class HealthCheckEndpointTests(TestCase):
    """
    Pruebas automatizadas para el endpoint de monitoreo de disponibilidad institucional /health/ (RNF-06).
    Verifica estado HTTP 200 ante BD operativa y HTTP 503 ante caída de BD,
    certificando la no exposición de datos sensibles ni credenciales.
    """

    def setUp(self):
        self.client = Client()

    def test_health_check_satisfactorio_retorna_200(self):
        """La solicitud GET /health/ con la base operativa retorna HTTP 200 y JSON estructurado."""
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('database'), 'connected')
        self.assertIn('timestamp', data)
        # Verificar que no expone cadenas de conexión ni contraseñas
        self.assertNotIn('password', str(data).lower())
        self.assertNotIn('secret', str(data).lower())

    def test_health_check_falla_base_datos_retorna_503_sin_filtrar_secretos(self):
        """Ante falla de base de datos, GET /health/ retorna HTTP 503 sin exponer trazas ni contraseñas."""
        from unittest.mock import patch
        from django.db import OperationalError

        with patch('django.db.connection.cursor', side_effect=OperationalError("Connection to postgresql://user:SecretPass123@db:5432 failed")):
            response = self.client.get(reverse('health_check'))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response['Content-Type'], 'application/json')
            data = response.json()
            self.assertEqual(data.get('status'), 'unhealthy')
            self.assertEqual(data.get('database'), 'unavailable')
            # Comprobación de seguridad: NO debe existir información de excepción ni contraseñas filtradas
            content = response.content.decode('utf-8')
            self.assertNotIn('SecretPass123', content)
            self.assertNotIn('Traceback', content)
            self.assertNotIn('OperationalError', content)
