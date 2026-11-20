"""
Pruebas unitarias y de integración para Permisos Compartidos entre Docentes Asociados,
ControlEntradaEvento, exclusión mutua Entrada/Salida, restricción de reportes PDF,
trazabilidad en auditoría, compatibilidad histórica e inscripción única con NRC opcional.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
import time
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from auditoria.models import Auditoria
from asistencia.models import (
    Asistencia,
    EstadoAsistencia,
    MetodoAsistencia,
    ControlEntradaEvento,
    ControlSalidaEvento,
)
from asistencia.services import (
    generar_token_qr,
    generar_token_salida_evento,
    validar_token_salida_evento,
    registrar_asistencia_llegada,
    iniciar_sesion_entrada_service,
    cerrar_sesion_entrada_service,
    iniciar_sesion_salida_service,
    cerrar_sesion_salida_service,
    es_entrada_habilitada,
)
from eventos.models import (
    CategoriaEvento,
    Evento,
    ModalidadEvento,
    ModalidadInscripcion,
    EstadoEvento,
    DocenteEvento,
    CalificacionEvento,
)
from eventos.permissions import (
    puede_gestionar_evento,
    puede_asignar_docentes,
    obtener_eventos_gestionables,
    asignar_docente_evento_service,
    remover_docente_evento_service,
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
class DocentesAsociadosBaseTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_coord = Rol.objects.create(nombre='Coordinador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.admin = Usuario.objects.create_user(
            username='admin_comp',
            email='admin_comp@uniminuto.edu.co',
            password='Password123*',
            documento='80000001',
            nombres='Admin',
            apellidos='General',
            rol=self.rol_admin,
            is_staff=True,
        )
        self.coordinador = Usuario.objects.create_user(
            username='coord_comp',
            email='coord_comp@uniminuto.edu.co',
            password='Password123*',
            documento='80000002',
            nombres='Paula',
            apellidos='Coordinadora',
            rol=self.rol_coord,
        )
        self.monica = Usuario.objects.create_user(
            username='doc_monica',
            email='monica@uniminuto.edu.co',
            password='Password123*',
            documento='80000010',
            nombres='Mónica',
            apellidos='Profesora',
            rol=self.rol_docente,
        )
        self.alexander = Usuario.objects.create_user(
            username='doc_alexander',
            email='alexander@uniminuto.edu.co',
            password='Password123*',
            documento='80000011',
            nombres='Alexander',
            apellidos='Profesor',
            rol=self.rol_docente,
        )
        self.carlos = Usuario.objects.create_user(
            username='doc_carlos',
            email='carlos@uniminuto.edu.co',
            password='Password123*',
            documento='80000012',
            nombres='Carlos',
            apellidos='Profesor',
            rol=self.rol_docente,
        )
        self.docente_ajeno = Usuario.objects.create_user(
            username='doc_ajeno',
            email='ajeno@uniminuto.edu.co',
            password='Password123*',
            documento='80000019',
            nombres='Diego',
            apellidos='NoAsociado',
            rol=self.rol_docente,
        )
        self.estudiante = Usuario.objects.create_user(
            username='est_comp',
            email='est_comp@uniminuto.edu.co',
            password='Password123*',
            documento='80000050',
            nombres='Sofía',
            apellidos='Estudiante',
            rol=self.rol_estudiante,
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Congreso Académico')

        # Evento creado por Coordinador con ControlEntradaEvento inicializado en False (evento nuevo)
        self.evento = Evento.objects.create(
            nombre='Jornada Conjunta de Ingeniería',
            descripcion='Evento compartido por varios cursos y docentes.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio Mayor',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.coordinador,
        )
        ControlEntradaEvento.objects.create(evento=self.evento, entradas_habilitadas=False)

        # Asociar a Mónica, Alexander y Carlos con sus NRC
        asignar_docente_evento_service(self.evento, self.monica, self.coordinador, nrc='45101')
        asignar_docente_evento_service(self.evento, self.alexander, self.admin, nrc='45102')
        asignar_docente_evento_service(self.evento, self.carlos, self.coordinador, nrc='45103')

        self.part_est = Participante.objects.create(
            usuario=self.estudiante,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=self.estudiante.documento,
            nombres=self.estudiante.nombres,
            apellidos=self.estudiante.apellidos,
            correo=self.estudiante.email,
        )
        self.inscripcion = Inscripcion.objects.create(
            evento=self.evento,
            participante=self.part_est,
            estado=EstadoInscripcion.ACTIVA,
            nrc='45101',
        )


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class AsociacionYRestriccionAccesoTests(DocentesAsociadosBaseTestCase):
    """Asociación N:M de docentes, auditoría y restricción de acceso en todos los módulos."""

    def test_01_multiples_docentes_en_un_evento_y_un_docente_en_multiples_eventos(self):
        """Un evento admite múltiples docentes y un docente puede estar asociado a múltiples eventos."""
        evento_2 = Evento.objects.create(
            nombre='Seminario de Redes',
            descripcion='Segundo evento.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Sala 301',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.admin,
            estado=EstadoEvento.PUBLICADO,
        )
        asignar_docente_evento_service(evento_2, self.monica, self.admin, nrc='55201')

        self.assertEqual(DocenteEvento.objects.filter(evento=self.evento, activo=True).count(), 3)
        self.assertEqual(obtener_eventos_gestionables(self.monica).count(), 2)
        self.assertEqual(obtener_eventos_gestionables(self.alexander).count(), 1)
        self.assertEqual(obtener_eventos_gestionables(self.docente_ajeno).count(), 0)

    def test_02_solo_admin_o_coordinador_puede_asignar_o_remover_docentes(self):
        """Solo Administrador y Coordinador pueden asociar o desasociar docentes; Docente y Estudiante reciben 403."""
        self.assertTrue(puede_asignar_docentes(self.admin))
        self.assertTrue(puede_asignar_docentes(self.coordinador))
        self.assertFalse(puede_asignar_docentes(self.monica))
        self.assertFalse(puede_asignar_docentes(self.estudiante))

        url_asig = reverse('eventos:gestionar_docentes', kwargs={'id_evento': self.evento.pk})
        url_rem = reverse('eventos:remover_docente', kwargs={'id_evento': self.evento.pk, 'id_docente': self.carlos.pk})

        for usuario_no_autorizado in [self.monica, self.docente_ajeno, self.estudiante]:
            self.client.force_login(usuario_no_autorizado)
            self.assertEqual(self.client.post(url_asig, {'docente_id': self.docente_ajeno.pk}).status_code, 403)
            self.assertEqual(self.client.post(url_rem).status_code, 403)

        # Coordinador sí puede asociar y desasociar con auditoría
        self.client.force_login(self.coordinador)
        resp = self.client.post(url_asig, {'docente_id': self.docente_ajeno.pk, 'nrc': '45109'})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(puede_gestionar_evento(self.docente_ajeno, self.evento))
        self.assertTrue(Auditoria.objects.filter(usuario=self.coordinador, accion='ASIGNAR_DOCENTE_EVENTO').exists())

        resp_r = self.client.post(
            reverse('eventos:remover_docente', kwargs={'id_evento': self.evento.pk, 'id_docente': self.docente_ajeno.pk})
        )
        self.assertEqual(resp_r.status_code, 302)
        self.assertFalse(puede_gestionar_evento(self.docente_ajeno, self.evento))
        self.assertTrue(Auditoria.objects.filter(usuario=self.coordinador, accion='REMOVER_DOCENTE_EVENTO').exists())

    def test_03_no_permite_asociar_estudiante_como_docente_ni_duplicados_en_bd(self):
        """Solo usuarios con rol Docente pueden ser asociados y existe UniqueConstraint(evento, docente)."""
        with self.assertRaises(ValidationError):
            asignar_docente_evento_service(self.evento, self.estudiante, self.admin)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocenteEvento.objects.create(evento=self.evento, docente=self.monica)

    def test_04_restriccion_estricta_docente_no_asociado_en_todos_los_modulos_y_reportes_pdf(self):
        """Un docente NO asociado recibe HTTP 403 en reportes PDF, asistencia, sesiones QR, analítica, edición e invitaciones."""
        self.client.force_login(self.docente_ajeno)

        rutas_get_403 = [
            reverse('reportes:planilla_asistencia_pdf', kwargs={'id_evento': self.evento.pk}),
            reverse('reportes:reporte_consolidado_pdf', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:proyector_salida', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:estado_sesiones_evento', kwargs={'id_evento': self.evento.pk}),
            reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk}),
            reverse('eventos:editar', kwargs={'id_evento': self.evento.pk}),
            reverse('eventos:cancelar', kwargs={'id_evento': self.evento.pk}),
            reverse('analitica:dashboard') + f'?evento={self.evento.pk}',
            reverse('analitica:exportar_csv') + f'?evento={self.evento.pk}',
            reverse('analitica:exportar_excel') + f'?evento={self.evento.pk}',
        ]
        for ruta in rutas_get_403:
            self.assertEqual(self.client.get(ruta).status_code, 403, f"Se esperaba 403 en GET {ruta}")

        rutas_post_403 = [
            reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:cerrar_sesion_entrada', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:cerrar_sesion_salida', kwargs={'id_evento': self.evento.pk}),
            reverse('asistencia:rotar_nonce_salida', kwargs={'id_evento': self.evento.pk}),
        ]
        for ruta in rutas_post_403:
            self.assertEqual(self.client.post(ruta).status_code, 403, f"Se esperaba 403 en POST {ruta}")

        # Tampoco aparece en su panel de gestión de eventos
        resp_mis = self.client.get(reverse('eventos:mis_eventos'))
        self.assertEqual(resp_mis.status_code, 200)
        self.assertNotContains(resp_mis, self.evento.nombre)

    def test_05_estudiante_no_puede_acceder_a_reportes_pdf_ni_gestion_docente(self):
        """Un estudiante recibe 403 al intentar descargar planillas, reportes o gestionar sesiones."""
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get(reverse('reportes:planilla_asistencia_pdf', kwargs={'id_evento': self.evento.pk})).status_code, 403)
        self.assertEqual(self.client.get(reverse('reportes:reporte_consolidado_pdf', kwargs={'id_evento': self.evento.pk})).status_code, 403)
        self.assertEqual(self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})).status_code, 403)
        self.assertEqual(self.client.post(reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk})).status_code, 403)

    def test_06_todos_los_docentes_asociados_tienen_permisos_compartidos_completos(self):
        """Mónica, Alexander y Carlos acceden por igual a gestión, asistencia, reportes PDF, analítica y calificaciones."""
        # Agregar una calificación real para validar visibilidad de estadísticas RF-30
        Asistencia.objects.create(
            inscripcion=self.inscripcion,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 10),
            hora_salida=datetime.time(11, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        CalificacionEvento.objects.create(evento=self.evento, estudiante=self.estudiante, puntuacion=5)

        for docente in [self.monica, self.alexander, self.carlos]:
            self.client.force_login(docente)

            resp_mis = self.client.get(reverse('eventos:mis_eventos'))
            self.assertEqual(resp_mis.status_code, 200)
            self.assertContains(resp_mis, self.evento.nombre)

            resp_det = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk}))
            self.assertEqual(resp_det.status_code, 200)
            self.assertContains(resp_det, 'Panel de Gestión del Evento')
            self.assertContains(resp_det, '5.0')

            self.assertEqual(self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})).status_code, 200)
            self.assertEqual(self.client.get(reverse('participantes:gestionar_invitaciones', kwargs={'id_evento': self.evento.pk})).status_code, 200)

            resp_plan = self.client.get(reverse('reportes:planilla_asistencia_pdf', kwargs={'id_evento': self.evento.pk}))
            self.assertEqual(resp_plan.status_code, 200)
            self.assertEqual(resp_plan['Content-Type'], 'application/pdf')

            resp_rep = self.client.get(reverse('reportes:reporte_consolidado_pdf', kwargs={'id_evento': self.evento.pk}))
            self.assertEqual(resp_rep.status_code, 200)
            self.assertEqual(resp_rep['Content-Type'], 'application/pdf')

            resp_dash = self.client.get(reverse('analitica:dashboard') + f'?evento={self.evento.pk}')
            self.assertEqual(resp_dash.status_code, 200)
            self.assertContains(resp_dash, self.evento.nombre)

            # RF-28 intacto: ningún docente asociado puede calificar como estudiante
            self.assertEqual(self.client.post(reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk}), {'puntuacion': '5'}).status_code, 403)


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class SesionesCompartidasYConcurrenciaTests(DocentesAsociadosBaseTestCase):
    """Sesión compartida de entrada/salida, exclusión mutua, trazabilidad y compatibilidad histórica."""

    def test_07_evento_nuevo_creado_por_vista_exige_activacion_explicita_de_entrada(self):
        """Un evento nuevo creado por eventos:crear crea ControlEntradaEvento inactivo y bloquea llegadas hasta activarlo."""
        self.client.force_login(self.coordinador)
        self.client.post(reverse('eventos:crear'), {
            'nombre': 'Taller Nuevo con Control Obligatorio',
            'descripcion': 'Debe exigir activación explícita de entrada.',
            'fecha': timezone.localdate().isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '12:00',
            'lugar': 'Sala 101',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'modalidad_inscripcion': ModalidadInscripcion.ABIERTA,
            'cupo': 50,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        })
        ev_nuevo = Evento.objects.get(nombre='Taller Nuevo con Control Obligatorio')
        control = ControlEntradaEvento.objects.filter(evento=ev_nuevo).first()
        self.assertIsNotNone(control)
        self.assertFalse(control.entradas_habilitadas)
        self.assertFalse(es_entrada_habilitada(ev_nuevo))

        insc = Inscripcion.objects.create(evento=ev_nuevo, participante=self.part_est, estado=EstadoInscripcion.ACTIVA)
        res = registrar_asistencia_llegada(insc, metodo=MetodoAsistencia.QR, operador=self.coordinador)
        self.assertFalse(res['exito'])
        self.assertEqual(res['codigo'], 'ENTRADAS_DESHABILITADAS')

    def test_08_flujo_colaborativo_monica_alexander_carlos_con_trazabilidad_auditoria(self):
        """Mónica activa entrada -> Alexander consulta -> Carlos registra llegada -> Alexander cierra entrada y abre salida -> Mónica proyecta -> Carlos cierra salida."""
        Auditoria.objects.all().delete()

        # 1. Sin sesión de entrada activa, Carlos no puede registrar llegada
        token_llegada = generar_token_qr(self.inscripcion)
        self.client.force_login(self.carlos)
        url_ctrl = reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk})
        res_bloqueado = self.client.post(url_ctrl, {'token_qr': token_llegada}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(res_bloqueado.json()['exito'])
        self.assertEqual(res_bloqueado.json()['codigo'], 'ENTRADAS_DESHABILITADAS')

        # 2. Mónica activa la sesión compartida de entrada
        self.client.force_login(self.monica)
        res_ini_ent = self.client.post(
            reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_ini_ent.status_code, 200)
        sesion_ent_id = res_ini_ent.json()['sesion_id']

        # 3. Alexander consulta el estado compartido y ve que Mónica la activó
        self.client.force_login(self.alexander)
        res_est = self.client.get(reverse('asistencia:estado_sesiones_evento', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(res_est.status_code, 200)
        data_est = res_est.json()
        self.assertEqual(data_est['sesion_activa_tipo'], 'ENTRADA')
        self.assertTrue(data_est['entrada']['activa'])
        self.assertEqual(data_est['entrada']['sesion_id'], sesion_ent_id)
        self.assertIn('Mónica', data_est['entrada']['habilitado_por'])

        # 4. Carlos escanea la entrada del estudiante sobre la misma sesión
        self.client.force_login(self.carlos)
        res_in = self.client.post(url_ctrl, {'token_qr': token_llegada}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(res_in.json()['exito'])

        # 5. Mónica intenta escanear el mismo estudiante -> sin duplicidad
        self.client.force_login(self.monica)
        res_dup = self.client.post(url_ctrl, {'token_qr': token_llegada}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(res_dup.json()['exito'])
        self.assertEqual(res_dup.json()['codigo'], 'ASISTENCIA_DUPLICADA')
        self.assertEqual(Asistencia.objects.filter(inscripcion=self.inscripcion).count(), 1)

        # 6. Alexander cierra la sesión de entrada y activa la sesión compartida de salida
        self.client.force_login(self.alexander)
        self.assertEqual(
            self.client.post(
                reverse('asistencia:cerrar_sesion_entrada', kwargs={'id_evento': self.evento.pk}),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            ).status_code,
            200,
        )
        res_ini_sal = self.client.post(
            reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_ini_sal.status_code, 200)
        token_salida = res_ini_sal.json()['token_salida']

        # 7. Mónica consulta el estado de salida y abre el proyector vigente
        self.client.force_login(self.monica)
        res_est2 = self.client.get(reverse('asistencia:estado_sesiones_evento', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(res_est2.json()['sesion_activa_tipo'], 'SALIDA')
        self.assertIn('Alexander', res_est2.json()['salida']['habilitado_por'])
        self.assertEqual(self.client.get(reverse('asistencia:proyector_salida', kwargs={'id_evento': self.evento.pk})).status_code, 200)

        # 8. Estudiante registra salida y recibe obligatoriedad de calificación RF-26 intacta
        self.client.force_login(self.estudiante)
        res_out = self.client.post(
            reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk}),
            {'token_salida': token_salida},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_out.status_code, 200)
        self.assertTrue(res_out.json()['exito'])
        self.assertTrue(res_out.json()['requiere_calificacion'])

        # 9. Carlos cierra la sesión de salida
        self.client.force_login(self.carlos)
        self.assertEqual(
            self.client.post(
                reverse('asistencia:cerrar_sesion_salida', kwargs={'id_evento': self.evento.pk}),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            ).status_code,
            200,
        )

        # 10. Auditoría identifica individualmente al docente responsable de cada operación
        self.assertTrue(Auditoria.objects.filter(usuario=self.monica, accion='INICIAR_SESION_ENTRADA').exists())
        self.assertTrue(Auditoria.objects.filter(usuario=self.carlos, accion='REGISTRAR_ASISTENCIA').exists())
        self.assertTrue(Auditoria.objects.filter(usuario=self.alexander, accion='CERRAR_SESION_ENTRADA').exists())
        self.assertTrue(Auditoria.objects.filter(usuario=self.alexander, accion='INICIAR_SESION_SALIDA').exists())
        self.assertTrue(Auditoria.objects.filter(usuario=self.carlos, accion='CERRAR_SESION_SALIDA').exists())

    def test_09_bloqueo_sesiones_duplicadas_y_exclusion_mutua_entrada_vs_salida(self):
        """Impide duplicar sesión de entrada/salida e impide sesiones incompatibles simultáneas (HTTP 409)."""
        # Mónica inicia sesión de entrada
        self.client.force_login(self.monica)
        r1 = self.client.post(reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r1.status_code, 200)
        sesion_ent_orig = r1.json()['sesion_id']

        # Alexander intenta duplicar sesión de entrada -> 409 y conserva sesion_id original
        self.client.force_login(self.alexander)
        r_dup_ent = self.client.post(reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_dup_ent.status_code, 409)
        self.assertEqual(r_dup_ent.json()['codigo'], 'SESION_ENTRADA_YA_ACTIVA')
        self.assertEqual(ControlEntradaEvento.objects.get(evento=self.evento).sesion_id, sesion_ent_orig)

        # Carlos intenta iniciar salida mientras entrada está activa -> 409 (exclusión mutua)
        self.client.force_login(self.carlos)
        r_inc_sal = self.client.post(reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_inc_sal.status_code, 409)
        self.assertEqual(r_inc_sal.json()['codigo'], 'SESION_ENTRADA_ACTIVA_INCOMPATIBLE')

        # Cerrar entrada e iniciar salida
        cerrar_sesion_entrada_service(self.evento, operador=self.carlos)
        r_sal = self.client.post(reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_sal.status_code, 200)
        sesion_sal_orig = r_sal.json()['sesion_id']
        token_sal_vigente = r_sal.json()['token_salida']

        # Mónica intenta duplicar sesión de salida -> 409 y el QR de Carlos sigue válido
        self.client.force_login(self.monica)
        r_dup_sal = self.client.post(reverse('asistencia:iniciar_sesion_salida', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_dup_sal.status_code, 409)
        self.assertEqual(r_dup_sal.json()['codigo'], 'SESION_SALIDA_YA_ACTIVA')
        self.assertEqual(ControlSalidaEvento.objects.get(evento=self.evento).sesion_id, sesion_sal_orig)
        ok_tok, _, _ = validar_token_salida_evento(token_sal_vigente, self.evento)
        self.assertTrue(ok_tok)

        # Alexander intenta reactivar entrada mientras salida sigue activa -> 409 (exclusión mutua)
        self.client.force_login(self.alexander)
        r_inc_ent = self.client.post(reverse('asistencia:iniciar_sesion_entrada', kwargs={'id_evento': self.evento.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_inc_ent.status_code, 409)
        self.assertEqual(r_inc_ent.json()['codigo'], 'SESION_SALIDA_ACTIVA_INCOMPATIBLE')

    def test_10_compatibilidad_historica_evento_sin_control_entrada_conserva_asistencias(self):
        """Un evento histórico sin ControlEntradaEvento mantiene sus registros intactos y compatibilidad heredada."""
        ev_hist = Evento.objects.create(
            nombre='Evento Histórico Previo',
            descripcion='Creado antes de ControlEntradaEvento.',
            fecha=datetime.date(2026, 10, 1),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(11, 0),
            lugar='Auditorio Viejo',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.monica,
            estado=EstadoEvento.PUBLICADO,
        )
        # Sin ControlEntradaEvento asociado
        self.assertFalse(ControlEntradaEvento.objects.filter(evento=ev_hist).exists())
        self.assertTrue(es_entrada_habilitada(ev_hist))

        insc_hist = Inscripcion.objects.create(evento=ev_hist, participante=self.part_est, estado=EstadoInscripcion.ACTIVA)
        res = registrar_asistencia_llegada(insc_hist, metodo=MetodoAsistencia.QR, operador=self.monica)
        self.assertTrue(res['exito'])

    def test_11_inscripcion_unica_con_nrc_validado_sin_duplicar_inscripciones(self):
        """Un evento con múltiples cursos conserva una sola inscripción por estudiante e identifica su NRC validado."""
        est2 = Usuario.objects.create_user(
            username='est_nrc',
            email='est_nrc@uniminuto.edu.co',
            password='Password123*',
            documento='80000099',
            nombres='Mateo',
            apellidos='Curso',
            rol=self.rol_estudiante,
        )
        self.client.force_login(est2)
        url_insc = reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk})

        # NRC inválido (no asociado al evento) es rechazado
        self.client.post(url_insc, {'nrc': '99999'})
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento, participante__usuario=est2).exists())

        # NRC válido (asociado al docente Alexander) registra inscripción única con NRC
        self.client.post(url_insc, {'nrc': '45102'})
        insc_creada = Inscripcion.objects.get(evento=self.evento, participante__usuario=est2)
        self.assertEqual(insc_creada.nrc, '45102')
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento, participante__usuario=est2).count(), 1)

        # Mónica puede filtrar por NRC en el panel único de control de asistencia
        self.client.force_login(self.monica)
        resp_f = self.client.get(reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}) + '?nrc=45102')
        self.assertEqual(resp_f.status_code, 200)
        self.assertContains(resp_f, 'Mateo')
        self.assertNotContains(resp_f, 'Sofía')
