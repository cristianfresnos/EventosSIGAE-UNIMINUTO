"""
Pruebas unitarias y de integración para Permisos Compartidos entre Docentes Asociados,
ControlEntradaEvento, exclusión mutua Entrada/Salida, restricción de reportes PDF,
trazabilidad en auditoría, compatibilidad histórica e inscripción única con NRC opcional.
Proyecto: EventosSIGAE-UNIMINUTO
"""

import datetime
import time
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, RequestFactory, override_settings
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
    registrar_asistencia_salida,
    inicializar_controles_sesiones_evento,
    iniciar_sesion_entrada_service,
    cerrar_sesion_entrada_service,
    iniciar_sesion_salida_service,
    cerrar_sesion_salida_service,
    es_entrada_habilitada,
    es_salida_habilitada,
    obtener_estado_sesiones_evento,
)
from eventos.admin import EventoAdmin
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
    puede_editar_evento,
    puede_cancelar_evento,
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


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class CorreccionesAuditoriaPredespliegueTests(DocentesAsociadosBaseTestCase):
    """Pruebas específicas para las 4 correcciones de auditoría predespliegue."""

    def test_12_correccion1_crear_evento_y_admin_inicializan_entrada_y_salida_cerradas(self):
        """
        Corrección 1: crear_evento y EventoAdmin.save_model inicializan de forma idempotente y
        transaccional ControlEntradaEvento(False) y ControlSalidaEvento(False). Impide salida
        antes de activación formal y conserva compatibilidad histórica para eventos sin control.
        """
        # A) Creación mediante vista eventos:crear
        self.client.force_login(self.coordinador)
        resp_crear = self.client.post(reverse('eventos:crear'), {
            'nombre': 'Evento Nuevo Doble Control Cerrado',
            'descripcion': 'Debe nacer con entrada y salida formalmente inactivas.',
            'fecha': timezone.localdate().isoformat(),
            'hora_inicio': '08:00',
            'hora_fin': '12:00',
            'lugar': 'Auditorio Central',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'modalidad_inscripcion': ModalidadInscripcion.ABIERTA,
            'cupo': 40,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        })
        self.assertEqual(resp_crear.status_code, 302)

        ev_vista = Evento.objects.get(nombre='Evento Nuevo Doble Control Cerrado')
        ctrl_ent = ControlEntradaEvento.objects.filter(evento=ev_vista).first()
        ctrl_sal = ControlSalidaEvento.objects.filter(evento=ev_vista).first()
        self.assertIsNotNone(ctrl_ent)
        self.assertIsNotNone(ctrl_sal)
        self.assertFalse(ctrl_ent.entradas_habilitadas)
        self.assertFalse(ctrl_sal.salidas_habilitadas)
        self.assertFalse(es_entrada_habilitada(ev_vista))
        self.assertFalse(es_salida_habilitada(ev_vista))
        estado = obtener_estado_sesiones_evento(ev_vista)
        self.assertEqual(estado['sesion_activa_tipo'], 'NINGUNA')
        self.assertFalse(estado['entradas_permitidas'])
        self.assertFalse(estado['salidas_permitidas'])

        # Idempotencia de inicializar_controles_sesiones_evento sin duplicados
        c_ent_2, c_sal_2 = inicializar_controles_sesiones_evento(ev_vista)
        self.assertEqual(c_ent_2.pk, ctrl_ent.pk)
        self.assertEqual(c_sal_2.pk, ctrl_sal.pk)
        self.assertEqual(ControlEntradaEvento.objects.filter(evento=ev_vista).count(), 1)
        self.assertEqual(ControlSalidaEvento.objects.filter(evento=ev_vista).count(), 1)

        # Inscripción + llegada activada -> salida bloqueada mientras entrada está activa y tras cerrarla
        insc = Inscripcion.objects.create(evento=ev_vista, participante=self.part_est, estado=EstadoInscripcion.ACTIVA)
        iniciar_sesion_entrada_service(ev_vista, operador=self.coordinador)
        res_in = registrar_asistencia_llegada(insc, metodo=MetodoAsistencia.QR, operador=self.coordinador)
        self.assertTrue(res_in['exito'])
        res_in['asistencia'].hora_entrada = datetime.time(8, 30)
        res_in['asistencia'].save(update_fields=['hora_entrada'])

        # Mientras entrada está activa no permite registrar salida ni iniciar sesión de salida
        res_out_con_entrada = registrar_asistencia_salida(insc, operador=self.coordinador, hora_salida_custom=datetime.time(10, 0))
        self.assertFalse(res_out_con_entrada['exito'])
        self.assertEqual(res_out_con_entrada['codigo'], 'SALIDAS_DESHABILITADAS')
        with self.assertRaises(ValidationError):
            iniciar_sesion_salida_service(ev_vista, operador=self.coordinador)

        # Tras cerrar entrada pero SIN activar salida, la salida sigue bloqueada
        cerrar_sesion_entrada_service(ev_vista, operador=self.coordinador)
        res_out_sin_activar = registrar_asistencia_salida(insc, operador=self.coordinador, hora_salida_custom=datetime.time(10, 0))
        self.assertFalse(res_out_sin_activar['exito'])
        self.assertEqual(res_out_sin_activar['codigo'], 'SALIDAS_DESHABILITADAS')

        # Al activar formalmente salida, ahora sí permite salida y bloquea reabrir entrada
        iniciar_sesion_salida_service(ev_vista, operador=self.coordinador)
        with self.assertRaises(ValidationError):
            iniciar_sesion_entrada_service(ev_vista, operador=self.coordinador)
        res_out_ok = registrar_asistencia_salida(insc, operador=self.coordinador, hora_salida_custom=datetime.time(10, 0))
        self.assertTrue(res_out_ok['exito'])

        # B) Creación mediante Django Admin (EventoAdmin.save_model)
        rf = RequestFactory()
        req = rf.post('/admin/eventos/evento/add/')
        req.user = self.admin
        ev_admin_obj = Evento(
            nombre='Evento Nuevo Desde Admin',
            descripcion='Creado vía EventoAdmin.save_model.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(16, 0),
            lugar='Sala Admin',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.admin,
            estado=EstadoEvento.PUBLICADO,
        )
        evento_admin = EventoAdmin(Evento, AdminSite())
        evento_admin.save_model(req, ev_admin_obj, form=None, change=False)

        ctrl_ent_adm = ControlEntradaEvento.objects.filter(evento=ev_admin_obj).first()
        ctrl_sal_adm = ControlSalidaEvento.objects.filter(evento=ev_admin_obj).first()
        self.assertIsNotNone(ctrl_ent_adm)
        self.assertIsNotNone(ctrl_sal_adm)
        self.assertFalse(ctrl_ent_adm.entradas_habilitadas)
        self.assertFalse(ctrl_sal_adm.salidas_habilitadas)

        # C) Compatibilidad histórica: evento previo sin controles mantiene entradas y salidas operativas
        ev_hist = Evento.objects.create(
            nombre='Evento Histórico Sin Controles',
            descripcion='Simula evento anterior al despliegue.',
            fecha=datetime.date(2026, 9, 15),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(11, 0),
            lugar='Bloque A',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.monica,
            estado=EstadoEvento.PUBLICADO,
        )
        # Editar evento histórico vía EventoAdmin(change=True) NO crea controles retroactivos
        evento_admin.save_model(req, ev_hist, form=None, change=True)
        self.assertFalse(ControlEntradaEvento.objects.filter(evento=ev_hist).exists())
        self.assertFalse(ControlSalidaEvento.objects.filter(evento=ev_hist).exists())
        self.assertTrue(es_entrada_habilitada(ev_hist))
        self.assertTrue(es_salida_habilitada(ev_hist))

        insc_hist = Inscripcion.objects.create(evento=ev_hist, participante=self.part_est, estado=EstadoInscripcion.ACTIVA)
        r_hist_in = registrar_asistencia_llegada(insc_hist, operador=self.monica)
        self.assertTrue(r_hist_in['exito'])
        r_hist_in['asistencia'].hora_entrada = datetime.time(9, 5)
        r_hist_in['asistencia'].save(update_fields=['hora_entrada'])
        r_hist_out = registrar_asistencia_salida(insc_hist, operador=self.monica, hora_salida_custom=datetime.time(10, 45))
        self.assertTrue(r_hist_out['exito'])

    def test_13_correccion2_separacion_permisos_estructurales_vs_operativos(self):
        """
        Corrección 2: valida la matriz completa de permisos estructurales (editar/cancelar) vs.
        operativos para 2 docentes asociados, 1 docente no asociado, organizador, coordinador,
        administrador y estudiante.
        """
        # Evento 1: organizado por self.coordinador; Mónica y Alexander son docentes asociados NO organizadores
        # Evento 2: organizado por Mónica (docente organizadora), con Alexander asociado
        evento_org_monica = Evento.objects.create(
            nombre='Taller Organizado por Mónica',
            descripcion='Mónica es organizadora, Alexander es docente asociado.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(16, 0),
            lugar='Lab 204',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.monica,
            estado=EstadoEvento.PUBLICADO,
        )
        inicializar_controles_sesiones_evento(evento_org_monica)
        asignar_docente_evento_service(evento_org_monica, self.alexander, self.coordinador)

        # 1. Validación directa en capa de servicios de permisos (eventos/permissions.py)
        # Sobre self.evento (organizador = coordinador):
        self.assertTrue(puede_editar_evento(self.admin, self.evento))
        self.assertTrue(puede_cancelar_evento(self.admin, self.evento))
        self.assertTrue(puede_editar_evento(self.coordinador, self.evento))
        self.assertTrue(puede_cancelar_evento(self.coordinador, self.evento))
        # Dos docentes asociados NO organizadores: sí operan, NO editan ni cancelan
        for docente_asoc in [self.monica, self.alexander]:
            self.assertTrue(puede_gestionar_evento(docente_asoc, self.evento))
            self.assertFalse(puede_editar_evento(docente_asoc, self.evento))
            self.assertFalse(puede_cancelar_evento(docente_asoc, self.evento))
        # Docente no asociado y estudiante: nada permitido
        for no_auth in [self.docente_ajeno, self.estudiante]:
            self.assertFalse(puede_gestionar_evento(no_auth, self.evento))
            self.assertFalse(puede_editar_evento(no_auth, self.evento))
            self.assertFalse(puede_cancelar_evento(no_auth, self.evento))

        # Sobre evento_org_monica (organizador = Mónica):
        self.assertTrue(puede_editar_evento(self.monica, evento_org_monica))
        self.assertTrue(puede_cancelar_evento(self.monica, evento_org_monica))
        self.assertTrue(puede_editar_evento(self.coordinador, evento_org_monica))
        self.assertTrue(puede_editar_evento(self.admin, evento_org_monica))
        self.assertTrue(puede_gestionar_evento(self.alexander, evento_org_monica))
        self.assertFalse(puede_editar_evento(self.alexander, evento_org_monica))
        self.assertFalse(puede_cancelar_evento(self.alexander, evento_org_monica))

        # 2. Validación estricta en backend (HTTP 403 en GET y POST) y UI para docentes asociados no organizadores
        url_edit_1 = reverse('eventos:editar', kwargs={'id_evento': self.evento.pk})
        url_canc_1 = reverse('eventos:cancelar', kwargs={'id_evento': self.evento.pk})

        for docente_asoc in [self.monica, self.alexander]:
            self.client.force_login(docente_asoc)
            # Backend bloquea editar y cancelar con 403 (GET y POST)
            self.assertEqual(self.client.get(url_edit_1).status_code, 403)
            self.assertEqual(self.client.post(url_edit_1, {'nombre': 'Intento No Autorizado'}).status_code, 403)
            self.assertEqual(self.client.get(url_canc_1).status_code, 403)
            self.assertEqual(self.client.post(url_canc_1, {'motivo_cancelacion': 'No autorizado'}).status_code, 403)

            # UI oculta botones Editar y Cancelar pero conserva controles operativos
            resp_det = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento.pk}))
            self.assertEqual(resp_det.status_code, 200)
            self.assertNotContains(resp_det, url_edit_1)
            self.assertNotContains(resp_det, url_canc_1)
            self.assertContains(resp_det, reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}))

            resp_mis = self.client.get(reverse('eventos:mis_eventos'))
            self.assertEqual(resp_mis.status_code, 200)
            self.assertNotContains(resp_mis, url_edit_1)
            self.assertNotContains(resp_mis, url_canc_1)

        # Docente NO asociado y Estudiante reciben 403 en backend
        for usuario_bloqueado in [self.docente_ajeno, self.estudiante]:
            self.client.force_login(usuario_bloqueado)
            self.assertEqual(self.client.get(url_edit_1).status_code, 403)
            self.assertEqual(self.client.get(url_canc_1).status_code, 403)

        # 3. Administrador, Coordinador y Organizador SÍ acceden a editar y cancelar
        url_edit_2 = reverse('eventos:editar', kwargs={'id_evento': evento_org_monica.pk})
        url_canc_2 = reverse('eventos:cancelar', kwargs={'id_evento': evento_org_monica.pk})

        for autorizado in [self.admin, self.coordinador, self.monica]:
            self.client.force_login(autorizado)
            self.assertEqual(self.client.get(url_edit_2).status_code, 200)
            self.assertEqual(self.client.get(url_canc_2).status_code, 200)
            resp_det_auth = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': evento_org_monica.pk}))
            self.assertContains(resp_det_auth, url_edit_2)
            self.assertContains(resp_det_auth, url_canc_2)

        # Organizador (Mónica) cancela exitosamente su propio evento
        self.client.force_login(self.monica)
        resp_canc_ok = self.client.post(url_canc_2, {'motivo_cancelacion': 'Reprogramación académica institucional'})
        self.assertEqual(resp_canc_ok.status_code, 302)
        evento_org_monica.refresh_from_db()
        self.assertEqual(evento_org_monica.estado, EstadoEvento.CANCELADO)

    def test_14_correccion3_auditoria_registro_afectado_nunca_supera_100_caracteres(self):
        """
        Corrección 3: garantiza que Auditoria.registro_afectado (y accion/modulo) nunca superen
        100 caracteres en escritura directa, reportes PDF con nombres largos y flujos de asistencia.
        """
        # 1. Protección centralizada en Auditoria.save()
        log_largo = Auditoria.objects.create(
            usuario=self.admin,
            accion='ACCION_EXTREMADAMENTE_LARGA_' + ('X' * 120),
            modulo='MODULO_EXTREMADAMENTE_LARGO_' + ('Y' * 120),
            registro_afectado='Evento con descripción desbordada ' + ('Z' * 200),
            ip='127.0.0.1',
        )
        log_largo.refresh_from_db()
        self.assertEqual(len(log_largo.registro_afectado), 100)
        self.assertEqual(len(log_largo.accion), 100)
        self.assertEqual(len(log_largo.modulo), 100)

        # 2. Flujo de reportes PDF con evento de nombre de 190 caracteres
        nombre_190 = 'Congreso Internacional de Ingeniería, Ciencia de Datos y Transformación Digital Universitaria UNIMINUTO ' + ('A' * 86)
        self.assertEqual(len(nombre_190), 190)
        ev_largo = Evento.objects.create(
            nombre=nombre_190,
            descripcion='Prueba de truncamiento de auditoría en PDF.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.coordinador,
            estado=EstadoEvento.PUBLICADO,
        )
        asignar_docente_evento_service(ev_largo, self.monica, self.coordinador)

        Auditoria.objects.all().delete()
        self.client.force_login(self.monica)
        resp_plan = self.client.get(reverse('reportes:planilla_asistencia_pdf', kwargs={'id_evento': ev_largo.pk}))
        resp_rep = self.client.get(reverse('reportes:reporte_consolidado_pdf', kwargs={'id_evento': ev_largo.pk}))
        self.assertEqual(resp_plan.status_code, 200)
        self.assertEqual(resp_rep.status_code, 200)

        logs_rep = list(Auditoria.objects.filter(modulo='REPORTES'))
        self.assertEqual(len(logs_rep), 2)
        for lg in logs_rep:
            self.assertLessEqual(len(lg.registro_afectado), 100)

    def test_15_correccion4_integridad_transaccional_y_orden_bloqueo_determinista(self):
        """
        Corrección 4: valida que registrar_asistencia_llegada y registrar_asistencia_salida
        verifiquen el estado de sesiones dentro de transaction.atomic() usando select_for_update()
        en orden determinista (Evento -> ControlEntradaEvento -> ControlSalidaEvento -> Inscripcion),
        evitando carreras entre cierre de sesión y registro de asistencia.
        """
        from django.db.models.query import QuerySet

        # Preparar evento nuevo con ambos controles cerrados
        ev_tx = Evento.objects.create(
            nombre='Evento Prueba Transaccional',
            descripcion='Validación de orden determinista de bloqueos.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sala 402',
            modalidad=ModalidadEvento.PRESENCIAL,
            categoria=self.categoria,
            organizador=self.coordinador,
            estado=EstadoEvento.PUBLICADO,
        )
        inicializar_controles_sesiones_evento(ev_tx)
        insc_tx = Inscripcion.objects.create(evento=ev_tx, participante=self.part_est, estado=EstadoInscripcion.ACTIVA)

        # 1. Activar entrada y registrar orden real de modelos bloqueados con select_for_update()
        iniciar_sesion_entrada_service(ev_tx, operador=self.monica)
        modelos_bloqueados_llegada = []
        original_sfu = QuerySet.select_for_update

        def tracked_sfu(qs_self, *args, **kwargs):
            modelos_bloqueados_llegada.append(qs_self.model.__name__)
            return original_sfu(qs_self, *args, **kwargs)

        with patch.object(QuerySet, 'select_for_update', new=tracked_sfu):
            res_in = registrar_asistencia_llegada(insc_tx, metodo=MetodoAsistencia.QR, operador=self.alexander)

        self.assertTrue(res_in['exito'])
        self.assertEqual(
            modelos_bloqueados_llegada,
            ['Evento', 'ControlEntradaEvento', 'ControlSalidaEvento', 'Inscripcion'],
        )

        # 2. Simular carrera: docente Mónica cierra sesión de entrada mientras otro docente intenta registrar entrada
        cerrar_sesion_entrada_service(ev_tx, operador=self.monica)
        est2 = Usuario.objects.create_user(
            username='est_race',
            email='est_race@uniminuto.edu.co',
            password='Password123*',
            documento='80000199',
            nombres='Laura',
            apellidos='Carrera',
            rol=self.rol_estudiante,
        )
        part2 = Participante.objects.create(
            usuario=est2,
            tipo=TipoParticipante.ESTUDIANTE,
            documento=est2.documento,
            nombres=est2.nombres,
            apellidos=est2.apellidos,
            correo=est2.email,
        )
        insc_tx_2 = Inscripcion.objects.create(evento=ev_tx, participante=part2, estado=EstadoInscripcion.ACTIVA)
        res_in_cerrada = registrar_asistencia_llegada(insc_tx_2, metodo=MetodoAsistencia.QR, operador=self.alexander)
        self.assertFalse(res_in_cerrada['exito'])
        self.assertEqual(res_in_cerrada['codigo'], 'ENTRADAS_DESHABILITADAS')
        self.assertFalse(Asistencia.objects.filter(inscripcion=insc_tx_2).exists())

        # 3. Activar salida y verificar orden determinista idéntico en registrar_asistencia_salida
        res_in['asistencia'].hora_entrada = datetime.time(8, 15)
        res_in['asistencia'].save(update_fields=['hora_entrada'])
        iniciar_sesion_salida_service(ev_tx, operador=self.alexander)

        modelos_bloqueados_salida = []

        def tracked_sfu_salida(qs_self, *args, **kwargs):
            modelos_bloqueados_salida.append(qs_self.model.__name__)
            return original_sfu(qs_self, *args, **kwargs)

        with patch.object(QuerySet, 'select_for_update', new=tracked_sfu_salida):
            res_out = registrar_asistencia_salida(
                insc_tx,
                metodo=MetodoAsistencia.QR,
                operador=self.monica,
                hora_salida_custom=datetime.time(10, 30),
            )

        self.assertTrue(res_out['exito'])
        self.assertEqual(
            modelos_bloqueados_salida,
            ['Evento', 'ControlEntradaEvento', 'ControlSalidaEvento', 'Inscripcion'],
        )

        # 4. Tras cerrar salida, intento de salida (incluso forzar_actualizacion=True) se rechaza dentro de transacción
        cerrar_sesion_salida_service(ev_tx, operador=self.carlos)
        res_out_cerrada = registrar_asistencia_salida(
            insc_tx,
            metodo=MetodoAsistencia.QR,
            operador=self.monica,
            forzar_actualizacion=True,
            hora_salida_custom=datetime.time(11, 0),
        )
        self.assertFalse(res_out_cerrada['exito'])
        self.assertEqual(res_out_cerrada['codigo'], 'SALIDAS_DESHABILITADAS')
