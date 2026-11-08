import datetime
import time
from unittest.mock import patch
from django.core.exceptions import ValidationError, PermissionDenied
from django.core import signing
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from usuarios.models import Rol, Usuario
from eventos.models import CategoriaEvento, Evento, ModalidadEvento, EstadoEvento, ModalidadInscripcion
from participantes.models import Participante, Inscripcion, TipoParticipante, EstadoInscripcion, AccesoExternoInscripcion
from asistencia.models import Asistencia, MetodoAsistencia, EstadoAsistencia, ControlSalidaEvento
from asistencia.services import (
    generar_token_qr,
    decodificar_token_qr,
    generar_imagen_qr_bytes,
    registrar_asistencia_llegada,
    registrar_asistencia_salida,
    generar_token_salida_evento,
    decodificar_token_salida_evento,
    validar_token_salida_evento,
    iniciar_sesion_salida_service,
    cerrar_sesion_salida_service,
    rotar_nonce_salida_service,
    es_salida_habilitada,
    toggle_salidas_evento_service,
    calcular_permanencia_promedio,
    construir_url_salida_evento,
    MAX_AGE_QR_LLEGADA,
    MAX_AGE_QR_SALIDA,
)
from auditoria.models import Auditoria


class AsistenciaModelTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='organizador_test',
            email='organizador@test.edu',
            password='TestPassword123*',
            documento='20202020',
            nombres='María',
            apellidos='López',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Taller')
        self.evento = Evento.objects.create(
            nombre='Taller de Django',
            descripcion='Taller práctico',
            fecha=datetime.date(2026, 11, 25),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(18, 0),
            lugar='Laboratorio 3',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=30,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )
        self.participante = Participante.objects.create(
            tipo=TipoParticipante.EXTERNO,
            documento='70707070',
            nombres='Pedro',
            apellidos='Gómez',
            correo='pedro@gmail.com'
        )
        self.inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante,
            estado=EstadoInscripcion.ACTIVA
        )

    def test_registro_asistencia_valida(self):
        """Registro exitoso de asistencia y verificación de propiedad asistio."""
        self.assertFalse(self.inscripcion.asistio)
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(14, 5),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self.inscripcion.refresh_from_db()
        self.assertTrue(self.inscripcion.asistio)
        self.assertEqual(self.inscripcion.asistencia, asistencia)

    def test_asistencia_anulada_no_cuenta_como_asistio(self):
        """Una asistencia en estado ANULADA debe reflejar asistio=False."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(14, 5),
            metodo=MetodoAsistencia.MANUAL,
            estado=EstadoAsistencia.ANULADA
        )
        self.inscripcion.refresh_from_db()
        self.assertFalse(self.inscripcion.asistio)

    def test_rechazo_doble_asistencia_misma_inscripcion_db(self):
        """La base de datos rechaza registrar dos asistencias para la misma inscripción (OneToOne)."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(14, 5),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        with self.assertRaises(IntegrityError):
            Asistencia.objects.create(
                inscripcion=self.inscripcion,
                fecha=self.evento.fecha,
                hora_entrada=datetime.time(14, 10),
                metodo=MetodoAsistencia.MANUAL,
                estado=EstadoAsistencia.REGISTRADA
            )

    def test_validacion_clean_doble_asistencia(self):
        """El método clean() detecta que la inscripción ya tiene asistencia."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(14, 5),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        segunda = Asistencia(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(14, 15),
            metodo=MetodoAsistencia.MANUAL
        )
        with self.assertRaises(ValidationError) as ctx:
            segunda.clean()
        self.assertIn('inscripcion', ctx.exception.message_dict)

    def test_propiedad_es_valida(self):
        """Verifica la propiedad es_valida para estados REGISTRADA y ANULADA."""
        asistencia = Asistencia(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            estado=EstadoAsistencia.REGISTRADA
        )
        self.assertTrue(asistencia.es_valida)

        asistencia.estado = EstadoAsistencia.ANULADA
        self.assertFalse(asistencia.es_valida)


class AsistenciaServiciosTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Coordinador')
        self.usuario = Usuario.objects.create_user(
            username='user_serv',
            email='user_serv@test.edu',
            password='TestPassword123*',
            documento='12345678',
            nombres='Carlos',
            apellidos='Servicio',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Académico')
        self.evento = Evento.objects.create(
            nombre='Conferencia de Ciberseguridad',
            descripcion='Seguridad informática.',
            fecha=datetime.date(2026, 11, 30),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio B',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.usuario
        )
        self.participante = Participante.objects.create(
            usuario=self.usuario,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.usuario.documento,
            nombres=self.usuario.nombres,
            apellidos=self.usuario.apellidos,
            correo=self.usuario.email
        )
        self.inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante,
            estado=EstadoInscripcion.ACTIVA
        )

    def test_generar_y_validar_token_qr_valido(self):
        """Un token QR firmado se genera correctamente y decodifica el payload esperado."""
        token = generar_token_qr(self.inscripcion)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

        payload = decodificar_token_qr(token)
        self.assertEqual(payload['ins'], self.inscripcion.pk)
        self.assertEqual(payload['evt'], self.evento.pk)

    def test_token_qr_adulterado_rechazado(self):
        """Cualquier alteración en el token firmado lanza BadSignature."""
        token = generar_token_qr(self.inscripcion)
        token_adulterado = token[:-5] + 'XXXXX'
        with self.assertRaises(signing.BadSignature):
            decodificar_token_qr(token_adulterado)

    def test_generar_imagen_qr_bytes_png(self):
        """La generación de imagen QR en memoria produce bytes válidos con cabecera PNG."""
        token = generar_token_qr(self.inscripcion)
        qr_bytes = generar_imagen_qr_bytes(token, formato='PNG')
        self.assertIsInstance(qr_bytes, bytes)
        self.assertGreater(len(qr_bytes), 100)
        # Firma binaria estándar de un archivo PNG
        self.assertTrue(qr_bytes.startswith(b'\x89PNG\r\n\x1a\n'))


class AsistenciaDigitalPortalTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.organizador = Usuario.objects.create_user(
            username='docente_organizador',
            email='organizador@uniminuto.edu.co',
            password='TestPassword123*',
            documento='88888888',
            nombres='Docente',
            apellidos='Titular',
            rol=self.rol_docente
        )

        self.otro_docente = Usuario.objects.create_user(
            username='otro_docente',
            email='otro@uniminuto.edu.co',
            password='TestPassword123*',
            documento='77777777',
            nombres='Otro',
            apellidos='Docente',
            rol=self.rol_docente
        )

        self.estudiante = Usuario.objects.create_user(
            username='estudiante_asist',
            email='estudiante@uniminuto.edu.co',
            password='TestPassword123*',
            documento='55555555',
            nombres='Estudiante',
            apellidos='Asistente',
            rol=self.rol_estudiante
        )

        self.otro_estudiante = Usuario.objects.create_user(
            username='estudiante_ajeno',
            email='ajeno@uniminuto.edu.co',
            password='TestPassword123*',
            documento='66666666',
            nombres='Estudiante',
            apellidos='Ajeno',
            rol=self.rol_estudiante
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Seminario')

        self.evento = Evento.objects.create(
            nombre='Simposio de Innovación Educativa',
            descripcion='Simposio académico.',
            fecha=datetime.date(2026, 12, 5),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Auditorio San Juan Eudes',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )

        self.otro_evento = Evento.objects.create(
            nombre='Festival de Teatro Universitario',
            descripcion='Evento cultural.',
            fecha=datetime.date(2026, 12, 6),
            hora_inicio=datetime.time(15, 0),
            hora_fin=datetime.time(18, 0),
            lugar='Teatro UNIMINUTO',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=80,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.otro_docente
        )

        self.participante = Participante.objects.create(
            usuario=self.estudiante,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.estudiante.documento,
            nombres=self.estudiante.nombres,
            apellidos=self.estudiante.apellidos,
            correo=self.estudiante.email
        )

        self.inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante,
            estado=EstadoInscripcion.ACTIVA
        )

        self.inscripcion_otro_evento = Inscripcion.objects.create(
            evento=self.otro_evento,
            participante=self.participante,
            estado=EstadoInscripcion.ACTIVA
        )

    def test_pase_digital_visualizacion_participante(self):
        """Un participante autenticado puede visualizar su propio pase digital con código QR."""
        self.client.login(username='estudiante_asist', password='TestPassword123*')
        response = self.client.get(reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(response, self.evento.nombre)
        self.assertContains(response, self.participante.nombres)
        self.assertContains(response, 'data:image/png;base64,')

    def test_pase_digital_rechazo_usuario_ajeno(self):
        """Un usuario no puede visualizar el pase digital de otra persona (403)."""
        self.client.login(username='estudiante_ajeno', password='TestPassword123*')
        response = self.client.get(reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion.pk}))
        self.assertEqual(response.status_code, 403)

    def test_pase_digital_anonimo_con_token_valido(self):
        """Un participante no autenticado puede visualizar su pase digital si presenta un token firmado válido."""
        token = generar_token_qr(self.inscripcion)
        url = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion.pk}) + f"?token={token}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(response, 'data:image/png;base64,')
        self.assertContains(response, '← Volver al Evento')

    def test_descarga_qr_imagen_png_anonimo_con_token_valido(self):
        """Un participante no autenticado puede descargar la imagen PNG si presenta un token válido."""
        token = generar_token_qr(self.inscripcion)
        url = reverse('asistencia:qr_imagen', kwargs={'id_inscripcion': self.inscripcion.pk}) + f"?token={token}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_pase_digital_anonimo_con_token_invalido_rechazado(self):
        """Un participante no autenticado con token alterado o inválido es rechazado con 403."""
        url = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion.pk}) + "?token=token_falso_manipulado"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_pase_digital_anonimo_con_token_otro_evento_rechazado(self):
        """Un participante con token perteneciente a otra inscripción o evento es rechazado con 403."""
        token_otro = generar_token_qr(self.inscripcion_otro_evento)
        url = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion.pk}) + f"?token={token_otro}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_descarga_qr_imagen_png(self):
        """El endpoint de descarga de imagen QR retorna un archivo PNG binario válido."""
        self.client.login(username='estudiante_asist', password='TestPassword123*')
        response = self.client.get(reverse('asistencia:qr_imagen', kwargs={'id_inscripcion': self.inscripcion.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_control_asistencia_anonimo_redirige_login(self):
        """Un usuario anónimo que intenta acceder al control de asistencia es redirigido al login."""
        response = self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('usuarios:login'), response.url)

    def test_control_asistencia_denegado_usuario_sin_permiso(self):
        """Un estudiante o docente ajeno al evento no puede acceder al panel de control de asistencia (403)."""
        # Estudiante
        self.client.login(username='estudiante_asist', password='TestPassword123*')
        resp_est = self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(resp_est.status_code, 403)

        # Otro docente (no es organizador ni admin)
        self.client.login(username='otro_docente', password='TestPassword123*')
        resp_doc = self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(resp_doc.status_code, 403)

    def test_registro_asistencia_qr_exitoso_con_auditoria(self):
        """El organizador escanea un QR válido; se crea Asistencia y se registra auditoría."""
        self.client.login(username='docente_organizador', password='TestPassword123*')
        token = generar_token_qr(self.inscripcion)

        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_REGISTRADA')
        self.assertIn(self.participante.nombres, data['participante'])

        # Verificar en base de datos
        self.inscripcion.refresh_from_db()
        self.assertTrue(self.inscripcion.asistio)
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion)
        self.assertEqual(asistencia.metodo, MetodoAsistencia.QR)
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.organizador,
            accion='REGISTRAR_ASISTENCIA',
            modulo='ASISTENCIA'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn(str(self.inscripcion.pk), auditoria.registro_afectado)

    def test_registro_asistencia_rechazo_evento_distinto(self):
        """Un código QR de otro evento presentado en este evento es rechazado."""
        self.client.login(username='docente_organizador', password='TestPassword123*')
        # Token del otro evento
        token_otro = generar_token_qr(self.inscripcion_otro_evento)

        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token_otro},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'EVENTO_INCORRECTO')

        # No debe haber registrado asistencia
        self.assertFalse(Asistencia.objects.filter(inscripcion=self.inscripcion_otro_evento).exists())

    def test_registro_asistencia_rechazo_inscripcion_cancelada(self):
        """Una inscripción cancelada es rechazada al intentar registrar asistencia por QR."""
        self.inscripcion.estado = EstadoInscripcion.CANCELADA
        self.inscripcion.save()

        self.client.login(username='docente_organizador', password='TestPassword123*')
        token = generar_token_qr(self.inscripcion)

        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'INSCRIPCION_NO_ACTIVA')
        self.assertIn('No admite registro de asistencia', data['mensaje'])

    def test_registro_asistencia_prevencion_duplicada(self):
        """Un segundo escaneo para un participante que ya tiene asistencia registrada no duplica el registro."""
        self.client.login(username='docente_organizador', password='TestPassword123*')
        token = generar_token_qr(self.inscripcion)

        # Primer escaneo exitoso
        self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Segundo escaneo
        resp_segundo = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_segundo.status_code, 200)
        data = resp_segundo.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_DUPLICADA')
        self.assertIn('ya registró su asistencia', data['mensaje'])

        # Solo existe 1 registro en BD
        self.assertEqual(Asistencia.objects.filter(inscripcion=self.inscripcion).count(), 1)

    def test_registro_asistencia_reactivacion_asistencia_anulada(self):
        """Una asistencia previamente anulada puede ser reactivada por el organizador."""
        # Crear asistencia anulada
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=datetime.date(2026, 12, 5),
            hora_entrada=datetime.time(9, 10),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.ANULADA
        )
        self.assertFalse(self.inscripcion.asistio)

        self.client.login(username='docente_organizador', password='TestPassword123*')
        token = generar_token_qr(self.inscripcion)

        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_REACTIVADA')

        # Verificar en base de datos
        asistencia.refresh_from_db()
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)
        self.assertTrue(self.inscripcion.asistio)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.organizador,
            accion='REACTIVAR_ASISTENCIA',
            modulo='ASISTENCIA'
        ).first()
        self.assertIsNotNone(auditoria)

    def test_registro_asistencia_manual_exitoso(self):
        """El organizador puede registrar asistencia manualmente buscando al participante."""
        self.client.login(username='docente_organizador', password='TestPassword123*')

        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {
                'accion': 'registrar_manual',
                'id_inscripcion': self.inscripcion.pk,
                'observaciones': 'Ingreso manual por falla de batería en móvil'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])

        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion)
        self.assertEqual(asistencia.metodo, MetodoAsistencia.MANUAL)
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)
        self.assertIn('Ingreso manual', asistencia.observaciones)

    def test_anular_asistencia_por_organizador(self):
        """El organizador puede anular una asistencia y se registra auditoría."""
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=datetime.date(2026, 12, 5),
            hora_entrada=datetime.time(9, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self.assertTrue(self.inscripcion.asistio)

        self.client.login(username='docente_organizador', password='TestPassword123*')
        response = self.client.post(
            reverse('asistencia:anular_asistencia', kwargs={'id_asistencia': asistencia.pk}),
            {'motivo': 'Error de digitación'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        asistencia.refresh_from_db()
        self.assertEqual(asistencia.estado, EstadoAsistencia.ANULADA)
        self.assertFalse(self.inscripcion.asistio)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.organizador,
            accion='ANULAR_ASISTENCIA',
            modulo='ASISTENCIA'
        ).first()
        self.assertIsNotNone(auditoria)

    def test_anular_asistencia_denegado_usuario_no_autorizado(self):
        """Un usuario no organizador no puede anular asistencias (403)."""
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=datetime.date(2026, 12, 5),
            hora_entrada=datetime.time(9, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )

        self.client.login(username='otro_docente', password='TestPassword123*')
        response = self.client.post(
            reverse('asistencia:anular_asistencia', kwargs={'id_asistencia': asistencia.pk}),
            {'motivo': 'Intento no autorizado'}
        )
        self.assertEqual(response.status_code, 403)
        asistencia.refresh_from_db()
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)

    def test_busqueda_manual_filtrado(self):
        """La búsqueda manual por GET filtra por documento o nombres de participante."""
        self.client.login(username='docente_organizador', password='TestPassword123*')

        # Búsqueda por documento existente
        resp = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'q': '55555555'}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Asistente, Estudiante')

        # Búsqueda inexistente
        resp_vacia = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'q': '99999999'}
        )
        self.assertEqual(resp_vacia.status_code, 200)
        self.assertContains(resp_vacia, 'No se encontraron inscripciones')

    def test_registrar_salida_exitosa_calculo_permanencia(self):
        """(RF-12) Registra salida con cálculo exacto de permanencia en horas y minutos."""
        self.client.login(username='docente_organizador', password='TestPassword123*')

        # 1. Registrar entrada a las 09:00
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self.assertIsNone(asistencia.hora_salida)
        self.assertIsNone(asistencia.permanencia)

        # 2. Registrar salida a las 11:45 (2h 45m de permanencia)
        res_salida = registrar_asistencia_salida(
            inscripcion=self.inscripcion,
            operador=self.organizador,
            hora_salida_custom=datetime.time(11, 45)
        )
        self.assertTrue(res_salida['exito'])
        asistencia_salida = res_salida['asistencia']

        self.assertEqual(asistencia_salida.hora_salida, datetime.time(11, 45))
        self.assertEqual(asistencia_salida.permanencia['horas'], 2)
        self.assertEqual(asistencia_salida.permanencia['minutos'], 45)
        self.assertEqual(asistencia_salida.tiempo_permanencia_str, '2h 45m')

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.organizador,
            accion='REGISTRAR_SALIDA_ASISTENCIA',
            modulo='ASISTENCIA'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn('2h 45m', auditoria.registro_afectado)

    def test_registrar_salida_sin_asistencia_o_anulada_falla(self):
        """(RF-12) No se puede registrar salida de una asistencia inexistente o anulada."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 30),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.ANULADA
        )
        res = registrar_asistencia_salida(
            inscripcion=self.inscripcion,
            operador=self.organizador,
            hora_salida_custom=datetime.time(10, 0)
        )
        self.assertFalse(res['exito'])
        self.assertEqual(res['codigo'], 'ASISTENCIA_NO_REGISTRADA')

    def test_impedir_doble_salida_para_misma_asistencia(self):
        """(RF-12) Impide registrar dos salidas para una misma asistencia sin corrección previa."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        # Primera salida exitosa
        res_1 = registrar_asistencia_salida(
            inscripcion=self.inscripcion,
            operador=self.organizador,
            hora_salida_custom=datetime.time(10, 0)
        )
        self.assertTrue(res_1['exito'])

        # Segunda salida debe ser rechazada
        res_2 = registrar_asistencia_salida(
            inscripcion=self.inscripcion,
            operador=self.organizador,
            hora_salida_custom=datetime.time(11, 0)
        )
        self.assertFalse(res_2['exito'])
        self.assertEqual(res_2['codigo'], 'SALIDA_YA_REGISTRADA')
        self.assertIn('ya fue registrada', res_2['mensaje'].lower())

    def test_permanencia_evento_cruza_medianoche(self):
        """(RF-12) Calcula correctamente la permanencia en eventos nocturnos que cruzan la medianoche."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(22, 30),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        # Salida al día siguiente a las 02:15
        res_salida = registrar_asistencia_salida(
            inscripcion=self.inscripcion,
            operador=self.organizador,
            hora_salida_custom=datetime.time(2, 15)
        )
        self.assertTrue(res_salida['exito'])
        asistencia_salida = res_salida['asistencia']
        # 22:30 a 02:15 = 3 horas y 45 minutos
        self.assertEqual(asistencia_salida.permanencia['horas'], 3)
        self.assertEqual(asistencia_salida.permanencia['minutos'], 45)
        self.assertEqual(asistencia_salida.tiempo_permanencia_str, '3h 45m')

    def test_control_asistencia_post_salida_via_web(self):
        """(RF-12) La consola web procesa peticiones de salida tanto manuales como por QR."""
        self.client.login(username='docente_organizador', password='TestPassword123*')

        # Primero registrar entrada
        res_llegada = registrar_asistencia_llegada(
            inscripcion=self.inscripcion,
            operador=self.organizador
        )
        asistencia = res_llegada['asistencia']

        # Petición POST con tipo_registro=salida
        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {
                'id_inscripcion': self.inscripcion.pk,
                'tipo_registro': 'salida'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['tipo_registro'], 'salida')
        self.assertIn('permanencia', data)

        asistencia.refresh_from_db()
        self.assertIsNotNone(asistencia.hora_salida)
        self.assertIsNotNone(asistencia.permanencia)

    def test_control_asistencia_filtros_asistencia_y_ausentes(self):
        """Los filtros de control de asistencia discriminan correctamente entre todos, asistentes y ausentes (incluyendo asistencias anuladas)."""
        from participantes.models import Participante, TipoParticipante

        self.client.login(username='docente_organizador', password='TestPassword123*')

        # 1. self.inscripcion ya tiene asistencia registrada
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )

        # 2. Participante ausente sin registro de asistencia
        part_ausente = Participante.objects.create(
            documento='66554433',
            nombres='Mario',
            apellidos='AusenteTotal',
            correo='mario@ausente.org',
            tipo=TipoParticipante.EXTERNO
        )
        insc_ausente = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_ausente,
            estado=EstadoInscripcion.ACTIVA
        )

        # 3. Participante con asistencia anulada (debe contar como ausente)
        part_anulado = Participante.objects.create(
            documento='55443322',
            nombres='Elena',
            apellidos='AnuladaAsistencia',
            correo='elena@anulada.org',
            tipo=TipoParticipante.EXTERNO
        )
        insc_anulada = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_anulado,
            estado=EstadoInscripcion.ACTIVA
        )
        Asistencia.objects.create(
            inscripcion=insc_anulada,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 10),
            metodo=MetodoAsistencia.MANUAL,
            estado=EstadoAsistencia.ANULADA,
            observaciones='Anulado por error de operador'
        )

        # 4. Participante con inscripción cancelada
        part_cancelado = Participante.objects.create(
            documento='44332211',
            nombres='Roberto',
            apellidos='InscripcionCancelada',
            correo='roberto@cancelado.org',
            tipo=TipoParticipante.EXTERNO
        )
        insc_cancelada = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_cancelado,
            estado=EstadoInscripcion.CANCELADA
        )

        # CONSULTA 1: Filtro 'todos'
        resp_todos = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'todos'}
        )
        self.assertEqual(resp_todos.status_code, 200)
        self.assertEqual(resp_todos.context['total_inscritos'], 3)  # Activos: self.inscripcion, insc_ausente, insc_anulada
        self.assertEqual(resp_todos.context['total_asistieron'], 1)  # Solo self.inscripcion
        self.assertEqual(resp_todos.context['total_ausentes'], 2)  # insc_ausente e insc_anulada

        # CONSULTA 2: Filtro 'asistieron'
        resp_asistieron = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'asistieron'}
        )
        self.assertEqual(resp_asistieron.status_code, 200)
        ids_mostrados = [i.pk for i in resp_asistieron.context['inscripciones']]
        self.assertIn(self.inscripcion.pk, ids_mostrados)
        self.assertNotIn(insc_ausente.pk, ids_mostrados)
        self.assertNotIn(insc_anulada.pk, ids_mostrados)
        self.assertNotIn(insc_cancelada.pk, ids_mostrados)

        # CONSULTA 3: Filtro 'ausentes'
        resp_ausentes = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'ausentes'}
        )
        self.assertEqual(resp_ausentes.status_code, 200)
        ids_ausentes = [i.pk for i in resp_ausentes.context['inscripciones']]
        self.assertIn(insc_ausente.pk, ids_ausentes)
        self.assertIn(insc_anulada.pk, ids_ausentes)
        self.assertNotIn(self.inscripcion.pk, ids_ausentes)
        self.assertNotIn(insc_cancelada.pk, ids_ausentes)

        # CONSULTA 4: Filtro 'ausentes' combinado con búsqueda textual 'q=Elena'
        resp_ausentes_q = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'ausentes', 'q': 'Elena'}
        )
        self.assertEqual(resp_ausentes_q.status_code, 200)
        ids_q = [i.pk for i in resp_ausentes_q.context['inscripciones']]
        self.assertEqual(ids_q, [insc_anulada.pk])


class AsistenciaFlujoQRSalidaTests(TestCase):
    """
    Suite de pruebas correspondiente a la FASE 7 del flujo de asistencia:
    1. Entrada QR válida.
    2. Entrada manual válida.
    3. Entrada duplicada.
    4. QR inválido o manipulado.
    5. QR de salida válido.
    6. Salida sin entrada previa.
    7. Salida duplicada.
    8. Salida con el registro deshabilitado.
    9. Intento de registrar la salida de otra persona / documento no vinculado.
    10. QR de salida de otro evento.
    11. Actualización de las métricas y filtros.
    12. Cálculo correcto de permanencia.
    13. Conservación de la auditoría y los permisos.
    """
    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.organizador = Usuario.objects.create_user(
            username='org_salida',
            email='org_salida@uniminuto.edu.co',
            password='TestPassword123*',
            documento='10101010',
            nombres='Paula',
            apellidos='Organizadora',
            rol=self.rol_docente
        )

        self.otro_usuario = Usuario.objects.create_user(
            username='otro_usuario',
            email='otro_usuario@uniminuto.edu.co',
            password='TestPassword123*',
            documento='20202021',
            nombres='Pedro',
            apellidos='Ajeno',
            rol=self.rol_estudiante
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Innovación')
        self.evento = Evento.objects.create(
            nombre='Seminario de Inteligencia Artificial',
            descripcion='Conferencia magistral.',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio Central',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )

        self.evento_b = Evento.objects.create(
            nombre='Congreso de Robótica',
            descripcion='Congreso paralelo.',
            fecha=datetime.date(2026, 12, 11),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(18, 0),
            lugar='Salón 201',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )

        # Participante A: Con cuenta
        self.estudiante_a = Usuario.objects.create_user(
            username='estudiante_a',
            email='estudiante_a@uniminuto.edu.co',
            password='TestPassword123*',
            documento='30303030',
            nombres='Andrés',
            apellidos='Castro',
            rol=self.rol_estudiante
        )
        self.part_a = Participante.objects.create(
            usuario=self.estudiante_a,
            tipo=TipoParticipante.ESTUDIANTE,
            documento='30303030',
            nombres='Andrés',
            apellidos='Castro',
            correo='estudiante_a@uniminuto.edu.co'
        )
        self.insc_a = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_a,
            estado=EstadoInscripcion.ACTIVA
        )

        # Participante B: Externo (sin usuario)
        self.part_b = Participante.objects.create(
            tipo=TipoParticipante.EXTERNO,
            documento='40404040',
            nombres='Beatriz',
            apellidos='Díaz',
            correo='beatriz@gmail.com'
        )
        self.insc_b = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_b,
            estado=EstadoInscripcion.ACTIVA
        )
        self.acceso_b, self.token_acceso_b = AccesoExternoInscripcion.crear_para_inscripcion(self.insc_b)

    def _autenticar_sesion_externa(self, acceso):
        session = self.client.session
        session['acceso_externo_id'] = acceso.pk
        session.save()

    def test_01_entrada_qr_valida(self):
        """1. Entrada QR válida: registra llegada, método QR, estado REGISTRADA y auditoría."""
        self.client.login(username='org_salida', password='TestPassword123*')
        token = generar_token_qr(self.insc_a)
        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token, 'tipo_registro': 'entrada'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_REGISTRADA')
        self.assertIn('Castro', data['participante'])

        asistencia = Asistencia.objects.get(inscripcion=self.insc_a)
        self.assertEqual(asistencia.metodo, MetodoAsistencia.QR)
        self.assertTrue(asistencia.es_valida)
        self.assertIsNotNone(asistencia.hora_entrada)

    def test_02_entrada_manual_valida(self):
        """2. Entrada manual válida: registra llegada vía formulario de búsqueda manual."""
        self.client.login(username='org_salida', password='TestPassword123*')
        response = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'accion': 'registrar_manual', 'id_inscripcion': self.insc_b.pk, 'tipo_registro': 'entrada'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        asistencia = Asistencia.objects.get(inscripcion=self.insc_b)
        self.assertEqual(asistencia.metodo, MetodoAsistencia.MANUAL)
        self.assertTrue(asistencia.es_valida)

    def test_03_entrada_duplicada(self):
        """3. Entrada duplicada: rechaza un segundo registro de entrada con código ASISTENCIA_DUPLICADA."""
        self.client.login(username='org_salida', password='TestPassword123*')
        token = generar_token_qr(self.insc_a)
        # Primer registro
        self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token, 'tipo_registro': 'entrada'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        # Intento duplicado
        resp_dup = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': token, 'tipo_registro': 'entrada'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_dup.status_code, 200)
        data = resp_dup.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_DUPLICADA')

    def test_04_qr_invalido_o_manipulado(self):
        """4. QR inválido o manipulado: rechaza tokens alterados o corruptos."""
        self.client.login(username='org_salida', password='TestPassword123*')
        resp = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': 'token_totalmente_falso_y_manipulado:123', 'tipo_registro': 'entrada'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'QR_INVALIDO')

    def test_05_qr_de_salida_valido_y_descarga(self):
        """5. QR de salida válido: token decodifica evento correcto, página pública carga y PNG se descarga."""
        token = generar_token_salida_evento(self.evento)
        payload = decodificar_token_salida_evento(token)
        self.assertEqual(payload['evt'], self.evento.pk)

        # Carga de la página pública de salida con token
        url_salida = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"
        resp_pagina = self.client.get(url_salida)
        self.assertEqual(resp_pagina.status_code, 200)
        self.assertContains(resp_pagina, 'Control de Salida del Evento')
        self.assertContains(resp_pagina, self.evento.nombre)

        # Descarga de la imagen QR de salida por el organizador
        self.client.login(username='org_salida', password='TestPassword123*')
        resp_img = self.client.get(reverse('asistencia:descargar_qr_salida_imagen', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(resp_img.status_code, 200)
        self.assertEqual(resp_img['Content-Type'], 'image/png')
        self.assertTrue(resp_img.content.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_06_salida_sin_entrada_previa(self):
        """6. Salida sin entrada previa: rechaza el check-out si el participante no registró su llegada."""
        self._autenticar_sesion_externa(self.acceso_b)
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"
        # Participante B (externo con sesión) intenta salida sin tener entrada
        resp = self.client.post(url, {'token_evento': token})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'no cuenta con un registro de entrada previo válido')
        self.assertFalse(Asistencia.objects.filter(inscripcion=self.insc_b).exists())

    def test_07_salida_duplicada(self):
        """7. Salida duplicada: rechaza un segundo registro de salida para el mismo participante."""
        # 1. Registrar entrada previa (30 minutos antes del momento actual)
        hora_entrada_ref = (timezone.localtime(timezone.now()) - datetime.timedelta(minutes=30)).time()
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=hora_entrada_ref,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self._autenticar_sesion_externa(self.acceso_b)
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"

        # 2. Primera salida exitosa
        resp1 = self.client.post(url, {'token_evento': token})
        self.assertEqual(resp1.status_code, 200)
        self.assertContains(resp1, '¡Salida Registrada con Éxito!')

        asist = Asistencia.objects.get(inscripcion=self.insc_b)
        self.assertIsNotNone(asist.hora_salida)

        # 3. Segunda salida rechazada
        resp2 = self.client.post(url, {'token_evento': token})
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'ya fue registrada')

    def test_08_salida_con_registro_deshabilitado(self):
        """8. Salida con el registro deshabilitado: si el organizador pausa salidas, se rechaza la salida."""
        # Registrar entrada (30 minutos antes del momento actual)
        hora_entrada_ref = (timezone.localtime(timezone.now()) - datetime.timedelta(minutes=30)).time()
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=hora_entrada_ref,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self._autenticar_sesion_externa(self.acceso_b)
        # Deshabilitar salidas
        toggle_salidas_evento_service(self.evento, habilitar=False, operador=self.organizador)
        self.assertFalse(es_salida_habilitada(self.evento))

        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"

        # La página debe advertir que el registro está deshabilitado
        resp_get = self.client.get(url)
        self.assertContains(resp_get, 'Registro de salidas no disponible')

        # Intento de POST debe ser rechazado
        resp_post = self.client.post(url, {'token_evento': token})
        self.assertContains(resp_post, 'Registro de salidas no disponible')
        asist = Asistencia.objects.get(inscripcion=self.insc_b)
        self.assertIsNone(asist.hora_salida)

    def test_09_intento_salida_manual_sin_sesion_rechazado(self):
        """9. Intento de registrar salida enviando documento manualmente sin sesión es rechazado."""
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"
        # Sin sesión activa, intentar enviar documento manual
        resp = self.client.post(url, {'documento': '99999999', 'token_evento': token})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No se detectó una sesión activa')

    def test_10_qr_salida_otro_evento(self):
        """10. QR de salida de otro evento: rechaza con 403 Forbidden."""
        token_b = generar_token_salida_evento(self.evento_b)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token_b}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_11_actualizacion_metricas_y_filtros(self):
        """11. Métricas y filtros: sin_salida y salieron muestran conteos e inscripciones precisas."""
        self.client.login(username='org_salida', password='TestPassword123*')

        # Inscripción A: con entrada y sin salida
        Asistencia.objects.create(
            inscripcion=self.insc_a,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        # Inscripción B: con entrada y con salida
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 15),
            hora_salida=datetime.time(10, 15),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )

        # Consultar panel con filtro 'sin_salida'
        resp_sin_salida = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'sin_salida'}
        )
        self.assertEqual(resp_sin_salida.status_code, 200)
        self.assertEqual(resp_sin_salida.context['total_sin_salida'], 1)
        self.assertEqual(resp_sin_salida.context['total_salidas'], 1)
        ids_sin_salida = [i.pk for i in resp_sin_salida.context['inscripciones']]
        self.assertIn(self.insc_a.pk, ids_sin_salida)
        self.assertNotIn(self.insc_b.pk, ids_sin_salida)

        # Consultar panel con filtro 'salieron'
        resp_salieron = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'filtro_asistencia': 'salieron'}
        )
        self.assertEqual(resp_salieron.status_code, 200)
        ids_salieron = [i.pk for i in resp_salieron.context['inscripciones']]
        self.assertIn(self.insc_b.pk, ids_salieron)
        self.assertNotIn(self.insc_a.pk, ids_salieron)

    def test_12_calculo_correcto_permanencia_promedio(self):
        """12. Cálculo correcto de permanencia promedio entre todos los participantes con salida."""
        # Participante A: 60 minutos (09:00 a 10:00)
        Asistencia.objects.create(
            inscripcion=self.insc_a,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 0),
            hora_salida=datetime.time(10, 0),
            estado=EstadoAsistencia.REGISTRADA
        )
        # Participante B: 120 minutos (09:00 a 11:00)
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(9, 0),
            hora_salida=datetime.time(11, 0),
            estado=EstadoAsistencia.REGISTRADA
        )
        # Promedio: (60 + 120) / 2 = 90 minutos = 1h 30m
        promedio = calcular_permanencia_promedio(self.evento)
        self.assertEqual(promedio['promedio_minutos'], 90)
        self.assertEqual(promedio['horas'], 1)
        self.assertEqual(promedio['minutos'], 30)
        self.assertEqual(promedio['texto'], '1h 30m')

    def test_13_conservacion_auditoria_y_permisos(self):
        """13. Conservación de auditoría y permisos en el control de salidas."""
        # 1. Usuario no organizador no puede hacer toggle de salidas (403)
        self.client.login(username='otro_usuario', password='TestPassword123*')
        resp_denegada = self.client.post(
            reverse('asistencia:toggle_salidas_evento', kwargs={'id_evento': self.evento.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_denegada.status_code, 403)

        # 2. Organizador autorizado hace toggle exitosamente
        self.client.login(username='org_salida', password='TestPassword123*')
        resp_ok = self.client.post(
            reverse('asistencia:toggle_salidas_evento', kwargs={'id_evento': self.evento.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_ok.status_code, 200)
        data = resp_ok.json()
        self.assertTrue(data['exito'])

        # 3. Verificar registro en el módulo de auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.organizador,
            accion__in=['DESHABILITAR_SALIDAS_EVENTO', 'HABILITAR_SALIDAS_EVENTO', 'TOGGLE_SALIDAS_EVENTO'],
            modulo='ASISTENCIA'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn(str(self.evento.pk), auditoria.registro_afectado)

    def test_14_qr_salida_escaneado_en_lector_operador_rechazado_con_aviso_especifico(self):
        """14. Si el operador escanea el QR común de salida en su lector, se rechaza con mensaje explicativo."""
        self.client.login(username='org_salida', password='TestPassword123*')
        token = generar_token_salida_evento(self.evento)
        url_salida_falsa = f"http://192.168.1.10:8000/asistencia/evento/{self.evento.pk}/salida/?token_evento={token}"
        
        resp = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'token_qr': url_salida_falsa, 'tipo_registro': 'entrada'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'QR_SALIDA_COMUN_NO_ES_PASE')
        self.assertIn('QR común de SALIDA', data['mensaje'])

    def test_15_construir_url_salida_evento_red_local(self):
        """15. La generación de la URL de salida no usa loopback (127.0.0.1) para que sea accesible desde celulares."""
        class MockRequest:
            def get_host(self):
                return '127.0.0.1:8000'
            def is_secure(self):
                return False

        url = construir_url_salida_evento(MockRequest(), self.evento)
        self.assertNotIn('127.0.0.1', url)
        self.assertNotIn('localhost', url)
        self.assertIn(':8000', url)
        self.assertIn('token_evento=', url)
        self.assertIn(f"/asistencia/evento/{self.evento.pk}/salida/", url)

    def test_16_bloqueo_suplantacion_manual_documento_y_correo(self):
        """16. Bloqueo de suplantación: envío de documento y correo manual sin sesión es rechazado."""
        # 1. Registrar entrada previa para participante B
        hora_entrada_ref = (timezone.localtime(timezone.now()) - datetime.timedelta(minutes=30)).time()
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=hora_entrada_ref,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"

        # 2. Atacante sin sesión intenta registrar salida enviando documento y correo manual
        resp = self.client.post(url, {
            'documento': self.part_b.documento,
            'correo': 'correo_atacante@hacker.com',
            'token_evento': token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No se detectó una sesión activa')
        asist = Asistencia.objects.get(inscripcion=self.insc_b)
        self.assertIsNone(asist.hora_salida)

    def test_17_salida_con_sesion_externa_exitosa(self):
        """17. Salida exitosa cuando la identidad validada en sesión (externa) confirma la salida."""
        # 1. Registrar entrada previa
        hora_entrada_ref = (timezone.localtime(timezone.now()) - datetime.timedelta(minutes=30)).time()
        Asistencia.objects.create(
            inscripcion=self.insc_b,
            fecha=self.evento.fecha,
            hora_entrada=hora_entrada_ref,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        self._autenticar_sesion_externa(self.acceso_b)
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"

        # 2. Confirmar salida (incluso si se enviara documento ajeno en POST, se resuelve por sesión)
        resp = self.client.post(url, {
            'documento': 'documento_ignorado',
            'token_evento': token
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '¡Salida Registrada con Éxito!')
        asist = Asistencia.objects.get(inscripcion=self.insc_b)
        self.assertIsNotNone(asist.hora_salida)

    def test_18_salida_con_sesion_institucional_request_user_exitosa(self):
        """18. Salida exitosa para participante institucional autenticado en request.user."""
        hora_entrada_ref = (timezone.localtime(timezone.now()) - datetime.timedelta(minutes=30)).time()
        Asistencia.objects.create(
            inscripcion=self.insc_a,
            fecha=self.evento.fecha,
            hora_entrada=hora_entrada_ref,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA
        )
        token = generar_token_salida_evento(self.evento)
        url = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token={token}"

        self.client.login(username='estudiante_a', password='TestPassword123*')
        resp = self.client.post(url, {'token_evento': token})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '¡Salida Registrada con Éxito!')
        asist = Asistencia.objects.get(inscripcion=self.insc_a)
        self.assertIsNotNone(asist.hora_salida)



class ControlSalidaEventoEstructuraTests(TestCase):
    """
    Pruebas unitarias de la estructura ampliada del modelo ControlSalidaEvento (Etapa 7.1).
    """
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='docente_ctrl',
            email='doc_ctrl@uniminuto.edu.co',
            password='TestPassword123*',
            documento='12345678',
            rol=self.rol
        )
        self.operador_cierre = Usuario.objects.create_user(
            username='operador_cierre',
            email='op_cierre@uniminuto.edu.co',
            password='TestPassword123*',
            documento='87654321',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Institucional')
        self.evento = Evento.objects.create(
            nombre='Jornada Universitaria',
            descripcion='Evento institucional',
            fecha=datetime.date(2026, 11, 30),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Campus Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=150,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )

    def test_campos_ampliados_control_salida_evento(self):
        """Verifica la persistencia de los nuevos campos estructurales de sesión y auditoría."""
        ahora = timezone.now()
        control = ControlSalidaEvento.objects.create(
            evento=self.evento,
            salidas_habilitadas=True,
            fecha_habilitacion=ahora,
            habilitado_por=self.organizador,
            sesion_id='SES-EVT-20261130-XYZ123',
            nonce_vigente='NONCE-ROT-9876543210',
            fecha_cierre=ahora + datetime.timedelta(hours=4),
            cerrado_por=self.operador_cierre
        )
        control.refresh_from_db()
        self.assertEqual(control.sesion_id, 'SES-EVT-20261130-XYZ123')
        self.assertEqual(control.nonce_vigente, 'NONCE-ROT-9876543210')
        self.assertEqual(control.habilitado_por, self.organizador)
        self.assertEqual(control.cerrado_por, self.operador_cierre)
        self.assertIsNotNone(control.fecha_modificacion)

    def test_integridad_onetoone_control_salida_evento(self):
        """Un evento solo puede tener una única instancia de ControlSalidaEvento (primary_key=True / OneToOne)."""
        ControlSalidaEvento.objects.create(
            evento=self.evento,
            salidas_habilitadas=True
        )
        with self.assertRaises(IntegrityError):
            ControlSalidaEvento.objects.create(
                evento=self.evento,
                salidas_habilitadas=False
            )

    def test_compatibilidad_defaults_control_salida(self):
        """Verifica que los nuevos campos admiten valores nulos para garantizar compatibilidad retroactiva."""
        control = ControlSalidaEvento.objects.create(
            evento=self.evento
        )
        self.assertFalse(control.salidas_habilitadas)
        self.assertIsNone(control.sesion_id)
        self.assertIsNone(control.nonce_vigente)
        self.assertIsNone(control.habilitado_por)
        self.assertIsNone(control.cerrado_por)
        self.assertIsNone(control.fecha_habilitacion)
        self.assertIsNone(control.fecha_cierre)

    def test_evento_sin_sesion_iniciada_rechaza_salidas(self):
        """Un evento sin sesión de salida formal iniciada rechaza cualquier intento de registrar salidas."""
        control = ControlSalidaEvento.objects.create(evento=self.evento)
        self.assertFalse(control.salidas_habilitadas)
        self.assertFalse(control.es_sesion_activa('SES-CUALQUIERA-123', 'nonce-invalido'))

    def test_iniciar_sesion_genera_sesion_id_y_nonce(self):
        """iniciar_sesion habilita salidas, genera sesion_id único, nonce y registra operador."""
        control = ControlSalidaEvento.objects.create(
            evento=self.evento,
            salidas_habilitadas=False
        )
        sesion_id, nonce = control.iniciar_sesion(operador=self.organizador)
        self.assertTrue(control.salidas_habilitadas)
        self.assertIsNotNone(sesion_id)
        self.assertIsNotNone(nonce)
        self.assertIn(str(self.evento.pk), sesion_id)
        self.assertEqual(control.habilitado_por, self.organizador)
        self.assertIsNone(control.fecha_cierre)
        self.assertTrue(control.es_sesion_activa(sesion_id, nonce))

    def test_cerrar_sesion_invalida_nonce_y_bloquea_reutilizacion(self):
        """cerrar_sesion invalida de inmediato el nonce vigente y bloquea la sesión."""
        control = ControlSalidaEvento.objects.create(evento=self.evento)
        sesion_id, nonce = control.iniciar_sesion(operador=self.organizador)

        control.cerrar_sesion(operador=self.operador_cierre)
        control.refresh_from_db()

        self.assertFalse(control.salidas_habilitadas)
        self.assertIsNone(control.nonce_vigente)
        self.assertIsNotNone(control.fecha_cierre)
        self.assertEqual(control.cerrado_por, self.operador_cierre)
        self.assertFalse(control.es_sesion_activa(sesion_id, nonce))

    def test_abrir_nueva_sesion_invalida_qr_de_sesion_anterior(self):
        """Al abrir una nueva sesión, ningún QR emitido para la sesión previa es aceptado."""
        control = ControlSalidaEvento.objects.create(evento=self.evento)
        sesion_1, nonce_1 = control.iniciar_sesion(operador=self.organizador)
        control.cerrar_sesion(operador=self.operador_cierre)

        sesion_2, nonce_2 = control.iniciar_sesion(operador=self.organizador)
        self.assertNotEqual(sesion_1, sesion_2)
        self.assertNotEqual(nonce_1, nonce_2)

        # La sesión 1 debe ser rechazada
        self.assertFalse(control.es_sesion_activa(sesion_1, nonce_1))
        # La sesión 2 es la única válida
        self.assertTrue(control.es_sesion_activa(sesion_2, nonce_2))

    def test_rotar_nonce_sesion_activa(self):
        """rotar_nonce actualiza el nonce vigente e invalida de inmediato el nonce anterior."""
        control = ControlSalidaEvento.objects.create(evento=self.evento)
        sesion_id, nonce_orig = control.iniciar_sesion(operador=self.organizador)

        nonce_nuevo = control.rotar_nonce()
        self.assertNotEqual(nonce_orig, nonce_nuevo)
        # El nonce original queda rechazado
        self.assertFalse(control.es_sesion_activa(sesion_id, nonce_orig))
        # El nuevo nonce es aceptado
        self.assertTrue(control.es_sesion_activa(sesion_id, nonce_nuevo))

        # En sesión cerrada no se permite rotar
        control.cerrar_sesion(operador=self.operador_cierre)
        with self.assertRaises(ValidationError):
            control.rotar_nonce()

    def test_unicidad_sesion_id_control_salida(self):
        """La base de datos rechaza duplicados de sesion_id entre diferentes eventos."""
        evento_2 = Evento.objects.create(
            nombre='Segundo Evento Sesion',
            descripcion='Evento para prueba de sesion_id',
            fecha=datetime.date(2026, 12, 1),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sede Norte',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )
        ControlSalidaEvento.objects.create(
            evento=self.evento,
            salidas_habilitadas=True,
            sesion_id='SESION-CLON-123'
        )
        with self.assertRaises(IntegrityError):
            ControlSalidaEvento.objects.create(
                evento=evento_2,
                salidas_habilitadas=True,
                sesion_id='SESION-CLON-123'
            )


class ControlAsistenciaIntegralQRTests(TestCase):
    """
    Suite integral de pruebas unitarias y de integración para la Etapa 7.3:
    Control de asistencia mediante códigos QR para participantes institucionales y externos.
    """

    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        # Organizador / Docente
        self.profesor = Usuario.objects.create_user(
            username='profesor_qr',
            email='profesor_qr@uniminuto.edu.co',
            password='Password123*',
            documento='10101010',
            nombres='Carlos',
            apellidos='Docente',
            rol=self.rol_docente
        )

        # Participante Institucional
        self.usuario_inst = Usuario.objects.create_user(
            username='estudiante_qr',
            email='estudiante_qr@uniminuto.edu.co',
            password='Password123*',
            documento='20202020',
            nombres='Ana',
            apellidos='Estudiante',
            rol=self.rol_estudiante
        )
        self.participante_inst = Participante.objects.create(
            usuario=self.usuario_inst,
            documento='20202020',
            nombres='Ana',
            apellidos='Estudiante',
            correo='estudiante_qr@uniminuto.edu.co',
            tipo=TipoParticipante.ESTUDIANTE,
            institucion='UNIMINUTO'
        )

        # Categoría y Evento Principal
        self.categoria = CategoriaEvento.objects.create(nombre='Congreso de Tecnología')
        self.evento = Evento.objects.create(
            nombre='Simposio Nacional de IA y Ciberseguridad',
            descripcion='Evento académico institucional de gran escala',
            fecha=datetime.date(2026, 11, 20),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(18, 0),
            lugar='Auditorio Principal San Camilo',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        # Segundo evento para verificar aislamiento entre eventos
        self.evento_ajeno = Evento.objects.create(
            nombre='Seminario Ajeno de Robótica',
            descripcion='Otro evento de prueba',
            fecha=datetime.date(2026, 11, 20),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Sede Alterna',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        # Inscripción Institucional en Evento Principal
        self.inscripcion_inst = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante_inst,
            estado=EstadoInscripcion.ACTIVA
        )

        # Participante Externo sin cuenta de usuario
        self.participante_ext = Participante.objects.create(
            documento='99887766',
            nombres='Roberto',
            apellidos='Visitante Externo',
            correo='roberto.visitante@externo.org',
            tipo=TipoParticipante.EXTERNO,
            institucion='Entidad Externa Aliada'
        )
        self.inscripcion_ext = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante_ext,
            estado=EstadoInscripcion.ACTIVA
        )
        self.acceso_ext, self.token_acceso_ext = AccesoExternoInscripcion.crear_para_inscripcion(
            inscripcion=self.inscripcion_ext,
            duracion_dias=10
        )

    def test_01_generacion_qr_dinamico_personal_institucional(self):
        """1. Generación de QR dinámico para participante institucional sin exponer PII."""
        token = generar_token_qr(self.inscripcion_inst)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)

        # Decodificación y validación de payload mínimo sin PII
        payload = decodificar_token_qr(token, max_age=MAX_AGE_QR_LLEGADA)
        self.assertEqual(payload['ins'], self.inscripcion_inst.pk)
        self.assertEqual(payload['evt'], self.evento.pk)

        # No expone documento, correo ni credenciales
        self.assertNotIn('documento', payload)
        self.assertNotIn('doc', payload)
        self.assertNotIn('correo', payload)
        self.assertNotIn('email', payload)
        self.assertNotIn('password', payload)

        # Endpoint AJAX qr-dinamico autenticado
        self.client.force_login(self.usuario_inst)
        url = reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': self.inscripcion_inst.pk})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertIn('qr_base64', data)
        self.assertIn('token', data)
        self.assertFalse(data['llegada_registrada'])

        # Usuario ajeno recibe 403 Forbidden
        otro_usuario = Usuario.objects.create_user(
            username='otro_usuario',
            email='otro@uniminuto.edu.co',
            password='Password123*',
            documento='30303030',
            rol=self.rol_estudiante
        )
        self.client.force_login(otro_usuario)
        res_ajeno = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_ajeno.status_code, 403)

    def test_02_generacion_qr_dinamico_personal_externo(self):
        """2. Generación de QR dinámico para participante externo vía token seguro."""
        url = reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': self.inscripcion_ext.pk})

        # Sin token ni sesión -> 403 Forbidden
        res_anon = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_anon.status_code, 403)

        # Con token de acceso externo válido en querystring
        res_token = self.client.get(f"{url}?token={self.token_acceso_ext}", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_token.status_code, 200)
        data = res_token.json()
        self.assertTrue(data['exito'])
        self.assertIn('qr_base64', data)
        self.assertIn('token', data)

    def test_03_validacion_qr_llegada_vigente(self):
        """3. Validación exitosa de un token QR de llegada dentro de su ventana de vigencia."""
        token = generar_token_qr(self.inscripcion_inst)
        payload = decodificar_token_qr(token, max_age=MAX_AGE_QR_LLEGADA)
        self.assertEqual(payload['ins'], self.inscripcion_inst.pk)
        self.assertEqual(payload['evt'], self.evento.pk)

    def test_04_rechazo_qr_llegada_expirado(self):
        """4. Rechazo estricto de un token QR de llegada expirado por superar MAX_AGE_QR_LLEGADA."""
        with patch('time.time', return_value=time.time() - 200):
            token_expirado = generar_token_qr(self.inscripcion_inst)

        # Decodificación directa arroja SignatureExpired
        with self.assertRaises(signing.SignatureExpired):
            decodificar_token_qr(token_expirado, max_age=MAX_AGE_QR_LLEGADA)

        # En el lector del operador genera error QR_EXPIRADO
        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_control, {'token_qr': token_expirado}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'QR_EXPIRADO')

    def test_05_rechazo_qr_llegada_manipulado_invalido(self):
        """5. Rechazo estricto de un token QR de llegada alterado o con firma rota."""
        token_valido = generar_token_qr(self.inscripcion_inst)
        token_manipulado = token_valido + "hacked"

        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_control, {'token_qr': token_manipulado}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'QR_INVALIDO')

    def test_06_rechazo_qr_llegada_evento_distinto(self):
        """6. Rechazo de un token QR de llegada correspondiente a otro evento."""
        ins_ajena = Inscripcion.objects.create(
            evento=self.evento_ajeno,
            participante=self.participante_inst,
            estado=EstadoInscripcion.ACTIVA
        )
        token_ajeno = generar_token_qr(ins_ajena)

        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_control, {'token_qr': token_ajeno}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'EVENTO_INCORRECTO')

    def test_07_registro_llegada_exitoso(self):
        """7. Registro exitoso de llegada mediante código QR en el escáner del operador."""
        token = generar_token_qr(self.inscripcion_inst)

        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_control, {'token_qr': token}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_REGISTRADA')

        # Verificación en BD
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_inst)
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)
        self.assertIsNotNone(asistencia.hora_entrada)
        self.assertEqual(asistencia.metodo, MetodoAsistencia.QR)
        self.assertIsNone(asistencia.hora_salida)

    def test_08_bloqueo_llegada_duplicada(self):
        """8. Bloqueo de registro de llegada duplicado al intentar escanear el QR dos veces."""
        token = generar_token_qr(self.inscripcion_inst)

        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})

        # Primer escaneo exitoso
        res1 = self.client.post(url_control, {'token_qr': token}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res1.json()['exito'])

        # Segundo escaneo bloqueado
        res2 = self.client.post(url_control, {'token_qr': token}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertFalse(data2['exito'])
        self.assertEqual(data2['codigo'], 'ASISTENCIA_DUPLICADA')

    def test_09_bloqueo_llegada_inscripcion_cancelada(self):
        """9. Bloqueo de registro de llegada si la inscripción se encuentra cancelada."""
        self.inscripcion_inst.estado = EstadoInscripcion.CANCELADA
        self.inscripcion_inst.save()

        token = generar_token_qr(self.inscripcion_inst)

        self.client.force_login(self.profesor)
        url_control = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_control, {'token_qr': token}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'INSCRIPCION_NO_ACTIVA')

    def test_10_inicio_sesion_salida_y_generacion_qr_colectivo(self):
        """10. Inicio formal de sesión de salida colectiva y emisión de QR colectivo de evento."""
        self.client.force_login(self.profesor)
        url_iniciar = reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_iniciar, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertTrue(data['salidas_habilitadas'])
        self.assertIn('token_salida', data)
        self.assertIn('sesion_id', data)

        # Control en BD activo
        control = ControlSalidaEvento.objects.get(evento=self.evento)
        self.assertTrue(control.salidas_habilitadas)
        self.assertIsNotNone(control.sesion_id)
        self.assertIsNotNone(control.nonce_vigente)

        # Validación del token colectivo generado
        valido, payload, err = validar_token_salida_evento(data['token_salida'], self.evento)
        self.assertTrue(valido)
        self.assertEqual(payload['ses'], control.sesion_id)
        self.assertEqual(payload['non'], control.nonce_vigente)

    def test_11_rotacion_nonce_salida(self):
        """11. Rotación del nonce colectivo e invalidación del token previo."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_previo = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.profesor)
        url_rotar = reverse('asistencia:rotar_nonce_salida', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_rotar)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        token_nuevo = data['token_salida']
        self.assertNotEqual(token_previo, token_nuevo)

        # El token previo queda rechazado por nonce inválido
        valido_viejo, _, err_viejo = validar_token_salida_evento(token_previo, self.evento)
        self.assertFalse(valido_viejo)

        # El nuevo token es aceptado
        valido_nuevo, _, _ = validar_token_salida_evento(token_nuevo, self.evento)
        self.assertTrue(valido_nuevo)

    def test_12_registro_salida_participante_institucional_exitoso(self):
        """12. Registro de salida para participante institucional mediante escaneo de QR colectivo."""
        # Paso previo: registrar llegada
        registrar_asistencia_llegada(self.inscripcion_inst, metodo=MetodoAsistencia.QR)
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        # Participante institucional autenticado
        self.client.force_login(self.usuario_inst)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])
        self.assertIn('permanencia', data)

        # BD actualizada
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_inst)
        self.assertIsNotNone(asistencia.hora_salida)
        self.assertGreaterEqual(asistencia.permanencia['total_minutos'], 0)

    def test_13_registro_salida_participante_externo_con_sesion_exitoso(self):
        """13. Registro de salida para participante externo con contexto de sesión seguro."""
        registrar_asistencia_llegada(self.inscripcion_ext, metodo=MetodoAsistencia.QR)
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        # Simular sesión externa activa
        session = self.client.session
        session['acceso_externo_id'] = self.acceso_ext.pk
        session.save()

        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exito'])

        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_ext)
        self.assertIsNotNone(asistencia.hora_salida)

    def test_14_rechazo_salida_sin_llegada_previa(self):
        """14. Rechazo de salida si el participante no cuenta con registro de llegada previo."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.usuario_inst)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['exito'])
        self.assertEqual(data['codigo'], 'ASISTENCIA_NO_REGISTRADA')

    def test_15_bloqueo_salida_duplicada(self):
        """15. Bloqueo de salida duplicada si ya fue confirmada previamente."""
        registrar_asistencia_llegada(self.inscripcion_inst, metodo=MetodoAsistencia.QR)
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.usuario_inst)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})

        # Primera salida
        res1 = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res1.json()['exito'])

        # Segunda salida
        res2 = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        data2 = res2.json()
        self.assertFalse(data2['exito'])
        self.assertEqual(data2['codigo'], 'SALIDA_YA_REGISTRADA')

    def test_16_rechazo_qr_salida_expirado(self):
        """16. Rechazo de un token QR de salida colectivo por superar MAX_AGE_QR_SALIDA."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)

        with patch('time.time', return_value=time.time() - 250):
            token_salida_expirado = generar_token_salida_evento(self.evento, control=control)

        valido, cod, err = validar_token_salida_evento(token_salida_expirado, self.evento)
        self.assertFalse(valido)
        self.assertEqual(cod, 'QR_SALIDA_EXPIRADO')

    def test_17_rechazo_qr_salida_evento_incorrecto(self):
        """17. Rechazo de un token QR de salida emitido para otro evento."""
        control_ajeno = iniciar_sesion_salida_service(self.evento_ajeno, operador=self.profesor)
        token_ajeno = generar_token_salida_evento(self.evento_ajeno, control=control_ajeno)

        valido, cod, err = validar_token_salida_evento(token_ajeno, self.evento)
        self.assertFalse(valido)
        self.assertEqual(cod, 'EVENTO_INCORRECTO')

    def test_18_invalidacion_qr_salida_tras_cierre_sesion(self):
        """18. Invalidación de tokens tras el cierre de sesión de salida por el profesor."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        # Cierre de sesión
        self.client.force_login(self.profesor)
        url_cerrar = reverse('asistencia:cerrar_sesion_salida', kwargs={'id_evento': self.evento.pk})
        self.client.post(url_cerrar)

        # El token previamente emitido queda rechazado
        valido, cod, err = validar_token_salida_evento(token_salida, self.evento)
        self.assertFalse(valido)
        self.assertEqual(cod, 'SESION_CERRADA')

    def test_19_invalidacion_qr_anteriores_tras_reinicio_sesion(self):
        """19. Invalidación de tokens al reiniciar una nueva sesión con nuevo sesion_id."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_sesion_1 = generar_token_salida_evento(self.evento, control=control)

        # Reinicio de sesión (nuevo sesion_id)
        control_2 = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        self.assertNotEqual(control.sesion_id, control_2.sesion_id)

        # El token de la sesión 1 queda rechazado
        valido, cod, err = validar_token_salida_evento(token_sesion_1, self.evento)
        self.assertFalse(valido)
        self.assertEqual(cod, 'SESION_INVALIDA')

    def test_20_proteccion_anti_idor_identidad_estricta(self):
        """20. Anti-IDOR: Se ignora cualquier documento o ID de inscripción enviado en POST."""
        registrar_asistencia_llegada(self.inscripcion_inst, metodo=MetodoAsistencia.QR)
        registrar_asistencia_llegada(self.inscripcion_ext, metodo=MetodoAsistencia.QR)

        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        # Ana está autenticada e intenta enviar el documento o id_inscripcion de Roberto (participante_ext)
        self.client.force_login(self.usuario_inst)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url_reg, {
            'token_salida': token_salida,
            'documento': self.participante_ext.documento,
            'id_inscripcion': self.inscripcion_ext.pk
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        # La salida registrada corresponde a Ana (usuario_inst) y NO a Roberto
        asist_ana = Asistencia.objects.get(inscripcion=self.inscripcion_inst)
        asist_roberto = Asistencia.objects.get(inscripcion=self.inscripcion_ext)
        self.assertIsNotNone(asist_ana.hora_salida)
        self.assertIsNone(asist_roberto.hora_salida)

    def test_21_proteccion_permisos_profesor_vs_participante(self):
        """21. Un participante no puede iniciar, cerrar o rotar sesiones de salida de un evento."""
        self.client.force_login(self.usuario_inst)

        url_iniciar = reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk})
        res_ini = self.client.post(url_iniciar)
        self.assertEqual(res_ini.status_code, 403)

        url_cerrar = reverse('asistencia:cerrar_sesion_salida', kwargs={'id_evento': self.evento.pk})
        res_cer = self.client.post(url_cerrar)
        self.assertEqual(res_cer.status_code, 403)

        url_rotar = reverse('asistencia:rotar_nonce_salida', kwargs={'id_evento': self.evento.pk})
        res_rot = self.client.post(url_rotar)
        self.assertEqual(res_rot.status_code, 403)

        url_proy = reverse('asistencia:proyector_salida', kwargs={'id_evento': self.evento.pk})
        res_proy = self.client.get(url_proy)
        self.assertEqual(res_proy.status_code, 403)

    def test_22_registro_auditoria_completo(self):
        """22. Verificación de creación de trazas de auditoría en todas las operaciones clave."""
        Auditoria.objects.all().delete()

        # 1. Llegada
        registrar_asistencia_llegada(self.inscripcion_inst, metodo=MetodoAsistencia.QR, operador=self.profesor)
        # 2. Inicio sesión
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        # 3. Rotar nonce
        rotar_nonce_salida_service(self.evento, operador=self.profesor)
        # 4. Salida
        registrar_asistencia_salida(self.inscripcion_inst, metodo=MetodoAsistencia.QR)
        # 5. Cierre sesión
        cerrar_sesion_salida_service(self.evento, operador=self.profesor)

        acciones = list(Auditoria.objects.values_list('accion', flat=True))
        self.assertIn('REGISTRAR_ASISTENCIA', acciones)
        self.assertIn('INICIAR_SESION_SALIDA', acciones)
        self.assertIn('ROTAR_NONCE_SALIDA', acciones)
        self.assertIn('REGISTRAR_SALIDA_ASISTENCIA', acciones)
        self.assertIn('CERRAR_SESION_SALIDA', acciones)

    def test_23_consistencia_transaccional_en_errores(self):
        """23. Integridad transaccional: un fallo no deja registros inconsistentes."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        # Intento de registrar salida sin llegada retorna error controlado y no crea asistencia
        resultado = registrar_asistencia_salida(self.inscripcion_inst, metodo=MetodoAsistencia.QR)
        self.assertFalse(resultado['exito'])
        self.assertEqual(resultado['codigo'], 'ASISTENCIA_NO_REGISTRADA')
        self.assertFalse(Asistencia.objects.filter(inscripcion=self.inscripcion_inst).exists())

    def test_24_escenario_e2e_a_participante_institucional(self):
        """
        24. ESCENARIO E2E A: Flujo completo participante institucional
        Inscripción -> Pase digital con QR dinámico -> Escaneo llegada operador ->
        Sesión salida colectiva -> Proyector -> Escaneo participante -> Checkout confirmado.
        """
        # A1: Participante abre su pase digital
        self.client.force_login(self.usuario_inst)
        url_pase = reverse('asistencia:pase_digital', kwargs={'id_inscripcion': self.inscripcion_inst.pk})
        res_pase = self.client.get(url_pase)
        self.assertEqual(res_pase.status_code, 200)
        self.assertContains(res_pase, 'Pase Digital')

        # A2: Participante genera token dinámico de llegada
        url_qr_din = reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': self.inscripcion_inst.pk})
        res_din = self.client.get(url_qr_din, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        token_llegada = res_din.json()['token']

        # A3: Operador escanea el QR en la mesa de entrada
        self.client.force_login(self.profesor)
        url_ctrl = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        res_scan_in = self.client.post(url_ctrl, {'token_qr': token_llegada}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res_scan_in.json()['exito'])

        # A4: Al terminar el evento, el profesor inicia sesión de salida y abre el proyector
        url_ini = reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk})
        res_ini = self.client.post(url_ini, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        token_salida = res_ini.json()['token_salida']

        url_proy = reverse('asistencia:proyector_salida', kwargs={'id_evento': self.evento.pk})
        res_proy = self.client.get(url_proy)
        self.assertEqual(res_proy.status_code, 200)
        self.assertContains(res_proy, 'Proyección de Salida')

        # A5: El participante institucional abre el escáner de salida y registra su salida
        self.client.force_login(self.usuario_inst)
        url_scan_out = reverse('asistencia:escanear_salida', kwargs={'id_evento': self.evento.pk})
        res_scan_view = self.client.get(url_scan_out)
        self.assertEqual(res_scan_view.status_code, 200)

        url_reg_out = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        res_reg_out = self.client.post(url_reg_out, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_reg_out.status_code, 200)
        data_out = res_reg_out.json()
        self.assertTrue(data_out['exito'])
        self.assertIn('permanencia', data_out)

        # A6: Verificación de estado final en base de datos
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_inst)
        self.assertIsNotNone(asistencia.hora_entrada)
        self.assertIsNotNone(asistencia.hora_salida)

    def test_25_escenario_e2e_b_participante_externo(self):
        """
        25. ESCENARIO E2E B: Flujo completo participante externo
        Acceso por enlace seguro -> Portal personal -> QR dinámico llegada ->
        Operador registra llegada -> Escáner de salida externo -> Salida y permanencia.
        """
        # B1: Participante externo abre su enlace seguro de entrada
        url_entry = reverse('participantes:consultar_acceso_externo', kwargs={'token': self.token_acceso_ext})
        res_entry = self.client.get(url_entry, follow=True)
        self.assertEqual(res_entry.status_code, 200)
        self.assertContains(res_entry, 'Portal de Participante Externo')
        # La sesión queda establecida
        self.assertEqual(self.client.session.get('acceso_externo_id'), self.acceso_ext.pk)

        # B2: Obtiene su token dinámico de llegada
        url_qr_din = reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': self.inscripcion_ext.pk})
        res_din = self.client.get(url_qr_din, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        token_llegada_ext = res_din.json()['token']

        # B3: Operador registra la llegada del externo
        client_operador = Client()
        client_operador.force_login(self.profesor)
        url_ctrl = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        res_scan_in = client_operador.post(url_ctrl, {'token_qr': token_llegada_ext}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res_scan_in.json()['exito'])

        # B4: Profesor habilita salida colectiva
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida_colectivo = generar_token_salida_evento(self.evento, control=control)

        # B5: Externo abre escáner de salida con su sesión activa
        url_scan_out = reverse('asistencia:escanear_salida', kwargs={'id_evento': self.evento.pk})
        res_scan_out = self.client.get(url_scan_out)
        self.assertEqual(res_scan_out.status_code, 200)

        url_reg_out = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        res_reg_out = self.client.post(url_reg_out, {'token_salida': token_salida_colectivo}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_reg_out.status_code, 200)
        data_out = res_reg_out.json()
        self.assertTrue(data_out['exito'])

        asist_ext = Asistencia.objects.get(inscripcion=self.inscripcion_ext)
        self.assertIsNotNone(asist_ext.hora_salida)
        self.assertGreaterEqual(asist_ext.permanencia['total_minutos'], 0)

    def test_26_escenario_e2e_c_intentos_indebidos_y_seguridad(self):
        """
        26. ESCENARIO E2E C: Batería exhaustiva de intentos indebidos y ataques de evasión.
        """
        # C1: Salida sin llegada registrada
        control = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.usuario_inst)
        url_reg_out = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        res_sin_llegada = self.client.post(url_reg_out, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_sin_llegada.status_code, 400)
        self.assertEqual(res_sin_llegada.json()['codigo'], 'ASISTENCIA_NO_REGISTRADA')

        # C2: Llegada con QR expirado
        with patch('time.time', return_value=time.time() - 200):
            token_llegada_viejo = generar_token_qr(self.inscripcion_inst)

        client_operador = Client()
        client_operador.force_login(self.profesor)
        url_ctrl = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        res_exp = client_operador.post(url_ctrl, {'token_qr': token_llegada_viejo}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_exp.status_code, 400)
        self.assertEqual(res_exp.json()['codigo'], 'QR_EXPIRADO')

        # C3: Registrar llegada válida
        token_llegada_ok = generar_token_qr(self.inscripcion_inst)
        res_ok = client_operador.post(url_ctrl, {'token_qr': token_llegada_ok}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res_ok.json()['exito'])

        # C4: Salida con token manipulado
        res_tampered = self.client.post(url_reg_out, {'token_salida': token_salida + "fake"}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_tampered.status_code, 400)
        self.assertEqual(res_tampered.json()['codigo'], 'QR_SALIDA_ALTERADO')

        # C5: Salida con sesión cerrada
        cerrar_sesion_salida_service(self.evento, operador=self.profesor)
        res_cerrada = self.client.post(url_reg_out, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_cerrada.status_code, 400)
        self.assertEqual(res_cerrada.json()['codigo'], 'SESION_CERRADA')

        # C6: Reabrir sesión, registrar salida válida y verificar bloqueo de duplicada
        control_nuevo = iniciar_sesion_salida_service(self.evento, operador=self.profesor)
        token_nuevo = generar_token_salida_evento(self.evento, control=control_nuevo)

        res_salida_ok = self.client.post(url_reg_out, {'token_salida': token_nuevo}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res_salida_ok.json()['exito'])

        res_salida_dup = self.client.post(url_reg_out, {'token_salida': token_nuevo}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(res_salida_dup.json()['exito'])
        self.assertEqual(res_salida_dup.json()['codigo'], 'SALIDA_YA_REGISTRADA')
        self.assertEqual(res_salida_dup.json()['codigo'], 'SALIDA_YA_REGISTRADA')

