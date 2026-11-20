"""
Suite exhaustiva de pruebas automatizadas para RF-24 a RF-30:
Sistema obligatorio de calificación de eventos mediante estrellas (1 a 5).
Cubre los 36 casos obligatorios (Asistencia, Calificación, Roles/Permisos y Estadísticas)
más validaciones de integración con ambos flujos de salida QR y dashboard analítico.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Auditoria
from asistencia.models import Asistencia, EstadoAsistencia, MetodoAsistencia
from asistencia.services import (
    generar_token_qr,
    generar_token_salida_evento,
    validar_token_salida_evento,
    iniciar_sesion_salida_service,
    cerrar_sesion_salida_service,
    rotar_nonce_salida_service,
    registrar_asistencia_llegada,
    registrar_asistencia_salida,
)
from eventos.models import (
    CategoriaEvento,
    Evento,
    ModalidadEvento,
    ModalidadInscripcion,
    EstadoEvento,
    CalificacionEvento,
)
from eventos.services import (
    verificar_elegibilidad_calificacion,
    obtener_evaluaciones_pendientes,
    registrar_o_actualizar_calificacion,
    calcular_estadisticas_calificacion,
    MENSAJE_SIN_CALIFICACIONES,
)
from participantes.models import (
    Participante,
    Inscripcion,
    TipoParticipante,
    EstadoInscripcion,
)
from usuarios.models import Rol, Usuario


FAST_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class SistemaCalificacionEstrellasBaseTestCase(TestCase):
    """Configuración base reutilizable para pruebas de RF-24 a RF-30."""

    def setUp(self):
        self.client = Client()
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.admin = Usuario.objects.create_user(
            username='admin_calif',
            email='admin_calif@uniminuto.edu.co',
            password='Password123*',
            documento='90000001',
            nombres='Laura',
            apellidos='Administradora',
            rol=self.rol_admin,
            is_staff=True,
        )
        self.docente = Usuario.objects.create_user(
            username='docente_calif',
            email='docente_calif@uniminuto.edu.co',
            password='Password123*',
            documento='90000002',
            nombres='Carlos',
            apellidos='Docente',
            rol=self.rol_docente,
        )
        self.estudiante_1 = Usuario.objects.create_user(
            username='est_calif_1',
            email='est1@uniminuto.edu.co',
            password='Password123*',
            documento='90000011',
            nombres='Ana',
            apellidos='Estrella',
            rol=self.rol_estudiante,
        )
        self.estudiante_2 = Usuario.objects.create_user(
            username='est_calif_2',
            email='est2@uniminuto.edu.co',
            password='Password123*',
            documento='90000012',
            nombres='Luis',
            apellidos='Participante',
            rol=self.rol_estudiante,
        )
        self.estudiante_3 = Usuario.objects.create_user(
            username='est_calif_3',
            email='est3@uniminuto.edu.co',
            password='Password123*',
            documento='90000013',
            nombres='Sofia',
            apellidos='Tercera',
            rol=self.rol_estudiante,
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Seminarios Académicos')
        self.evento = Evento.objects.create(
            nombre='Seminario de Arquitectura de Software',
            descripcion='Actividad académica sobre arquitectura limpia.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio B201',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente,
        )

        self.part_1 = Participante.objects.create(
            usuario=self.estudiante_1,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.estudiante_1.documento,
            nombres=self.estudiante_1.nombres,
            apellidos=self.estudiante_1.apellidos,
            correo=self.estudiante_1.email,
        )
        self.part_2 = Participante.objects.create(
            usuario=self.estudiante_2,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.estudiante_2.documento,
            nombres=self.estudiante_2.nombres,
            apellidos=self.estudiante_2.apellidos,
            correo=self.estudiante_2.email,
        )
        self.part_3 = Participante.objects.create(
            usuario=self.estudiante_3,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.estudiante_3.documento,
            nombres=self.estudiante_3.nombres,
            apellidos=self.estudiante_3.apellidos,
            correo=self.estudiante_3.email,
        )

        self.inscripcion_1 = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_1,
            estado=EstadoInscripcion.ACTIVA,
        )
        self.inscripcion_2 = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_2,
            estado=EstadoInscripcion.ACTIVA,
        )

    def _registrar_entrada_y_salida(self, inscripcion, hora_entrada=datetime.time(8, 10), hora_salida=datetime.time(10, 30)):
        """Helper para dejar una inscripción con entrada y salida válidas."""
        asistencia, _ = Asistencia.objects.update_or_create(
            inscripcion=inscripcion,
            defaults={
                'fecha': self.evento.fecha,
                'hora_entrada': hora_entrada,
                'hora_salida': hora_salida,
                'metodo': MetodoAsistencia.QR,
                'estado': EstadoAsistencia.REGISTRADA,
            },
        )
        return asistencia


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class AsistenciaIntegracionCalificacionTests(SistemaCalificacionEstrellasBaseTestCase):
    """Sección A (Casos 1 a 6): Integración con registro de entrada, salida y QR dinámico."""

    def test_01_estudiante_registra_entrada_correctamente(self):
        """1. El estudiante puede registrar correctamente su entrada mediante QR dinámico."""
        token_llegada = generar_token_qr(self.inscripcion_1)
        self.client.force_login(self.docente)
        url_ctrl = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        resp = self.client.post(url_ctrl, {'token_qr': token_llegada}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['exito'])
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_1)
        self.assertEqual(asistencia.estado, EstadoAsistencia.REGISTRADA)
        self.assertIsNotNone(asistencia.hora_entrada)
        self.assertIsNone(asistencia.hora_salida)

    def test_02_estudiante_registra_salida_mediante_qr_valido(self):
        """2. El estudiante puede registrar correctamente su salida mediante el QR válido."""
        registrar_asistencia_llegada(self.inscripcion_1, metodo=MetodoAsistencia.QR, operador=self.docente)
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.estudiante_1)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        resp = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['exito'])
        self.assertTrue(data['requiere_calificacion'])
        self.assertEqual(data['url_calificacion'], reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))

    def test_03_salida_queda_persistida_antes_de_presentar_calificacion(self):
        """3. El registro de salida queda persistido en BD antes de presentar la calificación."""
        Asistencia.objects.create(
            inscripcion=self.inscripcion_1,
            fecha=self.evento.fecha,
            hora_entrada=(timezone.localtime(timezone.now()) - datetime.timedelta(minutes=25)).time(),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.estudiante_1)
        url_pub = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk}) + f"?token_evento={token_salida}"
        resp = self.client.post(url_pub, {'token_evento': token_salida})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '¡Salida Registrada con Éxito!')
        self.assertContains(resp, '¡Gracias por participar!')
        self.assertContains(resp, '¿Cómo calificas este evento?')
        self.assertContains(resp, 'Enviar calificación')

        # La salida ya está persistida incluso sin haber enviado calificación
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_1)
        self.assertIsNotNone(asistencia.hora_salida)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_04_sistema_no_permite_registrar_salida_invalida(self):
        """4. El sistema no permite registrar una salida con token inválido o sin entrada."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_valido = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.estudiante_1)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})

        # Token alterado
        resp_alt = self.client.post(url_reg, {'token_salida': token_valido + 'tampered'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_alt.status_code, 400)
        self.assertFalse(resp_alt.json()['exito'])

        # Sin entrada previa
        resp_sin_ent = self.client.post(url_reg, {'token_salida': token_valido}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_sin_ent.status_code, 400)
        self.assertEqual(resp_sin_ent.json()['codigo'], 'ASISTENCIA_NO_REGISTRADA')

    def test_05_implementacion_no_afecta_rotacion_ni_expiracion_qr_dinamico(self):
        """5. La implementación no afecta la rotación de nonce ni la expiración del QR dinámico."""
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_v1 = generar_token_salida_evento(self.evento, control=control)

        # Rotar nonce invalida el token previo
        rotar_nonce_salida_service(self.evento, operador=self.docente)
        control.refresh_from_db()
        token_v2 = generar_token_salida_evento(self.evento, control=control)

        ok_v1, cod_v1, _ = validar_token_salida_evento(token_v1, self.evento)
        self.assertFalse(ok_v1)
        self.assertEqual(cod_v1, 'SESION_INVALIDA')

        ok_v2, _, _ = validar_token_salida_evento(token_v2, self.evento)
        self.assertTrue(ok_v2)

        # Token expirado es rechazado
        with patch('time.time', return_value=time.time() - 300):
            token_expirado = generar_token_salida_evento(self.evento, control=control)
        ok_exp, cod_exp, _ = validar_token_salida_evento(token_expirado, self.evento)
        self.assertFalse(ok_exp)
        self.assertEqual(cod_exp, 'QR_SALIDA_EXPIRADO')

    def test_06_no_se_generan_salidas_duplicadas(self):
        """6. No se generan salidas duplicadas si el estudiante vuelve a escanear el QR."""
        registrar_asistencia_llegada(self.inscripcion_1, metodo=MetodoAsistencia.QR, operador=self.docente)
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.estudiante_1)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})

        r1 = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r1.json()['exito'])
        hora_primera = Asistencia.objects.get(inscripcion=self.inscripcion_1).hora_salida

        r2 = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(r2.json()['exito'])
        self.assertEqual(r2.json()['codigo'], 'SALIDA_YA_REGISTRADA')
        self.assertEqual(Asistencia.objects.filter(inscripcion=self.inscripcion_1).count(), 1)
        self.assertEqual(Asistencia.objects.get(inscripcion=self.inscripcion_1).hora_salida, hora_primera)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class CalificacionObligatoriaYRecuperacionTests(SistemaCalificacionEstrellasBaseTestCase):
    """Sección B (Casos 7 a 27): Elegibilidad, validaciones, unicidad, obligatoriedad y recuperación."""

    def test_07_estudiante_elegible_puede_calificar_sin_esperar_cierre_global_evento(self):
        """7. Un estudiante con inscripción, entrada y salida puede calificar aunque el evento siga PUBLICADO."""
        self.assertEqual(self.evento.estado, EstadoEvento.PUBLICADO)
        self._registrar_entrada_y_salida(self.inscripcion_1)

        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        resp = self.client.post(url, {'puntuacion': '5'}, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '¡Gracias por tu opinión! Tu calificación ha sido registrada correctamente.')
        calif = CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante_1)
        self.assertEqual(calif.puntuacion, 5)
        self.assertEqual(calif.etiqueta_puntuacion, 'Excelente')

    def test_08_no_puede_calificar_estudiante_sin_inscripcion(self):
        """8. No puede calificar un estudiante sin inscripción en el evento (HTTP 403)."""
        self.client.force_login(self.estudiante_3)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'puntuacion': '4'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_09_no_puede_calificar_estudiante_sin_entrada(self):
        """9. No puede calificar un estudiante inscrito que no tiene entrada registrada (HTTP 403)."""
        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'puntuacion': '4'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_10_no_puede_calificar_estudiante_sin_salida(self):
        """10. No puede calificar un estudiante con entrada pero sin salida registrada (HTTP 403)."""
        registrar_asistencia_llegada(self.inscripcion_1, metodo=MetodoAsistencia.QR, operador=self.docente)

        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_11_no_se_permiten_puntuaciones_inferiores_a_1(self):
        """11. No se permiten puntuaciones inferiores a 1 (ni por vista, ni por servicio, ni en BD)."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        for invalida in ['0', '-1', '-5']:
            resp = self.client.post(url, {'puntuacion': invalida})
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

        # Validación de modelo y restricción CheckConstraint en BD
        calif_invalida = CalificacionEvento(evento=self.evento, estudiante=self.estudiante_1, puntuacion=0)
        with self.assertRaises(ValidationError):
            calif_invalida.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=0)

    def test_12_no_se_permiten_puntuaciones_superiores_a_5(self):
        """12. No se permiten puntuaciones superiores a 5 (ni por vista, ni por servicio, ni en BD)."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        for invalida in ['6', '10', '999']:
            resp = self.client.post(url, {'puntuacion': invalida})
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=6)

    def test_13_no_se_permiten_calificaciones_duplicadas(self):
        """13. Restricción UNIQUE (evento + estudiante) en BD y sin duplicados al reenviar."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=4)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=5)

        self.assertEqual(CalificacionEvento.objects.filter(evento=self.evento, estudiante=self.estudiante_1).count(), 1)

    def test_14_estudiante_puede_actualizar_su_propia_calificacion(self):
        """14. El estudiante puede actualizar su propia calificación y se actualiza el mismo registro."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        # Primera calificación
        self.client.post(url, {'puntuacion': '3'}, follow=True)
        calif_inicial = CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante_1)
        id_inicial = calif_inicial.pk
        self.assertEqual(calif_inicial.puntuacion, 3)

        # Actualización
        resp_upd = self.client.post(url, {'puntuacion': '5'}, follow=True)
        self.assertEqual(resp_upd.status_code, 200)
        calif_actualizada = CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante_1)
        self.assertEqual(calif_actualizada.pk, id_inicial)
        self.assertEqual(calif_actualizada.puntuacion, 5)
        self.assertEqual(CalificacionEvento.objects.filter(evento=self.evento, estudiante=self.estudiante_1).count(), 1)
        self.assertTrue(Auditoria.objects.filter(usuario=self.estudiante_1, accion='ACTUALIZAR_CALIFICACION_EVENTO').exists())

    def test_15_estudiante_no_puede_modificar_calificacion_de_otro(self):
        """15. Un estudiante no puede modificar la calificación de otro estudiante (anti-IDOR)."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self._registrar_entrada_y_salida(self.inscripcion_2)

        calif_est1 = CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=5)

        # Estudiante 2 intenta enviar parámetros manipulados apuntando a estudiante_1 o id_calificacion
        self.client.force_login(self.estudiante_2)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        self.client.post(url, {
            'puntuacion': '1',
            'estudiante': self.estudiante_1.pk,
            'estudiante_id': self.estudiante_1.pk,
            'id_calificacion': calif_est1.pk,
        })

        calif_est1.refresh_from_db()
        self.assertEqual(calif_est1.puntuacion, 5)  # Intacta
        calif_est2 = CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante_2)
        self.assertEqual(calif_est2.puntuacion, 1)  # Solo afecta al usuario autenticado

    def test_16_calificacion_es_obligatoria(self):
        """16. La calificación es obligatoria: navegar a otras rutas del portal redirige a calificar."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        url_calif = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        for ruta in [reverse('inicio'), reverse('eventos:catalogo'), reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk})]:
            resp = self.client.get(ruta)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, url_calif)

    def test_17_no_existe_opcion_para_omitir_evaluacion(self):
        """17. No existe botón ni enlace para omitir la evaluación en la pantalla obligatoria."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        resp = self.client.get(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))

        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8').lower()
        self.assertNotIn('omitir', html)
        self.assertNotIn('saltar', html)
        self.assertNotIn('volver a mis inscripciones', html)
        self.assertContains(resp, '¡Gracias por participar!')
        self.assertContains(resp, '¿Cómo calificas este evento?')
        self.assertContains(resp, 'Enviar calificación')

    def test_18_no_existe_opcion_para_posponer_evaluacion(self):
        """18. No existe botón ni enlace para posponer la evaluación ('Calificar más tarde', 'Ahora no')."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        resp = self.client.get(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))

        html = resp.content.decode('utf-8').lower()
        self.assertNotIn('calificar más tarde', html)
        self.assertNotIn('calificar mas tarde', html)
        self.assertNotIn('ahora no', html)
        self.assertNotIn('posponer', html)

    def test_19_no_permite_completar_flujo_sin_puntuacion_valida(self):
        """19. No se permite completar el flujo enviando vacío, texto o sin selección explícita."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})

        for payload in [{}, {'puntuacion': ''}, {'puntuacion': 'abc'}, {'puntuacion': '3.5'}]:
            resp = self.client.post(url, payload)
            self.assertEqual(resp.status_code, 400)

        self.assertEqual(CalificacionEvento.objects.count(), 0)
        self.assertEqual(obtener_evaluaciones_pendientes(self.estudiante_1).count(), 1)

    def test_20_si_cierra_navegador_salida_permanece_registrada(self):
        """20. Si el estudiante cierra el navegador sin calificar, la salida permanece guardada."""
        registrar_asistencia_llegada(self.inscripcion_1, metodo=MetodoAsistencia.QR, operador=self.docente)
        control = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_salida = generar_token_salida_evento(self.evento, control=control)

        self.client.force_login(self.estudiante_1)
        url_reg = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        r = self.client.post(url_reg, {'token_salida': token_salida}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r.json()['exito'])

        # Simular cierre total de navegador (nueva sesión limpia sin calificar)
        nuevo_cliente = Client()
        asistencia = Asistencia.objects.get(inscripcion=self.inscripcion_1)
        self.assertIsNotNone(asistencia.hora_salida)
        self.assertEqual(CalificacionEvento.objects.count(), 0)
        self.assertEqual(obtener_evaluaciones_pendientes(self.estudiante_1).count(), 1)
        self.assertIsNotNone(nuevo_cliente)

    def test_21_al_volver_a_ingresar_encuentra_calificacion_pendiente(self):
        """21. Al volver a iniciar sesión, el sistema detecta la evaluación pendiente y redirige a calificar."""
        self._registrar_entrada_y_salida(self.inscripcion_1)

        nuevo_cliente = Client()
        resp_login = nuevo_cliente.post(reverse('usuarios:login'), {
            'username': 'est_calif_1',
            'password': 'Password123*',
        })
        self.assertEqual(resp_login.status_code, 302)
        self.assertEqual(resp_login.url, reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))

        # Además es visible en su historial (Mis Inscripciones) como pendiente
        resp_hist = nuevo_cliente.get(reverse('participantes:mis_inscripciones'))
        self.assertEqual(resp_hist.status_code, 200)
        self.assertContains(resp_hist, 'Pendiente de Calificación')
        self.assertContains(resp_hist, 'Calificar Evento (Obligatorio)')

    def test_22_no_necesita_escanear_nuevamente_qr_de_salida(self):
        """22. El estudiante completa la evaluación pendiente sin escanear de nuevo el QR, aun con sesión cerrada."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        # El docente ya cerró la sesión de salida del evento
        cerrar_sesion_salida_service(self.evento, operador=self.docente)

        self.client.force_login(self.estudiante_1)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        resp = self.client.post(url, {'puntuacion': '4'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante_1).puntuacion, 4)

    def test_23_no_se_genera_segunda_salida_al_recuperar_y_calificar(self):
        """23. Recuperar y completar la evaluación pendiente no genera ni altera el registro de salida."""
        asist_orig = self._registrar_entrada_y_salida(
            self.inscripcion_1,
            hora_entrada=datetime.time(8, 15),
            hora_salida=datetime.time(10, 45),
        )
        self.client.force_login(self.estudiante_1)
        self.client.post(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}), {'puntuacion': '5'})

        asistencias = Asistencia.objects.filter(inscripcion=self.inscripcion_1)
        self.assertEqual(asistencias.count(), 1)
        self.assertEqual(asistencias.first().pk, asist_orig.pk)
        self.assertEqual(asistencias.first().hora_salida, datetime.time(10, 45))

    def test_24_al_registrar_calificacion_evaluacion_pendiente_desaparece(self):
        """24. Al registrar la calificación, desaparece de pendientes y se refleja en historial."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.assertEqual(obtener_evaluaciones_pendientes(self.estudiante_1).count(), 1)

        self.client.force_login(self.estudiante_1)
        self.client.post(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}), {'puntuacion': '5'})

        self.assertEqual(obtener_evaluaciones_pendientes(self.estudiante_1).count(), 0)
        # Puede navegar libremente por el portal nuevamente
        self.assertEqual(self.client.get(reverse('eventos:catalogo')).status_code, 200)
        resp_hist = self.client.get(reverse('participantes:mis_inscripciones'))
        self.assertNotContains(resp_hist, 'Pendiente de Calificación')
        self.assertContains(resp_hist, 'Calificado: 5/5 (Excelente)')

    def test_25_estudiante_que_ya_califico_no_vuelve_a_recibir_solicitud(self):
        """25. Un estudiante que ya calificó no vuelve a ser redirigido a calificar al iniciar sesión."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=4)

        nuevo_cliente = Client()
        resp_login = nuevo_cliente.post(reverse('usuarios:login'), {
            'username': 'est_calif_1',
            'password': 'Password123*',
        })
        self.assertEqual(resp_login.status_code, 302)
        self.assertNotEqual(resp_login.url, reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))

    def test_26_error_al_guardar_calificacion_no_afecta_asistencia(self):
        """26. Un error técnico al guardar la calificación no revierte ni altera la asistencia/salida."""
        asist = self._registrar_entrada_y_salida(
            self.inscripcion_1,
            hora_entrada=datetime.time(8, 0),
            hora_salida=datetime.time(10, 0),
        )
        with patch.object(CalificacionEvento, 'save', side_effect=RuntimeError("Fallo simulado de BD")):
            with self.assertRaises(RuntimeError):
                registrar_o_actualizar_calificacion(self.estudiante_1, self.evento, 5)

        asist.refresh_from_db()
        self.assertEqual(asist.estado, EstadoAsistencia.REGISTRADA)
        self.assertEqual(asist.hora_entrada, datetime.time(8, 0))
        self.assertEqual(asist.hora_salida, datetime.time(10, 0))
        self.assertEqual(CalificacionEvento.objects.count(), 0)
        self.assertEqual(obtener_evaluaciones_pendientes(self.estudiante_1).count(), 1)

    def test_27_no_se_guardan_calificaciones_automaticas_por_defecto(self):
        """27. Registrar salida o cargar la vista no crea ninguna calificación automática por defecto."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self.client.force_login(self.estudiante_1)
        self.client.get(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(CalificacionEvento.objects.count(), 0)

        # Enviar formulario sin selección explícita tampoco guarda nada por defecto
        resp = self.client.post(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}), {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CalificacionEvento.objects.count(), 0)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class RolesYPermisosCalificacionTests(SistemaCalificacionEstrellasBaseTestCase):
    """Sección C (Casos 28 a 31): Control de acceso por rol y privacidad."""

    def test_28_usuario_no_autenticado_no_puede_calificar(self):
        """28. Un usuario no autenticado es redirigido al login y no puede calificar."""
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        resp_get = self.client.get(url)
        self.assertEqual(resp_get.status_code, 302)
        self.assertIn(reverse('usuarios:login'), resp_get.url)

        resp_post = self.client.post(url, {'puntuacion': '5'})
        self.assertEqual(resp_post.status_code, 302)
        self.assertIn(reverse('usuarios:login'), resp_post.url)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_29_docente_no_puede_registrar_calificacion_como_estudiante(self):
        """29. Un docente no puede registrar calificaciones (HTTP 403), ni aunque tenga inscripción y salida."""
        part_doc = Participante.objects.create(
            usuario=self.docente,
            tipo=TipoParticipante.DOCENTE,
            documento=self.docente.documento,
            nombres=self.docente.nombres,
            apellidos=self.docente.apellidos,
            correo=self.docente.email,
        )
        insc_doc = Inscripcion.objects.create(evento=self.evento, participante=part_doc, estado=EstadoInscripcion.ACTIVA)
        self._registrar_entrada_y_salida(insc_doc)

        self.client.force_login(self.docente)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_30_administrador_no_puede_registrar_calificacion_como_estudiante(self):
        """30. Un administrador no puede registrar calificaciones como estudiante (HTTP 403)."""
        part_adm = Participante.objects.create(
            usuario=self.admin,
            tipo=TipoParticipante.ADMINISTRATIVO,
            documento=self.admin.documento,
            nombres=self.admin.nombres,
            apellidos=self.admin.apellidos,
            correo=self.admin.email,
        )
        insc_adm = Inscripcion.objects.create(evento=self.evento, participante=part_adm, estado=EstadoInscripcion.ACTIVA)
        self._registrar_entrada_y_salida(insc_adm)

        self.client.force_login(self.admin)
        url = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_31_estudiante_no_puede_consultar_calificaciones_individuales_de_otros(self):
        """31. Un estudiante ve el promedio general del evento, pero nunca identidades ni calificaciones individuales de otros."""
        self._registrar_entrada_y_salida(self.inscripcion_1)
        self._registrar_entrada_y_salida(self.inscripcion_2)
        CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_1, puntuacion=5)
        CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante_2, puntuacion=3)

        self.client.force_login(self.estudiante_2)
        resp = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(resp.status_code, 200)
        # Ve promedio general (4.0) y su propia calificación (3/5)
        self.assertContains(resp, '4.0')
        self.assertContains(resp, '2 evaluaciones')
        # NO expone identidad ni correo del otro estudiante
        self.assertNotContains(resp, self.estudiante_1.email)
        self.assertNotContains(resp, 'Ana Estrella')
        # Y no tiene acceso al dashboard analítico
        self.assertEqual(self.client.get(reverse('analitica:dashboard')).status_code, 403)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class EstadisticasCalificacionTests(SistemaCalificacionEstrellasBaseTestCase):
    """Sección D (Casos 32 a 36) + visualización para docente y administrador."""

    def _poblar_cinco_calificaciones(self):
        """Crea 5 calificaciones reales: 5★(2), 4★(1), 3★(1), 1★(1), 2★(0). Promedio = (5+5+4+3+1)/5 = 3.6."""
        usuarios_extras = [
            Usuario.objects.create_user(
                username=f'est_stat_{i}',
                email=f'est_stat_{i}@uniminuto.edu.co',
                password='Password123*',
                documento=f'9100000{i}',
                nombres=f'Est{i}',
                apellidos='Stats',
                rol=self.rol_estudiante,
            )
            for i in range(1, 6)
        ]
        puntuaciones = [5, 5, 4, 3, 1]
        for u, punt in zip(usuarios_extras, puntuaciones):
            CalificacionEvento.objects.create(evento=self.evento, estudiante=u, puntuacion=punt)

    def test_32_promedio_se_calcula_correctamente(self):
        """32. El promedio general se calcula dinámicamente con exactitud desde los registros reales."""
        self._poblar_cinco_calificaciones()
        stats = calcular_estadisticas_calificacion(self.evento)
        self.assertTrue(stats['tiene_calificaciones'])
        self.assertEqual(stats['promedio'], 3.6)
        self.assertEqual(stats['promedio_display'], '3.6')

    def test_33_cantidad_de_evaluaciones_es_correcta(self):
        """33. La cantidad total de estudiantes que calificaron es exacta."""
        self._poblar_cinco_calificaciones()
        stats = calcular_estadisticas_calificacion(self.evento)
        self.assertEqual(stats['total_calificaciones'], 5)

    def test_34_distribucion_de_estrellas_es_correcta(self):
        """34. El conteo individual de 1, 2, 3, 4 y 5 estrellas es exacto."""
        self._poblar_cinco_calificaciones()
        stats = calcular_estadisticas_calificacion(self.evento)
        self.assertEqual(stats['conteos'], {1: 1, 2: 0, 3: 1, 4: 1, 5: 2})

    def test_35_porcentajes_de_distribucion_son_correctos(self):
        """35. Los porcentajes de distribución por estrella se calculan exactamente."""
        self._poblar_cinco_calificaciones()
        stats = calcular_estadisticas_calificacion(self.evento)
        self.assertEqual(stats['porcentajes'], {1: 20.0, 2: 0.0, 3: 20.0, 4: 20.0, 5: 40.0})

    def test_36_evento_sin_calificaciones_muestra_estado_vacio(self):
        """36. Un evento sin calificaciones retorna y muestra el estado vacío exacto requerido."""
        stats = calcular_estadisticas_calificacion(self.evento)
        self.assertFalse(stats['tiene_calificaciones'])
        self.assertEqual(stats['total_calificaciones'], 0)
        self.assertEqual(stats['promedio'], 0.0)
        self.assertEqual(stats['mensaje_vacio'], MENSAJE_SIN_CALIFICACIONES)

        self.client.force_login(self.docente)
        resp_det = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(resp_det.status_code, 200)
        self.assertContains(resp_det, 'Este evento todavía no tiene calificaciones registradas')

    def test_37_docente_y_admin_consultan_estadisticas_en_detalle_y_dashboard(self):
        """37. Docente organizador y Administrador visualizan promedio y distribución en detalle y dashboard."""
        self._poblar_cinco_calificaciones()

        for user in [self.docente, self.admin]:
            self.client.force_login(user)

            resp_det = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk}))
            self.assertEqual(resp_det.status_code, 200)
            self.assertContains(resp_det, '3.6')
            self.assertContains(resp_det, '5 evaluaciones')
            self.assertContains(resp_det, 'Excelente')
            self.assertContains(resp_det, '40.0%')

            resp_dash = self.client.get(reverse('analitica:dashboard'))
            self.assertEqual(resp_dash.status_code, 200)
            self.assertContains(resp_dash, '3.6')
            self.assertContains(resp_dash, 'Satisfacción y Distribución de Calificaciones')
