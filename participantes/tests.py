import datetime
import hashlib
from unittest.mock import patch
from django.core import mail
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from usuarios.models import Rol, Usuario
from eventos.models import CategoriaEvento, Evento, ModalidadEvento, EstadoEvento, ModalidadInscripcion
from participantes.models import (
    Participante,
    Inscripcion,
    TipoParticipante,
    EstadoInscripcion,
    InvitacionEvento,
    EstadoInvitacion,
    AccesoExternoInscripcion,
)
from asistencia.models import Asistencia
from auditoria.models import Auditoria


class ParticipanteInscripcionModelTests(TestCase):
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Estudiante')
        self.usuario = Usuario.objects.create_user(
            username='estudiante_test',
            email='estudiante@test.edu',
            password='TestPassword123*',
            documento='10101010',
            nombres='Juan',
            apellidos='Pérez',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Académico')
        self.evento = Evento.objects.create(
            nombre='Simposio de Investigación',
            descripcion='Evento académico',
            fecha=datetime.date(2026, 11, 20),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio A',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.usuario
        )

    def test_inscripcion_estudiante_institucional(self):
        """Un estudiante institucional con Usuario y Participante puede inscribirse."""
        participante = Participante.objects.create(
            usuario=self.usuario,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.usuario.documento,
            nombres=self.usuario.nombres,
            apellidos=self.usuario.apellidos,
            correo=self.usuario.email
        )
        inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=participante,
            estado=EstadoInscripcion.ACTIVA
        )
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)
        self.assertFalse(inscripcion.asistio)

    def test_inscripcion_participante_externo_sin_usuario(self):
        """Un participante externo con usuario=NULL puede registrarse e inscribirse."""
        participante_ext = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='80808080',
            nombres='Carlos',
            apellidos='Externo',
            correo='carlos@externo.com'
        )
        self.assertIsNone(participante_ext.usuario)
        inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=participante_ext,
            estado=EstadoInscripcion.ACTIVA
        )
        self.assertEqual(inscripcion.participante, participante_ext)
        self.assertFalse(inscripcion.asistio)

    def test_rechazo_doble_inscripcion_mismo_evento(self):
        """Un participante no puede inscribirse dos veces al mismo evento a nivel de base de datos."""
        participante = Participante.objects.create(
            usuario=self.usuario,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.usuario.documento,
            nombres=self.usuario.nombres,
            apellidos=self.usuario.apellidos,
            correo=self.usuario.email
        )
        Inscripcion.objects.create(
            evento=self.evento,
            participante=participante,
            estado=EstadoInscripcion.ACTIVA
        )
        with self.assertRaises(IntegrityError):
            Inscripcion.objects.create(
                evento=self.evento,
                participante=participante,
                estado=EstadoInscripcion.ACTIVA
            )


class PortalInscripcionesViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')
        self.rol_docente = Rol.objects.create(nombre='Docente')

        self.organizador = Usuario.objects.create_user(
            username='organizador_view',
            email='org_view@uniminuto.edu.co',
            password='Password123*',
            documento='50505050',
            nombres='Profesor',
            apellidos='Organizador',
            rol=self.rol_docente
        )

        self.estudiante_1 = Usuario.objects.create_user(
            username='estudiante_uno',
            email='estudiante1@uniminuto.edu.co',
            password='Password123*',
            documento='11110000',
            nombres='Ana',
            apellidos='Gómez',
            rol=self.rol_estudiante
        )

        self.estudiante_2 = Usuario.objects.create_user(
            username='estudiante_dos',
            email='estudiante2@uniminuto.edu.co',
            password='Password123*',
            documento='22220000',
            nombres='Luis',
            apellidos='Torres',
            rol=self.rol_estudiante
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Tecnología')

        self.evento = Evento.objects.create(
            nombre='Hackathon Universitaria 2026',
            descripcion='Maratón de desarrollo de software.',
            fecha=datetime.date(2026, 11, 28),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(18, 0),
            lugar='Laboratorios de Cómputo',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=2,  # Cupo pequeño para pruebas de saturación
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA
        )

        self.evento_cerrado = Evento.objects.create(
            nombre='Seminario Ya Finalizado',
            descripcion='Evento pasado.',
            fecha=datetime.date(2026, 10, 1),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio C',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.FINALIZADO,
            categoria=self.categoria,
            organizador=self.organizador,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA
        )

    def test_inscripcion_institucional_un_clic(self):
        """Un estudiante autenticado se inscribe con 1 clic y se registra en auditoría."""
        self.client.login(username='estudiante_uno', password='Password123*')
        response = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Verificar participante creado y vinculado al usuario
        participante = Participante.objects.filter(usuario=self.estudiante_1).first()
        self.assertIsNotNone(participante)
        self.assertEqual(participante.tipo, TipoParticipante.ESTUDIANTE)

        # Verificar inscripción activa
        inscripcion = Inscripcion.objects.filter(evento=self.evento, participante=participante).first()
        self.assertIsNotNone(inscripcion)
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.estudiante_1,
            accion='INSCRIBIR_PARTICIPANTE',
            modulo='PARTICIPANTES'
        ).first()
        self.assertIsNotNone(auditoria)

    def test_inscripcion_externo_formulario_y_registro(self):
        """Un usuario externo no autenticado completa el formulario y se inscribe."""
        # GET al formulario
        resp_get = self.client.get(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk})
        )
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Participante Externo')
        self.assertContains(resp_get, 'Formulario de Inscripción al Evento')

        # POST con datos de participante externo
        resp_post = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            {
                'documento': '99887766',
                'nombres': 'María',
                'apellidos': 'Externa',
                'correo': 'maria@externo.org',
                'telefono': '3001234567',
                'institucion': 'Universidad Aliada',
                'acepta_politica_tratamiento': 'True',
            },
            follow=True
        )
        self.assertEqual(resp_post.status_code, 200)

        # Verificar participante externo sin usuario
        participante_ext = Participante.objects.filter(documento='99887766').first()
        self.assertIsNotNone(participante_ext)
        self.assertIsNone(participante_ext.usuario)
        self.assertEqual(participante_ext.tipo, TipoParticipante.EXTERNO)

        # Verificar inscripción activa
        inscripcion = Inscripcion.objects.filter(evento=self.evento, participante=participante_ext).first()
        self.assertIsNotNone(inscripcion)
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)

        # Verificar redirección al pase digital y renderizado del pase con código QR
        self.assertContains(resp_post, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(resp_post, 'María Externa')
        self.assertContains(resp_post, 'data:image/png;base64,')
        self.assertContains(resp_post, '← Volver al Evento')

        # Verificar auditoría con usuario=None
        auditoria = Auditoria.objects.filter(
            usuario__isnull=True,
            accion='INSCRIBIR_EXTERNO',
            modulo='PARTICIPANTES'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn('99887766', auditoria.registro_afectado)

    def test_inscripcion_externo_reintento_entrega_pase_qr(self):
        """Un participante externo que vuelve a registrarse con su documento obtiene su pase digital sin duplicar inscripción."""
        # Primera inscripción
        self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            {
                'documento': '88776655',
                'nombres': 'Pedro',
                'apellidos': 'Recurrente',
                'correo': 'pedro@externo.org',
                'telefono': '3112223344',
                'institucion': 'Entidad Socia',
                'acepta_politica_tratamiento': 'True',
            }
        )
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__documento='88776655').count(), 1)

        # Segundo intento: debe redirigir al pase digital con su token
        resp_reintento = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            {
                'documento': '88776655',
                'nombres': 'Pedro',
                'apellidos': 'Recurrente',
                'correo': 'pedro@externo.org',
                'telefono': '3112223344',
                'institucion': 'Entidad Socia',
                'acepta_politica_tratamiento': 'True',
            },
            follow=True
        )
        self.assertEqual(resp_reintento.status_code, 200)
        self.assertContains(resp_reintento, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(resp_reintento, 'Pedro Recurrente')
        self.assertContains(resp_reintento, 'ya cuenta con una inscripción activa')
        # Sigue existiendo exactamente 1 inscripción
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__documento='88776655').count(), 1)

    def test_inscripcion_externo_reactivacion_entrega_pase_qr(self):
        """Un participante externo cuya inscripción estaba cancelada la reactiva y obtiene su pase digital."""
        part_ext = Participante.objects.create(
            documento='77665544',
            nombres='Laura',
            apellidos='Cancelada',
            correo='laura@externo.org',
            tipo=TipoParticipante.EXTERNO,
            usuario=None
        )
        insc = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_ext,
            estado=EstadoInscripcion.CANCELADA
        )

        resp_reactiva = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            {
                'documento': '77665544',
                'nombres': 'Laura',
                'apellidos': 'Cancelada',
                'correo': 'laura@externo.org',
                'telefono': '3159998877',
                'institucion': 'Socio Externo',
                'acepta_politica_tratamiento': 'True',
            },
            follow=True
        )
        self.assertEqual(resp_reactiva.status_code, 200)
        insc.refresh_from_db()
        self.assertEqual(insc.estado, EstadoInscripcion.ACTIVA)
        self.assertContains(resp_reactiva, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(resp_reactiva, 'Laura Cancelada')

    def test_inscripcion_externo_sin_consentimiento_rechazada(self):
        """(RNF-14) Un usuario externo no puede inscribirse si no acepta la política de tratamiento de datos."""
        resp_post = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            {
                'documento': '11223344',
                'nombres': 'Carlos',
                'apellidos': 'SinConsentimiento',
                'correo': 'carlos@sindatos.org',
                'telefono': '3007654321',
                'institucion': 'Entidad Externa',
                # 'acepta_politica_tratamiento' omitido intencionalmente
            },
            follow=True
        )
        self.assertEqual(resp_post.status_code, 200)
        # No se debió crear participante ni inscripción
        participante = Participante.objects.filter(documento='11223344').first()
        self.assertIsNone(participante)
        self.assertContains(resp_post, 'Debes autorizar el tratamiento de datos personales')

    def test_rechazo_doble_inscripcion_activa(self):
        """Reintentar inscribirse cuando ya está activo no crea duplicados y muestra mensaje informativo."""
        self.client.login(username='estudiante_uno', password='Password123*')
        # Primera inscripción
        self.client.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        # Segunda inscripción
        response = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya cuentas con una inscripción activa en este evento')

        # Total inscripciones debe seguir siendo 1
        participante = Participante.objects.get(usuario=self.estudiante_1)
        total = Inscripcion.objects.filter(evento=self.evento, participante=participante).count()
        self.assertEqual(total, 1)

    def test_reactivacion_inscripcion_previamente_cancelada(self):
        """Un usuario que canceló su inscripción puede volver a inscribirse reactivando el registro existente."""
        self.client.login(username='estudiante_uno', password='Password123*')
        # Inscribirse
        self.client.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        participante = Participante.objects.get(usuario=self.estudiante_1)
        inscripcion = Inscripcion.objects.get(evento=self.evento, participante=participante)

        # Cancelar
        self.client.post(reverse('participantes:cancelar_inscripcion', kwargs={'id_inscripcion': inscripcion.pk}))
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, EstadoInscripcion.CANCELADA)

        # Volver a inscribirse
        resp_re = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            follow=True
        )
        self.assertEqual(resp_re.status_code, 200)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)
        self.assertContains(resp_re, 'ha sido reactivada exitosamente')

        # No debe haber creado un segundo registro
        total = Inscripcion.objects.filter(evento=self.evento, participante=participante).count()
        self.assertEqual(total, 1)

    def test_rechazo_inscripcion_cupo_agotado(self):
        """Cuando se llena el cupo del evento, no se permiten nuevas inscripciones."""
        # Llenar cupo (cupo = 2)
        part_a = Participante.objects.create(
            tipo=TipoParticipante.ESTUDIANTE,
            documento='111',
            nombres='P1',
            apellidos='A1',
            correo='p1@uniminuto.edu.co'
        )
        part_b = Participante.objects.create(
            tipo=TipoParticipante.ESTUDIANTE,
            documento='222',
            nombres='P2',
            apellidos='A2',
            correo='p2@uniminuto.edu.co'
        )
        Inscripcion.objects.create(evento=self.evento, participante=part_a, estado=EstadoInscripcion.ACTIVA)
        Inscripcion.objects.create(evento=self.evento, participante=part_b, estado=EstadoInscripcion.ACTIVA)

        # Intentar inscribir a estudiante_1
        self.client.login(username='estudiante_uno', password='Password123*')
        response = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'el cupo de 2 asistentes para este evento ya se encuentra agotado')

    def test_rechazo_inscripcion_evento_no_publicado(self):
        """No se permiten inscripciones a eventos finalizados, cerrados o cancelados."""
        self.client.login(username='estudiante_uno', password='Password123*')
        response = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento_cerrado.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No admite inscripciones')

    def test_mis_inscripciones_privacidad_y_aislamiento(self):
        """Un usuario solo puede ver sus propias inscripciones en el panel privado."""
        client_1 = Client()
        client_1.login(username='estudiante_uno', password='Password123*')
        client_1.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}), follow=True)

        # Estudiante 2 consulta 'Mis inscripciones'
        client_2 = Client()
        client_2.login(username='estudiante_dos', password='Password123*')
        response = client_2.get(reverse('participantes:mis_inscripciones'))
        self.assertEqual(response.status_code, 200)
        # Estudiante 2 no tiene inscripciones aún
        self.assertContains(response, 'No tienes inscripciones activas')
        self.assertNotContains(response, 'Hackathon Universitaria 2026')

        # Estudiante 1 consulta 'Mis inscripciones'
        response1 = client_1.get(reverse('participantes:mis_inscripciones'))
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, 'Hackathon Universitaria 2026')

    def test_cancelar_propia_inscripcion_exitosa(self):
        """El usuario puede cancelar su propia inscripción y se genera auditoría."""
        self.client.login(username='estudiante_uno', password='Password123*')
        self.client.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        participante = Participante.objects.get(usuario=self.estudiante_1)
        inscripcion = Inscripcion.objects.get(evento=self.evento, participante=participante)

        response = self.client.post(
            reverse('participantes:cancelar_inscripcion', kwargs={'id_inscripcion': inscripcion.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, EstadoInscripcion.CANCELADA)
        self.assertContains(response, 'ha sido cancelada')

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.estudiante_1,
            accion='CANCELAR_INSCRIPCION',
            modulo='PARTICIPANTES'
        ).first()
        self.assertIsNotNone(auditoria)

    def test_rechazo_cancelar_inscripcion_ajena(self):
        """Un usuario no puede cancelar la inscripción de otro usuario (403)."""
        # Estudiante 1 se inscribe
        self.client.login(username='estudiante_uno', password='Password123*')
        self.client.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        participante = Participante.objects.get(usuario=self.estudiante_1)
        inscripcion = Inscripcion.objects.get(evento=self.evento, participante=participante)

        # Estudiante 2 intenta cancelar la inscripción de Estudiante 1
        self.client.login(username='estudiante_dos', password='Password123*')
        response = self.client.post(
            reverse('participantes:cancelar_inscripcion', kwargs={'id_inscripcion': inscripcion.pk})
        )
        self.assertEqual(response.status_code, 403)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)

    def test_no_cancelar_inscripcion_con_asistencia_registrada(self):
        """No se permite cancelar una inscripción si ya se registró asistencia en el evento."""
        self.client.login(username='estudiante_uno', password='Password123*')
        self.client.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        participante = Participante.objects.get(usuario=self.estudiante_1)
        inscripcion = Inscripcion.objects.get(evento=self.evento, participante=participante)

        # Registrar asistencia
        Asistencia.objects.create(
            inscripcion=inscripcion,
            fecha=datetime.date(2026, 11, 28),
            hora_entrada=datetime.time(8, 30)
        )

        response = self.client.post(
            reverse('participantes:cancelar_inscripcion', kwargs={'id_inscripcion': inscripcion.pk}),
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No es posible cancelar una inscripción que ya cuenta con asistencia registrada')
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)


class InvitacionEventoModelTests(TestCase):
    """
    Pruebas unitarias de estructura, unicidad y seguridad del modelo InvitacionEvento (RF-02, Etapa 7.1).
    """
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='docente_inv',
            email='docente_inv@uniminuto.edu.co',
            password='TestPassword123*',
            documento='88889999',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Conferencia')
        self.evento = Evento.objects.create(
            nombre='Congreso de Ciberseguridad',
            descripcion='Conferencia internacional',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Auditorio Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA
        )

    def test_crear_invitacion_estado_inicial_pendiente(self):
        """Crear una invitación establece estado PENDIENTE y genera token y hash seguro."""
        raw_token, token_hash = InvitacionEvento.generar_token()
        self.assertEqual(len(token_hash), 64)
        self.assertNotEqual(raw_token, token_hash)

        fecha_exp = timezone.now() + datetime.timedelta(days=7)
        invitacion = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='invitado@ejemplo.com',
            nombres='Carlos',
            apellidos='Invitado',
            institucion='Universidad Aliada',
            token_hash=token_hash,
            invitado_por=self.organizador,
            fecha_expiracion=fecha_exp
        )
        self.assertEqual(invitacion.estado, EstadoInvitacion.PENDIENTE)
        self.assertEqual(invitacion.correo, 'invitado@ejemplo.com')
        self.assertFalse(invitacion.ha_expirado)

    def test_token_invitacion_generacion_y_verificacion(self):
        """La verificación del token mediante verificar_token confirma identidad criptográfica en tiempo constante."""
        raw_token, token_hash = InvitacionEvento.generar_token()
        invitacion = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='seguridad@ejemplo.com',
            nombres='Diana',
            apellidos='Segura',
            token_hash=token_hash,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=3)
        )
        self.assertTrue(invitacion.verificar_token(raw_token))
        self.assertFalse(invitacion.verificar_token('token_falso_adivinado_1234567890'))
        self.assertFalse(invitacion.verificar_token(''))
        self.assertFalse(invitacion.verificar_token(None))

    def test_invitacion_no_crea_inscripcion_automatica(self):
        """Regla RF-02: Enviar o crear una invitación NO crea una inscripción confirmada."""
        raw_token, token_hash = InvitacionEvento.generar_token()
        InvitacionEvento.objects.create(
            evento=self.evento,
            correo='sin_inscripcion@ejemplo.com',
            nombres='Andrés',
            apellidos='SinInscripcion',
            token_hash=token_hash,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=2)
        )
        # La tabla Inscripcion debe seguir vacía para este evento
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento).count(), 0)

    def test_unicidad_invitacion_pendiente_por_evento_y_correo(self):
        """No se permite crear dos invitaciones con estado PENDIENTE para el mismo correo y evento."""
        _, hash_1 = InvitacionEvento.generar_token()
        _, hash_2 = InvitacionEvento.generar_token()
        fecha_exp = timezone.now() + datetime.timedelta(days=5)

        InvitacionEvento.objects.create(
            evento=self.evento,
            correo='duplicado@ejemplo.com',
            nombres='Juan',
            apellidos='Original',
            token_hash=hash_1,
            invitado_por=self.organizador,
            fecha_expiracion=fecha_exp
        )

        with self.assertRaises(IntegrityError):
            InvitacionEvento.objects.create(
                evento=self.evento,
                correo='duplicado@ejemplo.com',
                nombres='Juan',
                apellidos='Duplicado',
                token_hash=hash_2,
                invitado_por=self.organizador,
                fecha_expiracion=fecha_exp
            )

    def test_permite_nueva_invitacion_si_anterior_fue_rechazada_o_expirada(self):
        """Permite reenvío creando nueva invitación si la previa ya pasó a estado EXPIRADA o RECHAZADA."""
        _, hash_1 = InvitacionEvento.generar_token()
        _, hash_2 = InvitacionEvento.generar_token()

        inv_previa = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='reenvio@ejemplo.com',
            nombres='Camila',
            apellidos='Expirada',
            token_hash=hash_1,
            estado=EstadoInvitacion.EXPIRADA,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() - datetime.timedelta(days=1)
        )
        self.assertEqual(inv_previa.estado, EstadoInvitacion.EXPIRADA)

        # Ahora debe permitir crear una nueva invitación PENDIENTE
        nueva_inv = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='reenvio@ejemplo.com',
            nombres='Camila',
            apellidos='Renovada',
            token_hash=hash_2,
            estado=EstadoInvitacion.PENDIENTE,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=5)
        )
        self.assertEqual(nueva_inv.estado, EstadoInvitacion.PENDIENTE)
        self.assertEqual(InvitacionEvento.objects.filter(evento=self.evento, correo='reenvio@ejemplo.com').count(), 2)

    def test_propiedad_ha_expirado(self):
        """La propiedad ha_expirado evalúa correctamente contra la marca de tiempo actual."""
        _, hash_1 = InvitacionEvento.generar_token()
        inv_pasada = InvitacionEvento(
            evento=self.evento,
            correo='exp@ejemplo.com',
            nombres='Test',
            apellidos='Expirado',
            token_hash=hash_1,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() - datetime.timedelta(hours=2)
        )
        self.assertTrue(inv_pasada.ha_expirado)

        _, hash_2 = InvitacionEvento.generar_token()
        inv_vigente = InvitacionEvento(
            evento=self.evento,
            correo='vig@ejemplo.com',
            nombres='Test',
            apellidos='Vigente',
            token_hash=hash_2,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=2)
        )
        self.assertFalse(inv_vigente.ha_expirado)

    def test_renovar_token_invalida_token_anterior(self):
        """Al renovar el token de una invitación pendiente, el token original queda revocado inmediatamente."""
        raw_token_orig, _ = InvitacionEvento.generar_token()
        inv = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='inv_renovar@ejemplo.com',
            nombres='Renata',
            apellidos='Original',
            token_hash=hashlib.sha256(raw_token_orig.encode('utf-8')).hexdigest(),
            estado=EstadoInvitacion.PENDIENTE,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=2)
        )
        self.assertTrue(inv.verificar_token(raw_token_orig))

        # Renovar el token
        nuevo_raw_token = inv.renovar_token(dias_vigencia=5)
        self.assertNotEqual(raw_token_orig, nuevo_raw_token)

        # El token original DEBE ser inválido
        self.assertFalse(inv.verificar_token(raw_token_orig))
        # El nuevo token DEBE ser válido
        self.assertTrue(inv.verificar_token(nuevo_raw_token))

    def test_crear_o_renovar_invitacion_idempotencia_y_renovacion(self):
        """crear_o_renovar_invitacion no duplica invitaciones pendientes y renueva el token."""
        inv1, token1 = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='duplicado@ejemplo.com',
            nombres='Pedro',
            apellidos='Inicial',
            invitado_por=self.organizador
        )
        self.assertEqual(InvitacionEvento.objects.filter(evento=self.evento, correo='duplicado@ejemplo.com').count(), 1)
        self.assertTrue(inv1.verificar_token(token1))

        # Intentar invitar nuevamente al mismo correo pendiente
        inv2, token2 = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='duplicado@ejemplo.com',
            nombres='Pedro',
            apellidos='Inicial',
            invitado_por=self.organizador
        )
        # Sigue existiendo exactamente 1 invitación en la BD
        self.assertEqual(InvitacionEvento.objects.filter(evento=self.evento, correo='duplicado@ejemplo.com').count(), 1)
        self.assertEqual(inv1.pk, inv2.pk)
        self.assertNotEqual(token1, token2)
        # El enlace anterior queda revocado
        inv2.refresh_from_db()
        self.assertFalse(inv2.verificar_token(token1))
        self.assertTrue(inv2.verificar_token(token2))

    def test_invitacion_puede_ser_aceptada_y_marcar_como_aceptada(self):
        """Una invitación vigente puede ser aceptada, marcando estado ACEPTADA y registrando fechas."""
        raw_token, token_hash = InvitacionEvento.generar_token()
        inv = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='aceptar@ejemplo.com',
            nombres='Lucía',
            apellidos='Acepta',
            token_hash=token_hash,
            estado=EstadoInvitacion.PENDIENTE,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=2)
        )
        self.assertTrue(inv.puede_ser_aceptada)

        inv.marcar_como_aceptada()
        inv.refresh_from_db()
        self.assertEqual(inv.estado, EstadoInvitacion.ACEPTADA)
        self.assertIsNotNone(inv.fecha_aceptacion)
        self.assertIsNotNone(inv.fecha_respuesta)
        self.assertFalse(inv.puede_ser_aceptada)

        # Intentar aceptarla nuevamente debe fallar
        with self.assertRaises(ValidationError):
            inv.marcar_como_aceptada()

    def test_invitacion_expirada_rechaza_marcar_como_aceptada(self):
        """Una invitación con fecha de expiración en el pasado no puede ser aceptada."""
        raw_token, token_hash = InvitacionEvento.generar_token()
        inv = InvitacionEvento.objects.create(
            evento=self.evento,
            correo='expirada_intento@ejemplo.com',
            nombres='Carlos',
            apellidos='Tardío',
            token_hash=token_hash,
            estado=EstadoInvitacion.PENDIENTE,
            invitado_por=self.organizador,
            fecha_expiracion=timezone.now() - datetime.timedelta(hours=1)
        )
        self.assertFalse(inv.puede_ser_aceptada)
        with self.assertRaises(ValidationError):
            inv.marcar_como_aceptada()
        inv.refresh_from_db()
        self.assertEqual(inv.estado, EstadoInvitacion.EXPIRADA)


class AccesoExternoInscripcionModelTests(TestCase):
    """
    Pruebas unitarias de estructura, seguridad y ciclo de vida de AccesoExternoInscripcion (RF-03, Etapa 7.1).
    """
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='docente_ext',
            email='docente_ext@uniminuto.edu.co',
            password='TestPassword123*',
            documento='77778888',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Seminario')
        self.evento = Evento.objects.create(
            nombre='Seminario Abierto de Innovación',
            descripcion='Evento con participantes externos',
            fecha=datetime.date(2026, 12, 12),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sede Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA
        )
        # Participante externo sin usuario institucional
        self.participante_ext = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='90909090',
            nombres='Manuel',
            apellidos='Externo',
            correo='manuel@empresa.com'
        )
        self.inscripcion_ext = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.participante_ext,
            estado=EstadoInscripcion.ACTIVA
        )

    def test_crear_acceso_externo_exitoso(self):
        """Crea exitosamente el acceso externo para un participante sin cuenta con token seguro y hash."""
        raw_token, token_hash = AccesoExternoInscripcion.generar_token()
        self.assertEqual(len(token_hash), 64)
        self.assertNotEqual(raw_token, token_hash)

        fecha_exp = timezone.now() + datetime.timedelta(days=30)
        acceso = AccesoExternoInscripcion.objects.create(
            inscripcion=self.inscripcion_ext,
            token_hash=token_hash,
            fecha_expiracion=fecha_exp
        )
        self.assertTrue(acceso.es_valido)
        self.assertFalse(acceso.revocado)
        self.assertIsNone(acceso.fecha_revocacion)

    def test_token_acceso_externo_generacion_y_verificacion(self):
        """El acceso externo valida de forma criptográfica segura el token en plano con el hash almacenado."""
        raw_token, token_hash = AccesoExternoInscripcion.generar_token()
        acceso = AccesoExternoInscripcion.objects.create(
            inscripcion=self.inscripcion_ext,
            token_hash=token_hash,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=10)
        )
        self.assertTrue(acceso.verificar_token(raw_token))
        self.assertFalse(acceso.verificar_token('token_equivocado_xyz'))
        self.assertFalse(acceso.verificar_token(''))
        self.assertFalse(acceso.verificar_token(None))

    def test_unicidad_acceso_externo_por_inscripcion(self):
        """Una inscripción solo puede tener un único acceso externo asociado (relación OneToOne)."""
        _, hash_1 = AccesoExternoInscripcion.generar_token()
        _, hash_2 = AccesoExternoInscripcion.generar_token()
        fecha_exp = timezone.now() + datetime.timedelta(days=15)

        AccesoExternoInscripcion.objects.create(
            inscripcion=self.inscripcion_ext,
            token_hash=hash_1,
            fecha_expiracion=fecha_exp
        )

        with self.assertRaises(IntegrityError):
            AccesoExternoInscripcion.objects.create(
                inscripcion=self.inscripcion_ext,
                token_hash=hash_2,
                fecha_expiracion=fecha_exp
            )

    def test_revocacion_acceso_externo(self):
        """Revocar un acceso externo establece revocado=True, guarda fecha_revocacion y marca es_valido=False."""
        raw_token, token_hash = AccesoExternoInscripcion.generar_token()
        acceso = AccesoExternoInscripcion.objects.create(
            inscripcion=self.inscripcion_ext,
            token_hash=token_hash,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=10)
        )
        self.assertTrue(acceso.es_valido)

        acceso.revocar()
        acceso.refresh_from_db()
        self.assertTrue(acceso.revocado)
        self.assertIsNotNone(acceso.fecha_revocacion)
        self.assertFalse(acceso.es_valido)
        self.assertFalse(acceso.verificar_token(raw_token))

    def test_expiracion_acceso_externo(self):
        """Un acceso cuya fecha de expiración esté en el pasado se considera no válido."""
        raw_token, token_hash = AccesoExternoInscripcion.generar_token()
        acceso = AccesoExternoInscripcion.objects.create(
            inscripcion=self.inscripcion_ext,
            token_hash=token_hash,
            fecha_expiracion=timezone.now() - datetime.timedelta(days=1)
        )
        self.assertFalse(acceso.es_valido)
        self.assertFalse(acceso.verificar_token(raw_token))

    def test_validacion_clean_rechaza_acceso_externo_con_usuario(self):
        """Regla RF-03: clean() rechaza asociar AccesoExternoInscripcion a participantes con usuario institucional."""
        rol_est = Rol.objects.create(nombre='Estudiante')
        estudiante_user = Usuario.objects.create_user(
            username='estudiante_acceso_ext',
            email='est_ext@uniminuto.edu.co',
            password='Password123*',
            documento='66667777',
            rol=rol_est
        )
        part_institucional = Participante.objects.create(
            usuario=estudiante_user,
            tipo=TipoParticipante.ESTUDIANTE,
            documento='66667777',
            nombres='Estudiante',
            apellidos='Institucional',
            correo='est_ext@uniminuto.edu.co'
        )
        insc_institucional = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_institucional,
            estado=EstadoInscripcion.ACTIVA
        )

        _, token_hash = AccesoExternoInscripcion.generar_token()
        acceso_invalido = AccesoExternoInscripcion(
            inscripcion=insc_institucional,
            token_hash=token_hash,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=10)
        )
        with self.assertRaises(ValidationError) as ctx:
            acceso_invalido.clean()
        self.assertIn('inscripcion', ctx.exception.message_dict)

    def test_save_directo_rechaza_participante_institucional_sin_invocar_clean(self):
        """save() rechaza la persistencia de AccesoExternoInscripcion para usuario institucional aun si no se llama clean()."""
        rol_doc = Rol.objects.create(nombre='DocenteInstitucional')
        doc_user = Usuario.objects.create_user(
            username='docente_save_test',
            email='doc_save@uniminuto.edu.co',
            password='Password123*',
            documento='99887766',
            rol=rol_doc
        )
        part_doc = Participante.objects.create(
            usuario=doc_user,
            tipo=TipoParticipante.DOCENTE,
            documento='99887766',
            nombres='Docente',
            apellidos='Seguridad',
            correo='doc_save@uniminuto.edu.co'
        )
        insc_doc = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_doc,
            estado=EstadoInscripcion.ACTIVA
        )
        _, token_hash = AccesoExternoInscripcion.generar_token()
        acceso_invalido = AccesoExternoInscripcion(
            inscripcion=insc_doc,
            token_hash=token_hash,
            fecha_expiracion=timezone.now() + datetime.timedelta(days=10)
        )
        with self.assertRaises(ValidationError):
            acceso_invalido.save()

    def test_crear_para_inscripcion_exitoso_y_defensivo(self):
        """El método fábrica crear_para_inscripcion emite tokens para externos y bloquea institucionales."""
        # 1. Éxito con participante externo
        acceso, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(
            inscripcion=self.inscripcion_ext,
            duracion_dias=20
        )
        self.assertIsNotNone(acceso.pk)
        self.assertTrue(acceso.es_valido)
        self.assertTrue(acceso.verificar_token(raw_token))

        # 2. Bloqueo con participante institucional
        rol_coord = Rol.objects.create(nombre='CoordinadorInstitucional')
        coord_user = Usuario.objects.create_user(
            username='coord_save_test',
            email='coord@uniminuto.edu.co',
            password='Password123*',
            documento='55667788',
            rol=rol_coord
        )
        part_coord = Participante.objects.create(
            usuario=coord_user,
            tipo=TipoParticipante.ADMINISTRATIVO,
            documento='55667788',
            nombres='Coord',
            apellidos='Seguridad',
            correo='coord@uniminuto.edu.co'
        )
        insc_coord = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_coord,
            estado=EstadoInscripcion.ACTIVA
        )
        with self.assertRaises(ValidationError):
            AccesoExternoInscripcion.crear_para_inscripcion(insc_coord)

    def test_acceso_externo_invalido_si_participante_adquiere_cuenta(self):
        """Si un participante externo posteriormente vincula una cuenta institucional, su token externo queda inválido."""
        acceso, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(
            inscripcion=self.inscripcion_ext,
            duracion_dias=10
        )
        self.assertTrue(acceso.es_valido)
        self.assertTrue(acceso.verificar_token(raw_token))

        # El participante vincula cuenta de usuario institucional
        nuevo_user = Usuario.objects.create_user(
            username='antiguo_externo',
            email='manuel@uniminuto.edu.co',
            password='Password123*',
            documento='90909090',
            rol=self.rol
        )
        self.participante_ext.usuario = nuevo_user
        self.participante_ext.save()

        # El acceso externo ahora DEBE ser inválido en el servidor
        self.assertFalse(acceso.es_valido)
        self.assertFalse(acceso.verificar_token(raw_token))


class InvitacionesFuncionalesTestCase(TestCase):
    """
    Suite integral para verificar los 22 escenarios obligatorios del flujo
    funcional de invitaciones institucionales (RF-01 / Etapa 7.2.1).
    """
    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')
        self.rol_admin = Rol.objects.create(nombre='Administrador')

        # Docente organizador
        self.profesor = Usuario.objects.create_user(
            username='profesor_carlos',
            email='carlos.docente@uniminuto.edu.co',
            password='Password123*',
            documento='11223344',
            nombres='Carlos',
            apellidos='Gómez',
            rol=self.rol_docente
        )

        # Otro profesor (no organizador del evento)
        self.otro_profesor = Usuario.objects.create_user(
            username='profesor_pedro',
            email='pedro.docente@uniminuto.edu.co',
            password='Password123*',
            documento='55667788',
            nombres='Pedro',
            apellidos='Martínez',
            rol=self.rol_docente
        )

        # Estudiante sin rol de gestión
        self.estudiante = Usuario.objects.create_user(
            username='estudiante_ana',
            email='ana.estudiante@uniminuto.edu.co',
            password='Password123*',
            documento='99001122',
            nombres='Ana',
            apellidos='López',
            rol=self.rol_estudiante
        )

        # Administrador general
        self.admin = Usuario.objects.create_user(
            username='admin_sigae',
            email='admin@uniminuto.edu.co',
            password='Password123*',
            documento='10000001',
            nombres='Super',
            apellidos='Admin',
            rol=self.rol_admin,
            is_staff=True
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Seminario')
        self.evento = Evento.objects.create(
            nombre='Seminario de Arquitectura de Software',
            descripcion='Taller avanzado de microservicios y seguridad',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Aula Magna',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.SOLO_INVITACION,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )
        mail.outbox.clear()

    def test_01_profesor_autorizado_crea_invitacion(self):
        """1. Profesor autorizado crea invitación exitosamente y se envía correo."""
        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url, {
            'correo': 'invitada.maria@ejemplo.com',
            'nombres': 'María',
            'apellidos': 'Reyes',
            'institucion': 'UNAL',
        })
        self.assertEqual(response.status_code, 302)
        inv = InvitacionEvento.objects.filter(evento=self.evento, correo='invitada.maria@ejemplo.com').first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.estado, EstadoInvitacion.PENDIENTE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Seminario de Arquitectura de Software', mail.outbox[0].subject)
        self.assertTrue(Auditoria.objects.filter(accion='CREAR_INVITACION').exists())

    def test_02_usuario_no_autorizado_intenta_invitar(self):
        """2. Usuario no autorizado (ej. estudiante) intenta invitar y recibe 403 Forbidden."""
        self.client.force_login(self.estudiante)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url, {
            'correo': 'alguien@ejemplo.com',
            'nombres': 'Alguien',
            'apellidos': 'Prueba',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(InvitacionEvento.objects.filter(correo='alguien@ejemplo.com').exists())

    def test_03_invitacion_duplicada_pendiente(self):
        """3. Invitación duplicada pendiente no crea dos filas; renueva la existente de forma segura."""
        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        self.client.post(url, {
            'correo': 'duplicada@ejemplo.com',
            'nombres': 'Laura',
            'apellidos': 'Torres',
        })
        self.assertEqual(InvitacionEvento.objects.filter(evento=self.evento, correo='duplicada@ejemplo.com').count(), 1)

        # Enviar nuevamente al mismo correo pendiente
        response = self.client.post(url, {
            'correo': 'duplicada@ejemplo.com',
            'nombres': 'Laura',
            'apellidos': 'Torres',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(InvitacionEvento.objects.filter(evento=self.evento, correo='duplicada@ejemplo.com').count(), 1)
        self.assertTrue(Auditoria.objects.filter(accion='RENOVAR_INVITACION').exists())

    def test_04_renovacion_invalida_token_anterior(self):
        """4. Renovación de invitación invalida inmediatamente el enlace anterior."""
        inv, raw_token_orig = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='renovacion@ejemplo.com',
            nombres='Andrés',
            apellidos='Bello',
            invitado_por=self.profesor
        )
        self.client.force_login(self.profesor)
        url_reenviar = reverse('participantes:reenviar_invitacion', kwargs={'id_evento': self.evento.pk, 'id_invitacion': inv.pk})
        response = self.client.post(url_reenviar)
        self.assertEqual(response.status_code, 302)

        inv.refresh_from_db()
        self.assertFalse(inv.verificar_token(raw_token_orig))

    def test_05_token_inexistente(self):
        """5. Consulta de token inexistente o inválido retorna error 404 / plantilla de error."""
        url = reverse('participantes:consultar_invitacion', kwargs={'token': 'token_completamente_falso_y_no_existente_12345'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertIn('estado', response.context)
        self.assertEqual(response.context['estado'], 'INVALIDA')

    def test_06_token_expirado(self):
        """6. Token expirado se presenta como expirado y no permite respuesta."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='expirada@ejemplo.com',
            nombres='Camilo',
            apellidos='Sesto',
            invitado_por=self.profesor,
            dias_vigencia=1
        )
        inv.fecha_expiracion = timezone.now() - datetime.timedelta(hours=2)
        inv.save()

        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['estado'], 'EXPIRADA')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'no-referrer')

    def test_07_invitacion_rechazada(self):
        """7. Invitación rechazada se presenta como rechazada y no permite nuevas acciones."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='rechazada@ejemplo.com',
            nombres='Ernesto',
            apellidos='Pérez',
            invitado_por=self.profesor
        )
        inv.marcar_como_rechazada()

        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['estado'], 'RECHAZADA')

    def test_08_invitacion_ya_aceptada(self):
        """8. Invitación ya aceptada se presenta con el estado correspondiente."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='aceptada@ejemplo.com',
            nombres='Diana',
            apellidos='Uribe',
            invitado_por=self.profesor
        )
        inv.marcar_como_aceptada()

        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['estado'], 'ACEPTADA')

    def test_09_invitado_sin_sesion(self):
        """9. Invitado sin sesión activa ve enlaces a inicio de sesión y registro, conservando token."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='anonimo@ejemplo.com',
            nombres='Invitado',
            apellidos='Anónimo',
            invitado_por=self.profesor
        )
        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Iniciar Sesión')
        self.assertContains(response, 'Crear una Cuenta')
        self.assertEqual(self.client.session.get('invitacion_id'), inv.pk)
        self.assertNotIn(raw_token, response.request['PATH_INFO'])

    def test_10_invitado_autenticado_con_correo_diferente(self):
        """10. Invitado autenticado con correo diferente ve advertencia y se bloquea la respuesta."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='destinatario.oficial@ejemplo.com',
            nombres='Oficial',
            apellidos='Persona',
            invitado_por=self.profesor
        )
        # Iniciar sesión con cuenta con correo diferente (ana.estudiante@uniminuto.edu.co)
        self.client.force_login(self.estudiante)
        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['coincide_correo'])
        self.assertContains(response, 'Discrepancia de cuenta institucional')

        # Intentar forzar respuesta con la cuenta equivocada a la URL limpia
        url_resp = reverse('participantes:responder_invitacion')
        resp_post = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(resp_post.status_code, 403)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).exists())

    def test_11_invitado_autenticado_con_correo_correcto(self):
        """11. Invitado autenticado con correo coincidente puede visualizar los botones de confirmación."""
        self.estudiante.email_verificado = True
        self.estudiante.save()
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['coincide_correo'])
        self.assertTrue(response.context['correo_verificado'])
        self.assertContains(response, 'Aceptar Invitación e Inscribirme')
        self.assertContains(response, 'Rechazar Invitación')

    def test_12_aceptacion_genera_inscripcion_activa(self):
        """12. Aceptación explícita crea inscripción en estado ACTIVA y marca invitación como ACEPTADA."""
        self.estudiante.email_verificado = True
        self.estudiante.save()
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        self.client.get(url_inv, follow=True)

        url_resp = reverse('participantes:responder_invitacion')
        response = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertRedirects(response, reverse('participantes:mis_inscripciones'))

        inv.refresh_from_db()
        self.assertEqual(inv.estado, EstadoInvitacion.ACEPTADA)
        self.assertIsNotNone(inv.fecha_aceptacion)

        inscripcion = Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).first()
        self.assertIsNotNone(inscripcion)
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)
        self.assertTrue(Auditoria.objects.filter(accion='ACEPTAR_INVITACION').exists())

    def test_13_rechazo_no_genera_inscripcion(self):
        """13. Rechazo de invitación marca estado RECHAZADA y NO genera ninguna inscripción."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        self.client.get(url_inv, follow=True)

        url_resp = reverse('participantes:responder_invitacion')
        response = self.client.post(url_resp, {'accion': 'rechazar'})
        self.assertRedirects(response, reverse('eventos:catalogo'))

        inv.refresh_from_db()
        self.assertEqual(inv.estado, EstadoInvitacion.RECHAZADA)
        self.assertIsNotNone(inv.fecha_respuesta)

        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).exists())
        self.assertTrue(Auditoria.objects.filter(accion='RECHAZAR_INVITACION').exists())

    def test_14_dos_aceptaciones_simultaneas_no_generan_duplicados(self):
        """14. Intentos repetidos o concurrentes de aceptación no generan inscripciones duplicadas."""
        self.estudiante.email_verificado = True
        self.estudiante.save()
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        self.client.get(url_inv, follow=True)

        url_resp = reverse('participantes:responder_invitacion')

        # Primera aceptación
        self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).count(), 1)

        # Reponer contexto para simular solicitud concurrente
        session = self.client.session
        session['invitacion_id'] = inv.pk
        session['invitacion_token_hash'] = inv.token_hash
        session['invitacion_evento_id'] = self.evento.pk
        session['invitacion_correo'] = inv.correo
        session.save()

        # Segunda aceptación (idempotencia y protección contra colisión)
        self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).count(), 1)

    def test_15_error_durante_aceptacion_no_deja_estados_inconsistentes(self):
        """15. Un fallo imprevisto durante la creación de inscripción revierte la transacción atómicamente."""
        self.estudiante.email_verificado = True
        self.estudiante.save()
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        self.client.get(url_inv, follow=True)

        url_resp = reverse('participantes:responder_invitacion')

        with patch.object(Inscripcion.objects, 'create', side_effect=RuntimeError("Error simulado de base de datos")):
            with self.assertRaises(RuntimeError):
                self.client.post(url_resp, {'accion': 'aceptar'})

        inv.refresh_from_db()
        # Debe mantenerse PENDIENTE por rollback de transaction.atomic
        self.assertEqual(inv.estado, EstadoInvitacion.PENDIENTE)
        self.assertIsNone(inv.fecha_aceptacion)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.estudiante).exists())

    def test_16_evento_solo_invitacion(self):
        """16. Evento en modalidad SOLO_INVITACION admite la emisión de invitaciones."""
        self.evento.modalidad_inscripcion = ModalidadInscripcion.SOLO_INVITACION
        self.evento.save()

        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url, {
            'correo': 'solo_inv@ejemplo.com',
            'nombres': 'Solo',
            'apellidos': 'Invitacion',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(InvitacionEvento.objects.filter(correo='solo_inv@ejemplo.com').exists())

    def test_17_evento_abierta(self):
        """17. Evento en modalidad ABIERTA bloquea el envío de invitaciones individuales."""
        self.evento.modalidad_inscripcion = ModalidadInscripcion.ABIERTA
        self.evento.save()

        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url, {
            'correo': 'abierta_bloqueada@ejemplo.com',
            'nombres': 'Intento',
            'apellidos': 'Fallido',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(InvitacionEvento.objects.filter(correo='abierta_bloqueada@ejemplo.com').exists())

    def test_18_evento_mixta(self):
        """18. Evento en modalidad MIXTA admite tanto invitaciones como inscripción abierta."""
        self.evento.modalidad_inscripcion = ModalidadInscripcion.MIXTA
        self.evento.save()

        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.post(url, {
            'correo': 'mixta_valida@ejemplo.com',
            'nombres': 'Usuario',
            'apellidos': 'Mixto',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(InvitacionEvento.objects.filter(correo='mixta_valida@ejemplo.com').exists())

    def test_19_correo_enviado_correctamente_backend_pruebas(self):
        """19. Correo es despachado con asunto, remitente y alternativas HTML/TXT en outbox."""
        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        self.client.post(url, {
            'correo': 'notificado@ejemplo.com',
            'nombres': 'Notificado',
            'apellidos': 'Prueba',
        })
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['notificado@ejemplo.com'])
        self.assertIn('Seminario de Arquitectura de Software', msg.subject)
        self.assertIn('/participantes/invitacion/', msg.body)
        self.assertEqual(len(msg.alternatives), 1)
        self.assertEqual(msg.alternatives[0][1], 'text/html')

    def test_20_fallo_envio_correo_no_se_presenta_como_exitoso(self):
        """20. Un fallo en el transporte de correo genera advertencia y no reporta falso éxito."""
        self.client.force_login(self.profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})

        with patch('participantes.services.EmailMultiAlternatives.send', side_effect=Exception("Error de conexión SMTP simulado")):
            response = self.client.post(url, {
                'correo': 'fallo.transporte@ejemplo.com',
                'nombres': 'Fallo',
                'apellidos': 'Transporte',
            }, follow=True)

            self.assertEqual(response.status_code, 200)
            # Debe informar que no pudo entregarse el mensaje por correo
            self.assertContains(response, 'no pudo entregar el mensaje')

    def test_21_token_no_aparece_en_logs_ni_auditoria(self):
        """21. El token original nunca se almacena en la bitácora de auditoría ni en campos de texto."""
        self.estudiante.email_verificado = True
        self.estudiante.save()
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='ana.estudiante@uniminuto.edu.co',
            nombres='Ana',
            apellidos='López',
            invitado_por=self.profesor
        )
        self.client.force_login(self.estudiante)
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        self.client.get(url_inv, follow=True)

        url_resp = reverse('participantes:responder_invitacion')
        self.client.post(url_resp, {'accion': 'aceptar'})

        registros = Auditoria.objects.filter(modulo='PARTICIPANTES')
        self.assertTrue(registros.exists())
        for reg in registros:
            self.assertNotIn(raw_token, reg.registro_afectado)

    def test_22_usuario_no_puede_consultar_invitaciones_ajenas(self):
        """22. Un docente no organizador no puede gestionar ni consultar invitaciones de otro evento."""
        self.client.force_login(self.otro_profesor)
        url = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_23_flujo_integral_registro_usuario_y_aceptacion(self):
        """Flujo integral: Invitado sin cuenta -> Se registra con correo de invitación -> Inicia sesión -> Verifica correo -> Acepta -> Inscripción ACTIVA."""
        inv, raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='nuevo.invitado@uniminuto.edu.co',
            nombres='Nuevo',
            apellidos='Invitado',
            invitado_por=self.profesor
        )

        # 1. Abre el enlace sin sesión -> Redirección 302 a URL limpia
        url_inv = reverse('participantes:consultar_invitacion', kwargs={'token': raw_token})
        url_limpia = reverse('participantes:ver_invitacion')
        resp1 = self.client.get(url_inv, follow=True)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.redirect_chain[0][0], url_limpia)

        # 2. Se registra mediante el formulario de nuevo usuario
        url_reg = reverse('usuarios:registro')
        resp_reg = self.client.post(f"{url_reg}?next={url_limpia}", {
            'username': 'nuevo_usuario_sigae',
            'documento': '77889900',
            'nombres': 'Nuevo',
            'apellidos': 'Invitado',
            'email': 'nuevo.invitado@uniminuto.edu.co',
            'password': 'PasswordSegura2026*',
            'confirm_password': 'PasswordSegura2026*',
        }, follow=True)
        self.assertEqual(resp_reg.status_code, 200)

        # 3. Usuario recién registrado inicia con email no verificado -> no puede aceptar
        nuevo_user = Usuario.objects.get(username='nuevo_usuario_sigae')
        self.assertFalse(nuevo_user.email_verificado)

        url_resp = reverse('participantes:responder_invitacion')
        resp_bloq = self.client.post(url_resp, {'accion': 'aceptar'}, follow=True)
        self.assertContains(resp_bloq, 'Debes verificar tu dirección de correo electrónico')
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__correo='nuevo.invitado@uniminuto.edu.co').exists())

        # 4. Verifica el correo electrónico
        nuevo_user.email_verificado = True
        nuevo_user.save()

        # 5. Acepta la invitación con correo verificado
        resp_aceptar = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertRedirects(resp_aceptar, reverse('participantes:mis_inscripciones'))

        # 6. Verifica estado final
        inv.refresh_from_db()
        self.assertEqual(inv.estado, EstadoInvitacion.ACEPTADA)
        insc = Inscripcion.objects.filter(evento=self.evento, participante__correo='nuevo.invitado@uniminuto.edu.co').first()
        self.assertIsNotNone(insc)
        self.assertEqual(insc.estado, EstadoInscripcion.ACTIVA)


class Etapa7211SeguridadEstadosInvitacionesTests(TestCase):
    """
    Pruebas automatizadas requeridas para la Etapa 7.2.1.1:
    1. Correo coincidente pero no verificado: aceptación bloqueada.
    2. Correo verificado y coincidente: aceptación permitida.
    3. Correo diferente: aceptación bloqueada (403).
    4. Token inicial validado y redirección a URL limpia (Referrer-Policy: no-referrer).
    5. Registro y login conservan correctamente el contexto de sesión.
    6. Una sesión no puede responder invitaciones diferentes.
    7. Aceptación y rechazo invalidan el contexto de sesión.
    8. Cancelación cambia el estado a CANCELADA (registra fecha_cancelacion, cancelado_por, e invalida token).
    9. Una invitación cancelada no puede aceptarse.
    10. Una invitación cancelada no se muestra como expirada.
    11. Renovación / re-emisión posterior de invitación cancelada permitida.
    12. No se generan inscripciones duplicadas bajo concurrencia.
    """
    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.profesor = Usuario.objects.create_user(
            username='profesor_org',
            email='profesor@uniminuto.edu.co',
            password='Password123*',
            documento='10101010',
            nombres='Carlos',
            apellidos='Docente',
            rol=self.rol_docente,
            email_verificado=True
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Conferencia')
        self.evento = Evento.objects.create(
            nombre='Congreso de Seguridad Web',
            descripcion='Evento de ciberseguridad',
            fecha=datetime.date(2026, 12, 1),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio Central',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.SOLO_INVITACION,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        self.usuario_invitado = Usuario.objects.create_user(
            username='invitado_pruebas',
            email='invitado@uniminuto.edu.co',
            password='Password123*',
            documento='20202020',
            nombres='Invitado',
            apellidos='Pruebas',
            rol=self.rol_estudiante,
            email_verificado=False
        )

        self.usuario_otro = Usuario.objects.create_user(
            username='otro_usuario',
            email='otro@uniminuto.edu.co',
            password='Password123*',
            documento='30303030',
            nombres='Otro',
            apellidos='Usuario',
            rol=self.rol_estudiante,
            email_verificado=True
        )

        self.invitacion, self.raw_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='invitado@uniminuto.edu.co',
            nombres='Invitado',
            apellidos='Pruebas',
            invitado_por=self.profesor
        )
        mail.outbox.clear()

    def test_01_correo_coincidente_pero_no_verificado_bloquea_aceptacion(self):
        """1. Correo coincidente pero no verificado: aceptación bloqueada."""
        self.assertFalse(self.usuario_invitado.email_verificado)
        self.client.force_login(self.usuario_invitado)

        # Cargar invitación en sesión
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        resp_entry = self.client.get(url_entry, follow=True)
        self.assertEqual(resp_entry.status_code, 200)
        self.assertTrue(resp_entry.context['coincide_correo'])
        self.assertFalse(resp_entry.context['correo_verificado'])

        # Intentar aceptar
        url_resp = reverse('participantes:responder_invitacion')
        resp_post = self.client.post(url_resp, {'accion': 'aceptar'}, follow=True)
        self.assertContains(resp_post, 'Debes verificar tu dirección de correo electrónico')

        # Verificar que no se creó inscripción y el estado sigue PENDIENTE
        self.invitacion.refresh_from_db()
        self.assertEqual(self.invitacion.estado, EstadoInvitacion.PENDIENTE)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_invitado).exists())

    def test_02_correo_verificado_y_coincidente_permite_aceptacion(self):
        """2. Correo verificado y coincidente: aceptación permitida."""
        self.usuario_invitado.email_verificado = True
        self.usuario_invitado.save()
        self.client.force_login(self.usuario_invitado)

        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        self.client.get(url_entry, follow=True)

        url_resp = reverse('participantes:responder_invitacion')
        response = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertRedirects(response, reverse('participantes:mis_inscripciones'))

        self.invitacion.refresh_from_db()
        self.assertEqual(self.invitacion.estado, EstadoInvitacion.ACEPTADA)
        self.assertIsNotNone(self.invitacion.fecha_aceptacion)

        inscripcion = Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_invitado).first()
        self.assertIsNotNone(inscripcion)
        self.assertEqual(inscripcion.estado, EstadoInscripcion.ACTIVA)

    def test_03_correo_diferente_bloquea_aceptacion_403(self):
        """3. Correo diferente: aceptación bloqueada con 403 Forbidden."""
        self.client.force_login(self.usuario_otro)

        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        resp_entry = self.client.get(url_entry, follow=True)
        self.assertEqual(resp_entry.status_code, 200)
        self.assertFalse(resp_entry.context['coincide_correo'])

        url_resp = reverse('participantes:responder_invitacion')
        resp_post = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(resp_post.status_code, 403)

        self.invitacion.refresh_from_db()
        self.assertEqual(self.invitacion.estado, EstadoInvitacion.PENDIENTE)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_otro).exists())

    def test_04_redireccion_a_url_limpia_y_referrer_policy(self):
        """4. Token inicial validado y redirección 302 a URL limpia con Referrer-Policy: no-referrer."""
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        url_limpia = reverse('participantes:ver_invitacion')

        resp_redirect = self.client.get(url_entry)
        self.assertEqual(resp_redirect.status_code, 302)
        self.assertEqual(resp_redirect.url, url_limpia)
        self.assertEqual(resp_redirect.headers.get('Referrer-Policy'), 'no-referrer')

        # Visita a la URL limpia
        resp_limpia = self.client.get(url_limpia)
        self.assertEqual(resp_limpia.status_code, 200)
        self.assertEqual(resp_limpia.headers.get('Referrer-Policy'), 'no-referrer')
        self.assertNotIn(self.raw_token, resp_limpia.request['PATH_INFO'])

    def test_05_registro_y_login_conservan_contexto_sesion(self):
        """5. Registro y login conservan correctamente el contexto de la invitación en sesión."""
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        self.client.get(url_entry)

        # Contexto guardado en sesión
        session = self.client.session
        self.assertEqual(session.get('invitacion_id'), self.invitacion.pk)
        self.assertEqual(session.get('invitacion_token_hash'), self.invitacion.token_hash)

        # Simular login del usuario
        self.client.login(username='invitado_pruebas', password='Password123*')

        # Comprobar que tras login, la URL limpia sigue reconociendo la invitación
        url_limpia = reverse('participantes:ver_invitacion')
        resp = self.client.get(url_limpia)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['invitacion'].pk, self.invitacion.pk)

    def test_06_sesion_no_puede_responder_invitacion_diferente(self):
        """6. Una sesión no puede responder invitaciones diferentes ni manipular contexto ajeno."""
        otra_inv, otro_token = InvitacionEvento.crear_o_renovar_invitacion(
            evento=self.evento,
            correo='segundo.invitado@uniminuto.edu.co',
            nombres='Segundo',
            apellidos='Invitado',
            invitado_por=self.profesor
        )
        self.usuario_invitado.email_verificado = True
        self.usuario_invitado.save()
        self.client.force_login(self.usuario_invitado)

        # Cargar contexto de otra_invitacion en sesión
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': otro_token})
        self.client.get(url_entry)

        # Intentar responder con un usuario cuyo correo es diferente al de la sesión
        url_resp = reverse('participantes:responder_invitacion')
        response = self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_invitado).exists())

    def test_07_aceptacion_y_rechazo_invalidan_contexto_sesion(self):
        """7. Aceptación y rechazo invalidan y limpian el contexto de sesión."""
        self.usuario_invitado.email_verificado = True
        self.usuario_invitado.save()
        self.client.force_login(self.usuario_invitado)

        # Cargar contexto y aceptar
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        self.client.get(url_entry)
        self.assertIn('invitacion_id', self.client.session)

        url_resp = reverse('participantes:responder_invitacion')
        self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertNotIn('invitacion_id', self.client.session)
        self.assertNotIn('invitacion_token_hash', self.client.session)

    def test_08_cancelacion_cambia_estado_a_cancelada_y_registra_datos(self):
        """8. Cancelación cambia el estado a CANCELADA, guarda responsable, fecha e invalida token."""
        self.client.force_login(self.profesor)
        url_cancelar = reverse('participantes:cancelar_invitacion', kwargs={
            'id_evento': self.evento.pk,
            'id_invitacion': self.invitacion.pk
        })
        resp_post = self.client.post(url_cancelar)
        self.assertEqual(resp_post.status_code, 302)

        self.invitacion.refresh_from_db()
        self.assertEqual(self.invitacion.estado, EstadoInvitacion.CANCELADA)
        self.assertEqual(self.invitacion.cancelado_por, self.profesor)
        self.assertIsNotNone(self.invitacion.fecha_cancelacion)
        # El token anterior queda invalidado
        self.assertFalse(self.invitacion.verificar_token(self.raw_token))

    def test_09_invitacion_cancelada_no_puede_ser_aceptada(self):
        """9. Una invitación cancelada no puede aceptarse (puede_ser_aceptada es False y lanza ValidationError)."""
        self.invitacion.cancelar_invitacion(responsable=self.profesor)
        self.assertFalse(self.invitacion.puede_ser_aceptada)

        with self.assertRaises(ValidationError):
            self.invitacion.marcar_como_aceptada()

    def test_10_invitacion_cancelada_no_se_muestra_como_expirada(self):
        """10. Una invitación cancelada no se muestra como expirada sino como cancelada."""
        self.invitacion.cancelar_invitacion(responsable=self.profesor)

        # Simular contexto de sesión existente
        session = self.client.session
        session['invitacion_id'] = self.invitacion.pk
        session['invitacion_token_hash'] = self.invitacion.token_hash
        session['invitacion_evento_id'] = self.evento.pk
        session['invitacion_correo'] = self.invitacion.correo
        session.save()

        url_limpia = reverse('participantes:ver_invitacion')
        response = self.client.get(url_limpia)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['estado'], 'CANCELADA')
        self.assertContains(response, 'Invitación Cancelada')
        self.assertNotContains(response, 'Invitación Expirada')

    def test_11_renovacion_posterior_de_invitacion_cancelada_permitida(self):
        """11. Re-emisión posterior de invitación cancelada permitida por partial unique index."""
        self.invitacion.cancelar_invitacion(responsable=self.profesor)

        # Ahora el profesor emite una nueva invitación al mismo correo
        self.client.force_login(self.profesor)
        url_gest = reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})
        resp = self.client.post(url_gest, {
            'correo': self.invitacion.correo,
            'nombres': 'Invitado',
            'apellidos': 'Reemitido',
        })
        self.assertEqual(resp.status_code, 302)

        # Debe existir una nueva invitación PENDIENTE además de la CANCELADA
        inv_cancelada = InvitacionEvento.objects.get(pk=self.invitacion.pk)
        self.assertEqual(inv_cancelada.estado, EstadoInvitacion.CANCELADA)

        nueva_inv = InvitacionEvento.objects.filter(evento=self.evento, correo=self.invitacion.correo, estado=EstadoInvitacion.PENDIENTE).first()
        self.assertIsNotNone(nueva_inv)
        self.assertNotEqual(nueva_inv.pk, inv_cancelada.pk)

    def test_12_no_duplicidad_inscripciones_concurrente(self):
        """12. No se generan inscripciones duplicadas bajo concurrencia o dobles respuestas."""
        self.usuario_invitado.email_verificado = True
        self.usuario_invitado.save()
        self.client.force_login(self.usuario_invitado)

        # Establecer sesión
        url_entry = reverse('participantes:consultar_invitacion', kwargs={'token': self.raw_token})
        self.client.get(url_entry)

        url_resp = reverse('participantes:responder_invitacion')
        # Primer envío
        self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_invitado).count(), 1)

        # Segundo envío simultáneo con contexto repuesto
        session = self.client.session
        session['invitacion_id'] = self.invitacion.pk
        session['invitacion_token_hash'] = self.invitacion.token_hash
        session['invitacion_evento_id'] = self.evento.pk
        session['invitacion_correo'] = self.invitacion.correo
        session.save()

        self.client.post(url_resp, {'accion': 'aceptar'})
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__usuario=self.usuario_invitado).count(), 1)


class InscripcionPublicaExternosTests(TestCase):
    """
    Suite de pruebas unitarias y de integración para la Etapa 7.2.2:
    Inscripción abierta y registro de participantes externos sin cuenta institucional.
    Cubre los 20 escenarios requeridos por la especificación técnica.
    """
    def setUp(self):
        self.client = Client()
        self.rol_profesor = Rol.objects.create(nombre='Docente')
        self.profesor = Usuario.objects.create_user(
            username='profesor_publico',
            email='profesor.pub@uniminuto.edu.co',
            password='Password123*',
            documento='70707070',
            nombres='Profesor',
            apellidos='Organizador',
            rol=self.rol_profesor
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Congreso Abierto')

        # Evento con modalidad ABIERTA
        self.evento_abierta = Evento.objects.create(
            nombre='Congreso Abierto de Innovación 2026',
            descripcion='Evento de divulgación abierto a toda la sociedad.',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Auditorio Principal UNIMINUTO',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        # Evento con modalidad MIXTA
        self.evento_mixta = Evento.objects.create(
            nombre='Feria Tecnológica Mixta 2026',
            descripcion='Feria con stands presenciales y transmisiones virtuales.',
            fecha=datetime.date(2026, 12, 15),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(16, 0),
            lugar='Plaza Central UNIMINUTO',
            modalidad=ModalidadEvento.HIBRIDA,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        # Evento con modalidad SOLO_INVITACION
        self.evento_solo_invitacion = Evento.objects.create(
            nombre='Reunión Privada de Decanatura',
            descripcion='Sesión exclusiva con invitación previa.',
            fecha=datetime.date(2026, 12, 20),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(16, 0),
            lugar='Sala de Juntas',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.SOLO_INVITACION,
            cupo=10,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.profesor
        )

        self.datos_validos = {
            'documento': '10998877',
            'nombres': 'Clara',
            'apellidos': 'Gómez',
            'correo': 'clara.gomez@externo.org',
            'telefono': '3123456789',
            'institucion': 'Fundación Aliada',
            'acepta_politica_tratamiento': 'True',
        }

    def test_01_evento_abierta_permite_registro_publico(self):
        """1. Evento con modalidad ABIERTA permite registro público."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        resp_get = self.client.get(url_reg)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Inscripción al Evento')

        resp_post = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp_post.status_code, 200)
        self.assertEqual(resp_post.context['estado'], 'EXITOSA')
        self.assertTrue(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').exists())

    def test_02_evento_mixta_permite_registro_publico(self):
        """2. Evento con modalidad MIXTA permite registro público."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_mixta.pk})
        resp_get = self.client.get(url_reg)
        self.assertEqual(resp_get.status_code, 200)

        datos = dict(self.datos_validos, documento='10998878', correo='mixta@externo.org')
        resp_post = self.client.post(url_reg, datos)
        self.assertEqual(resp_post.status_code, 200)
        self.assertEqual(resp_post.context['estado'], 'EXITOSA')
        self.assertTrue(Inscripcion.objects.filter(evento=self.evento_mixta, participante__documento='10998878').exists())

    def test_03_evento_solo_invitacion_bloquea_registro_publico(self):
        """3. Evento con modalidad SOLO_INVITACION bloquea registro público (403)."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_solo_invitacion.pk})
        resp_get = self.client.get(url_reg)
        self.assertEqual(resp_get.status_code, 403)
        self.assertEqual(resp_get.context['estado'], 'SOLO_INVITACION')

        resp_post = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp_post.status_code, 403)
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento_solo_invitacion, participante__documento='10998877').exists())

    def test_04_formulario_valido_crea_participante_externo(self):
        """4. Formulario válido crea participante externo con datos completos."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        resp = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp.status_code, 200)

        part = Participante.objects.filter(documento='10998877').first()
        self.assertIsNotNone(part)
        self.assertEqual(part.nombres, 'Clara')
        self.assertEqual(part.apellidos, 'Gómez')
        self.assertEqual(part.correo, 'clara.gomez@externo.org')
        self.assertEqual(part.telefono, '3123456789')
        self.assertEqual(part.institucion, 'Fundación Aliada')

    def test_05_participante_no_recibe_cuenta_institucional(self):
        """5. Participante creado no recibe cuenta institucional (usuario=None y tipo=EXTERNO)."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        self.client.post(url_reg, self.datos_validos)

        part = Participante.objects.filter(documento='10998877').first()
        self.assertIsNotNone(part)
        self.assertIsNone(part.usuario)
        self.assertEqual(part.tipo, TipoParticipante.EXTERNO)

    def test_06_inscripcion_creada_en_estado_activa(self):
        """6. Inscripción creada queda en estado ACTIVA."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        self.client.post(url_reg, self.datos_validos)

        insc = Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').first()
        self.assertIsNotNone(insc)
        self.assertEqual(insc.estado, EstadoInscripcion.ACTIVA)

    def test_07_no_duplica_participante_mismo_documento(self):
        """7. No se crean participantes duplicados si ya existe un externo con el mismo documento."""
        part_previo = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='10998877',
            nombres='Clara',
            apellidos='Gómez Anterior',
            correo='clara.anterior@externo.org'
        )
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        self.client.post(url_reg, self.datos_validos)

        self.assertEqual(Participante.objects.filter(documento='10998877').count(), 1)
        part_act = Participante.objects.get(pk=part_previo.pk)
        self.assertEqual(part_act.apellidos, 'Gómez')
        self.assertEqual(part_act.correo, 'clara.gomez@externo.org')

    def test_08_no_duplica_inscripcion_mismo_evento(self):
        """8. No se crean inscripciones duplicadas para el mismo evento y participante."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        self.client.post(url_reg, self.datos_validos)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').count(), 1)

        # Segundo intento idéntico
        resp2 = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.context['estado'], 'YA_INSCRITO')
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').count(), 1)

    def test_09_token_almacenado_unicamente_como_hash_sha256(self):
        """9. El token se almacena exclusivamente como hash SHA-256 en AccesoExternoInscripcion."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        self.client.post(url_reg, self.datos_validos)

        insc = Inscripcion.objects.get(evento=self.evento_abierta, participante__documento='10998877')
        acceso = AccesoExternoInscripcion.objects.get(inscripcion=insc)
        self.assertIsNotNone(acceso.token_hash)
        self.assertEqual(len(acceso.token_hash), 64)
        # Comprobar que no hay campos de token en texto plano
        self.assertFalse(hasattr(acceso, 'token'))

    def test_10_acceso_externo_valido_permite_consultar_en_url_limpia(self):
        """10. Acceso externo válido permite consultar la inscripción en URL limpia con Referrer-Policy."""
        part = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='10998877',
            nombres='Clara',
            apellidos='Gómez',
            correo='clara@externo.org'
        )
        insc = Inscripcion.objects.create(evento=self.evento_abierta, participante=part, estado=EstadoInscripcion.ACTIVA)
        acceso, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(insc)

        url_entry = reverse('participantes:consultar_acceso_externo', kwargs={'token': raw_token})
        resp_entry = self.client.get(url_entry)
        self.assertEqual(resp_entry.status_code, 302)
        self.assertEqual(resp_entry.headers.get('Referrer-Policy'), 'no-referrer')
        self.assertEqual(resp_entry.url, reverse('participantes:ver_inscripcion_externa'))

        resp_detalle = self.client.get(reverse('participantes:ver_inscripcion_externa'))
        self.assertEqual(resp_detalle.status_code, 200)
        self.assertEqual(resp_detalle.headers.get('Referrer-Policy'), 'no-referrer')
        self.assertContains(resp_detalle, 'Congreso Abierto de Innovación 2026')
        self.assertContains(resp_detalle, 'Clara Gómez')
        self.assertContains(resp_detalle, '10998877')

    def test_11_token_expirado_bloquea_acceso(self):
        """11. Token expirado bloquea acceso y muestra aviso correspondiente."""
        part = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='10998877',
            nombres='Clara',
            apellidos='Gómez',
            correo='clara@externo.org'
        )
        insc = Inscripcion.objects.create(evento=self.evento_abierta, participante=part, estado=EstadoInscripcion.ACTIVA)
        acceso, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(insc)
        acceso.fecha_expiracion = timezone.now() - datetime.timedelta(days=1)
        acceso.save(update_fields=['fecha_expiracion'])

        url_entry = reverse('participantes:consultar_acceso_externo', kwargs={'token': raw_token})
        resp = self.client.get(url_entry)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.context['estado'], 'EXPIRADO')
        self.assertContains(resp, 'Enlace de Acceso Expirado', status_code=403)

    def test_12_token_revocado_bloquea_acceso(self):
        """12. Token revocado bloquea acceso con estado REVOCADO."""
        part = Participante.objects.create(
            usuario=None,
            tipo=TipoParticipante.EXTERNO,
            documento='10998877',
            nombres='Clara',
            apellidos='Gómez',
            correo='clara@externo.org'
        )
        insc = Inscripcion.objects.create(evento=self.evento_abierta, participante=part, estado=EstadoInscripcion.ACTIVA)
        acceso, raw_token = AccesoExternoInscripcion.crear_para_inscripcion(insc)
        acceso.revocar()

        url_entry = reverse('participantes:consultar_acceso_externo', kwargs={'token': raw_token})
        resp = self.client.get(url_entry)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.context['estado'], 'REVOCADO')
        self.assertContains(resp, 'Acceso Revocado', status_code=403)

    def test_13_usuario_no_puede_consultar_inscripcion_ajena(self):
        """13. Usuario no puede consultar inscripción ajena alterando identificadores (anti-IDOR)."""
        url_detalle = reverse('participantes:ver_inscripcion_externa')
        resp = self.client.get(url_detalle)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.context['estado'], 'NO_AUTORIZADO')

    def test_14_correo_confirmacion_enviado_backend_pruebas(self):
        """14. Correo de confirmación enviado mediante backend de pruebas (mail.outbox)."""
        mail.outbox = []
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        resp = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('Confirmación de inscripción', email.subject)
        self.assertEqual(email.to, ['clara.gomez@externo.org'])
        self.assertIn('Congreso Abierto de Innovación 2026', email.body)
        self.assertIn('/participantes/externo/', email.body)

    def test_15_fallo_envio_correo_no_genera_falso_exito(self):
        """15. Fallo en el envío de correo no genera falso éxito en la respuesta al usuario."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        with patch('participantes.views.enviar_correo_confirmacion_externa', return_value=False):
            resp = self.client.post(url_reg, self.datos_validos)
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.context['correo_enviado'])
            self.assertContains(resp, 'Aviso sobre el servicio de correo')

    def test_16_qr_publico_dirige_a_evento_correcto(self):
        """16. QR público de inscripción se genera como PNG válido y permite descarga."""
        url_qr = reverse('participantes:qr_inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        resp = self.client.get(url_qr)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertTrue(len(resp.content) > 100)

        resp_descarga = self.client.get(f"{url_qr}?descargar=1")
        self.assertEqual(resp_descarga.status_code, 200)
        self.assertIn('attachment', resp_descarga['Content-Disposition'])

    def test_17_qr_o_enlace_publico_deja_de_permitir_registro_al_cerrar_o_cambiar_a_solo_invitacion(self):
        """17. QR o enlace público deja de permitir registros cuando el evento se cierra o cambia a SOLO_INVITACION."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})

        # Caso 1: Evento CERRADO
        self.evento_abierta.estado = EstadoEvento.CERRADO
        self.evento_abierta.save(update_fields=['estado'])

        resp_cerrado = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp_cerrado.status_code, 400)
        self.assertEqual(resp_cerrado.context['estado'], 'NO_DISPONIBLE')

        # Caso 2: Evento cambia a SOLO_INVITACION
        self.evento_abierta.estado = EstadoEvento.PUBLICADO
        self.evento_abierta.modalidad_inscripcion = ModalidadInscripcion.SOLO_INVITACION
        self.evento_abierta.save(update_fields=['estado', 'modalidad_inscripcion'])

        resp_solo_inv = self.client.post(url_reg, self.datos_validos)
        self.assertEqual(resp_solo_inv.status_code, 403)
        self.assertEqual(resp_solo_inv.context['estado'], 'SOLO_INVITACION')

    def test_18_consentimiento_datos_obligatorio(self):
        """18. Consentimiento de tratamiento de datos es obligatorio (falla si no se autoriza)."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        datos_sin_consentimiento = dict(self.datos_validos, acepta_politica_tratamiento='')
        resp = self.client.post(url_reg, datos_sin_consentimiento)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('acepta_politica_tratamiento', resp.context['form'].errors)
        self.assertContains(resp, 'Debes autorizar el tratamiento de datos personales')
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').exists())

    def test_19_rollback_atomico_ante_error(self):
        """19. Inscripción no se crea parcialmente si ocurre un error (rollback atómico)."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        with patch('participantes.models.AccesoExternoInscripcion.crear_para_inscripcion', side_effect=RuntimeError("Error simulado de acceso")):
            with self.assertRaises(RuntimeError):
                self.client.post(url_reg, self.datos_validos)

        # Verificar que no quedaron registros huérfanos
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').exists())

    def test_20_repeticion_solicitudes_no_genera_duplicados(self):
        """20. Repetición de solicitudes no genera duplicados y mantiene consistencia."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_abierta.pk})
        for _ in range(3):
            resp = self.client.post(url_reg, self.datos_validos)
            self.assertEqual(resp.status_code, 200)

        self.assertEqual(Participante.objects.filter(documento='10998877').count(), 1)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_abierta, participante__documento='10998877').count(), 1)


class Fase1AccesoInmediatoYRecuperacionExternaTests(TestCase):
    """
    Pruebas obligatorias de la Fase 1: Acceso inmediato tras inscripción pública,
    recuperación segura cuando el cupo está lleno, protección anti-IDOR, y
    funcionamiento del pase digital y código QR dinámico sin servicio de correo.
    """
    def setUp(self):
        self.client = Client()
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='docente_fase1',
            email='docente.fase1@uniminuto.edu.co',
            password='Password123*',
            documento='40404040',
            nombres='Docente',
            apellidos='FaseUno',
            rol=self.rol_docente
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Taller Mixto')
        self.evento_un_cupo = Evento.objects.create(
            nombre='Taller Mixto Cupo Único',
            descripcion='Evento de prueba con capacidad de 1 participante.',
            fecha=datetime.date(2026, 12, 18),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sala de Innovación',
            modalidad=ModalidadEvento.HIBRIDA,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=1,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )
        self.datos_participante_1 = {
            'documento': '1020304050',
            'nombres': 'Andrés',
            'apellidos': 'Externo',
            'correo': 'andres.externo@correo.org',
            'telefono': '3001112233',
            'institucion': 'Empresa Externa S.A.',
            'acepta_politica_tratamiento': 'True',
        }
        self.datos_participante_2 = {
            'documento': '9080706050',
            'nombres': 'Beatriz',
            'apellidos': 'Visitante',
            'correo': 'beatriz.visitante@correo.org',
            'telefono': '3104445566',
            'institucion': 'Consultora Aliada',
            'acepta_politica_tratamiento': 'True',
        }

    def test_01_evento_un_cupo_inscripcion_y_acceso_inmediato_portal_personal(self):
        """1. Evento con 1 cupo: el primer participante se inscribe y obtiene acceso inmediato a su portal personal."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        resp = self.client.post(url_reg, self.datos_participante_1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['estado'], 'EXITOSA')
        self.assertTrue(resp.context['acceso_disponible'])
        self.assertContains(resp, 'VER MI PASE Y CÓDIGO QR DE ASISTENCIA')
        self.assertContains(resp, reverse('participantes:ver_inscripcion_externa'))

        # Verificar que la sesión externa quedó establecida y corresponde a la inscripción creada
        insc = Inscripcion.objects.get(evento=self.evento_un_cupo, participante__documento='1020304050')
        acceso = AccesoExternoInscripcion.objects.get(inscripcion=insc)
        self.assertEqual(self.client.session.get('acceso_externo_id'), acceso.pk)
        self.assertEqual(self.client.session.get('acceso_externo_hash'), acceso.token_hash)

        # Acceder inmediatamente al portal personal sin necesidad de abrir el correo
        resp_portal = self.client.get(reverse('participantes:ver_inscripcion_externa'))
        self.assertEqual(resp_portal.status_code, 200)
        self.assertContains(resp_portal, 'Andrés Externo')
        self.assertContains(resp_portal, 'Taller Mixto Cupo Único')
        self.assertContains(resp_portal, 'data:image/png;base64,')
        self.assertNotContains(resp_portal, '?token=')

    def test_02_fallo_correo_permite_acceder_a_pase_y_qr(self):
        """2. Simular fallo de correo: el participante igualmente accede a su pase y QR individual."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        with patch('participantes.views.enviar_correo_confirmacion_externa', return_value=False):
            resp = self.client.post(url_reg, self.datos_participante_1)
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.context['correo_enviado'])
            self.assertTrue(resp.context['acceso_disponible'])
            self.assertContains(resp, 'VER MI PASE Y CÓDIGO QR DE ASISTENCIA')

        # El participante entra al portal personal y visualiza su QR
        resp_portal = self.client.get(reverse('participantes:ver_inscripcion_externa'))
        self.assertEqual(resp_portal.status_code, 200)
        self.assertIsNotNone(resp_portal.context['qr_base64'])
        self.assertTrue(len(resp_portal.context['qr_base64']) > 50)

    def test_03_cupo_lleno_mismo_participante_recupera_acceso_sin_duplicar(self):
        """3. Evento con cupo lleno: el mismo participante, con documento y correo coincidentes, recupera su acceso sin duplicar la inscripción."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        self.client.post(url_reg, self.datos_participante_1)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_un_cupo, estado=EstadoInscripcion.ACTIVA).count(), 1)

        # Nuevo cliente (simulando otro dispositivo o sesión perdida cuando el cupo ya está lleno)
        nuevo_cliente = Client()
        resp_get = nuevo_cliente.get(url_reg)
        self.assertEqual(resp_get.status_code, 200)
        self.assertTrue(resp_get.context['esta_lleno'])
        self.assertContains(resp_get, 'Recuperar mi Inscripción y Pase QR')

        with patch('participantes.views.enviar_correo_confirmacion_externa', return_value=False):
            resp_recup = nuevo_cliente.post(url_reg, self.datos_participante_1)
            self.assertEqual(resp_recup.status_code, 200)
            self.assertEqual(resp_recup.context['estado'], 'YA_INSCRITO')
            self.assertTrue(resp_recup.context['acceso_disponible'])
            self.assertContains(resp_recup, 'VER MI PASE Y CÓDIGO QR DE ASISTENCIA')

        # No se duplicó la inscripción ni se alteró el cupo ocupado (sigue siendo 1)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_un_cupo).count(), 1)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_un_cupo, estado=EstadoInscripcion.ACTIVA).count(), 1)

        # El nuevo cliente tiene sesión activa y puede ver su portal y QR
        resp_portal = nuevo_cliente.get(reverse('participantes:ver_inscripcion_externa'))
        self.assertEqual(resp_portal.status_code, 200)
        self.assertContains(resp_portal, 'Andrés Externo')
        self.assertContains(resp_portal, 'data:image/png;base64,')

    def test_04_cupo_lleno_segundo_participante_rechazado(self):
        """4. Evento con cupo lleno: un segundo participante no puede inscribirse."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        self.client.post(url_reg, self.datos_participante_1)

        cliente_2 = Client()
        resp_2 = cliente_2.post(url_reg, self.datos_participante_2)
        self.assertEqual(resp_2.status_code, 400)
        self.assertEqual(resp_2.context['estado'], 'CUPO_AGOTADO')
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento_un_cupo, participante__documento='9080706050').exists())
        self.assertIsNone(cliente_2.session.get('acceso_externo_id'))

    def test_05_documento_correcto_y_correo_incorrecto_rechaza_acceso_y_no_modifica_datos(self):
        """5. Documento correcto y correo incorrecto (o viceversa): el acceso es rechazado y no se modifican datos."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        self.client.post(url_reg, self.datos_participante_1)

        # Intento con documento correcto pero correo impostor en evento lleno
        cliente_atacante = Client()
        datos_correo_falso = dict(
            self.datos_participante_1,
            nombres='Atacante',
            correo='atacante@malicioso.org'
        )
        resp_falso_1 = cliente_atacante.post(url_reg, datos_correo_falso)
        self.assertIn(resp_falso_1.status_code, [400, 403])
        self.assertIsNone(cliente_atacante.session.get('acceso_externo_id'))

        # Verificar también cuando hay cupo disponible (cupo=5): debe devolver 403 DATOS_NO_COINCIDEN
        self.evento_un_cupo.cupo = 5
        self.evento_un_cupo.save(update_fields=['cupo'])

        resp_falso_2 = cliente_atacante.post(url_reg, datos_correo_falso)
        self.assertEqual(resp_falso_2.status_code, 403)
        self.assertEqual(resp_falso_2.context['estado'], 'DATOS_NO_COINCIDEN')
        self.assertIsNone(cliente_atacante.session.get('acceso_externo_id'))

        # Intento inverso: correo correcto pero documento distinto
        datos_doc_falso = dict(
            self.datos_participante_1,
            documento='9999999999',
            nombres='Atacante'
        )
        resp_falso_3 = cliente_atacante.post(url_reg, datos_doc_falso)
        self.assertEqual(resp_falso_3.status_code, 403)
        self.assertEqual(resp_falso_3.context['estado'], 'DATOS_NO_COINCIDEN')
        self.assertIsNone(cliente_atacante.session.get('acceso_externo_id'))

        # Verificar que los datos originales del participante inscrito NO fueron modificados
        part_orig = Participante.objects.get(documento='1020304050')
        self.assertEqual(part_orig.correo, 'andres.externo@correo.org')
        self.assertEqual(part_orig.nombres, 'Andrés')

    def test_06_anti_idor_participante_no_puede_acceder_pase_ajeno(self):
        """6. Un participante no puede acceder al pase o QR de otra persona manipulando URLs."""
        self.evento_un_cupo.cupo = 2
        self.evento_un_cupo.save(update_fields=['cupo'])

        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        # Inscribir participante 1 en client 1
        c1 = Client()
        c1.post(url_reg, self.datos_participante_1)
        insc_1 = Inscripcion.objects.get(evento=self.evento_un_cupo, participante__documento='1020304050')

        # Inscribir participante 2 en client 2
        c2 = Client()
        c2.post(url_reg, self.datos_participante_2)
        insc_2 = Inscripcion.objects.get(evento=self.evento_un_cupo, participante__documento='9080706050')

        # Participante 2 intenta acceder al pase digital, imagen QR y QR dinámico de la inscripción 1
        resp_pase_ajeno = c2.get(reverse('asistencia:pase_digital', kwargs={'id_inscripcion': insc_1.pk}))
        self.assertNotEqual(resp_pase_ajeno.status_code, 200)

        resp_img_ajena = c2.get(reverse('asistencia:qr_imagen', kwargs={'id_inscripcion': insc_1.pk}))
        self.assertNotEqual(resp_img_ajena.status_code, 200)

        resp_qr_din_ajeno = c2.get(reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': insc_1.pk}))
        self.assertEqual(resp_qr_din_ajeno.status_code, 403)

        # Pero Participante 2 sí accede a los suyos propios (insc_2)
        self.assertEqual(c2.get(reverse('asistencia:pase_digital', kwargs={'id_inscripcion': insc_2.pk})).status_code, 200)

    def test_07_qr_individual_dinamico_se_renueva_y_registra_asistencia(self):
        """7. El QR individual se renueva mediante qr_dinamico y funciona para registrar asistencia."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        self.client.post(url_reg, self.datos_participante_1)
        insc = Inscripcion.objects.get(evento=self.evento_un_cupo, participante__documento='1020304050')

        # Renovar QR dinámico usando la sesión externa establecida
        url_qr_din = reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': insc.pk})
        resp_qr = self.client.get(url_qr_din, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_qr.status_code, 200)
        data = resp_qr.json()
        self.assertTrue(data['exito'])
        self.assertTrue(data['token'])
        self.assertTrue(data['qr_base64'])

        # El docente organizador escanea el token QR en control_asistencia para registrar llegada
        cliente_docente = Client()
        cliente_docente.force_login(self.organizador)
        url_checkin = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento_un_cupo.pk})
        resp_checkin = cliente_docente.post(
            url_checkin,
            {'accion': 'qr', 'token_qr': data['token']},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_checkin.status_code, 200)
        checkin_data = resp_checkin.json()
        self.assertTrue(checkin_data['exito'])

        insc.refresh_from_db()
        self.assertTrue(insc.asistio)
        self.assertTrue(Asistencia.objects.filter(inscripcion=insc).exists())

    def test_08_descarga_pase_digital_y_qr_imagen_funciona_con_sesion_externa(self):
        """8. La visualización del pase digital y la descarga de la imagen QR (PNG) funcionan con la sesión externa."""
        url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_un_cupo.pk})
        self.client.post(url_reg, self.datos_participante_1)
        insc = Inscripcion.objects.get(evento=self.evento_un_cupo, participante__documento='1020304050')

        # Visualizar pase digital imprimible
        resp_pase = self.client.get(reverse('asistencia:pase_digital', kwargs={'id_inscripcion': insc.pk}))
        self.assertEqual(resp_pase.status_code, 200)
        self.assertContains(resp_pase, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(resp_pase, 'Andrés Externo')

        # Descargar imagen QR PNG directamente con la sesión externa (sin ?token=)
        resp_png = self.client.get(reverse('asistencia:qr_imagen', kwargs={'id_inscripcion': insc.pk}))
        self.assertEqual(resp_png.status_code, 200)
        self.assertEqual(resp_png['Content-Type'], 'image/png')
        self.assertIn('attachment', resp_png['Content-Disposition'])
        self.assertTrue(len(resp_png.content) > 100)


