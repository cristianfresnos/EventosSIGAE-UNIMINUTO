"""
Pruebas automatizadas RF-31: Calificaciones para participantes externos sin cuenta institucional.
Proyecto: EventosSIGAE-UNIMINUTO

Cubre los 14 escenarios obligatorios:
1. Estudiante institucional califica correctamente.
2. Participante externo califica sin iniciar sesión (flujos registrar_salida_participante, salida_evento y escanear_salida).
3. Participante externo sin salida (o sin entrada) no puede calificar.
4. Participante externo con acceso revocado no puede calificar.
5. Participante externo con acceso expirado no puede calificar hasta recuperar un acceso válido.
6. Recuperación de inscripción con evaluación pendiente.
7. Cierre del navegador después de registrar salida + CalificacionPendienteMiddleware sin bucles.
8. Recuperación desde otro navegador y retorno al comprobante tras calificar.
9. Prevención de calificaciones duplicadas (BD, concurrencia/doble envío y recuperación).
10. Actualización de la propia calificación.
11. Bloqueo de calificaciones de otros participantes y rechazo de IDOR por parámetros.
12. Docentes, coordinadores y administradores continúan bloqueados.
13. Estadísticas, analítica y Django Admin integran ambos tipos sin exponer datos sensibles.
14. Preservación de calificaciones históricas y backfill idempotente de la migración 0005.
"""

import datetime
import importlib
from unittest.mock import patch

from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from analitica.services import calcular_metricas_dashboard
from asistencia.models import Asistencia, EstadoAsistencia, MetodoAsistencia
from asistencia.services import (
    inicializar_controles_sesiones_evento,
    iniciar_sesion_entrada_service,
    cerrar_sesion_entrada_service,
    iniciar_sesion_salida_service,
    generar_token_salida_evento,
)
from auditoria.models import Auditoria
from eventos.admin import CalificacionEventoAdmin
from eventos.models import (
    CalificacionEvento,
    CategoriaEvento,
    EstadoEvento,
    Evento,
    ModalidadEvento,
    ModalidadInscripcion,
)
from eventos.services import (
    calcular_estadisticas_calificacion,
    calcular_estadisticas_calificacion_global,
    registrar_o_actualizar_calificacion_externa,
)
from participantes.models import (
    AccesoExternoInscripcion,
    EstadoInscripcion,
    Inscripcion,
    Participante,
    TipoParticipante,
)
from usuarios.models import Rol, Usuario


class CalificacionesExternosRF31Tests(TestCase):
    """Suite integral de validación para RF-31."""

    def setUp(self):
        self.rol_admin, _ = Rol.objects.get_or_create(nombre='Administrador')
        self.rol_coord, _ = Rol.objects.get_or_create(nombre='Coordinador')
        self.rol_docente, _ = Rol.objects.get_or_create(nombre='Docente')
        self.rol_est, _ = Rol.objects.get_or_create(nombre='Estudiante')

        self.admin = Usuario.objects.create_user(
            username='admin_rf31',
            email='admin.rf31@uniminuto.edu.co',
            password='PasswordSeguro2026*',
            nombres='Admin',
            apellidos='SIGAE',
            documento='90000031',
            rol=self.rol_admin,
            is_staff=True,
            is_superuser=True,
            email_verificado=True,
        )
        self.coordinador = Usuario.objects.create_user(
            username='coord_rf31',
            email='coord.rf31@uniminuto.edu.co',
            password='PasswordSeguro2026*',
            nombres='Clara',
            apellidos='Coordinadora',
            documento='90000032',
            rol=self.rol_coord,
            email_verificado=True,
        )
        self.docente = Usuario.objects.create_user(
            username='docente_rf31',
            email='docente.rf31@uniminuto.edu.co',
            password='PasswordSeguro2026*',
            nombres='Carlos',
            apellidos='Docente',
            documento='90000033',
            rol=self.rol_docente,
            email_verificado=True,
        )
        self.estudiante = Usuario.objects.create_user(
            username='estudiante_rf31',
            email='est.rf31@uniminuto.edu.co',
            password='PasswordSeguro2026*',
            nombres='Laura',
            apellidos='Estudiante',
            documento='80000031',
            rol=self.rol_est,
            email_verificado=True,
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Congreso RF-31', activo=True)
        hoy = timezone.localdate()

        self.evento = Evento.objects.create(
            nombre='Congreso Innovación Abierta UNIMINUTO',
            descripcion='Evento abierto a comunidad institucional y externos.',
            fecha=hoy,
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Auditorio Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente,
        )
        inicializar_controles_sesiones_evento(self.evento)

        self.evento_b = Evento.objects.create(
            nombre='Seminario Alterno RF-31',
            descripcion='Segundo evento para pruebas de aislamiento.',
            fecha=hoy,
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sala B',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente,
        )
        inicializar_controles_sesiones_evento(self.evento_b)

        self.url_reg = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento.pk})
        self.url_cons = reverse('participantes:consultar_inscripcion_publica', kwargs={'id_evento': self.evento.pk})
        self.url_portal = reverse('participantes:ver_inscripcion_externa')
        self.url_calificar = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento.pk})
        self.url_calificar_b = reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento_b.pk})
        self.url_escanear_salida = reverse('asistencia:escanear_salida', kwargs={'id_evento': self.evento.pk})
        self.url_reg_salida = reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento.pk})
        self.url_salida_pub = reverse('asistencia:salida_evento_publica', kwargs={'id_evento': self.evento.pk})

        self.datos_ext_1 = {
            'documento': '1055112233',
            'nombres': 'Andrés',
            'apellidos': 'Visitante',
            'correo': 'andres.visitante@externo.org',
            'telefono': '3101112233',
            'institucion': 'Empresa Aliada',
            'acepta_politica_tratamiento': 'True',
        }
        self.datos_ext_2 = {
            'documento': '1055445566',
            'nombres': 'Sofía',
            'apellidos': 'Invitada',
            'correo': 'sofia.invitada@externo.org',
            'telefono': '3104445566',
            'institucion': 'Universidad Vecina',
            'acepta_politica_tratamiento': 'True',
        }

    # --- Helpers ---

    def _inscribir_externo(self, datos=None, client=None):
        c = client or Client()
        payload = datos or self.datos_ext_1
        with patch('participantes.views.enviar_correo_confirmacion_externa', return_value=True):
            resp = c.post(self.url_reg, payload)
        self.assertEqual(resp.status_code, 200)
        insc = Inscripcion.objects.select_related('participante').get(
            evento=self.evento,
            participante__documento=payload['documento'],
        )
        acceso = AccesoExternoInscripcion.objects.get(inscripcion=insc)
        return c, insc, acceso

    def _registrar_entrada_y_salida_qr(self, client_ext, insc):
        iniciar_sesion_entrada_service(self.evento, operador=self.docente)
        r_qr = client_ext.get(reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': insc.pk}))
        self.assertEqual(r_qr.status_code, 200)
        token_in = r_qr.json()['token']

        c_doc = Client()
        c_doc.force_login(self.docente)
        r_in = c_doc.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento.pk}),
            {'accion': 'qr', 'token_qr': token_in},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(r_in.json()['exito'])

        cerrar_sesion_entrada_service(self.evento, operador=self.docente)
        ctrl_sal = iniciar_sesion_salida_service(self.evento, operador=self.docente)
        token_sal = generar_token_salida_evento(self.evento, control=ctrl_sal)

        r_out = client_ext.post(
            self.url_reg_salida,
            {'token_salida': token_sal},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        return r_out, token_sal

    # --- 14 Pruebas Obligatorias ---

    def test_01_estudiante_institucional_califica_correctamente(self):
        """1. Estudiante institucional califica correctamente y asocia estudiante + inscripcion."""
        c_est = Client()
        c_est.force_login(self.estudiante)
        r_ins = c_est.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        self.assertEqual(r_ins.status_code, 302)

        insc_est = Inscripcion.objects.get(evento=self.evento, participante__usuario=self.estudiante)
        Asistencia.objects.create(
            inscripcion=insc_est,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 15),
            hora_salida=datetime.time(11, 30),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )

        resp = c_est.post(self.url_calificar, {'puntuacion': '5'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], f"{self.url_calificar}?confirmada=1")

        calif = CalificacionEvento.objects.get(evento=self.evento, estudiante=self.estudiante)
        self.assertEqual(calif.puntuacion, 5)
        self.assertEqual(calif.inscripcion_id, insc_est.pk)
        self.assertFalse(calif.es_externa)

    def test_02_participante_externo_califica_sin_iniciar_sesion_en_los_tres_flujos_de_salida(self):
        """2. Participante externo califica sin login tras registrar salida QR, con redirección y retorno al comprobante."""
        c_ext, insc, acceso = self._inscribir_externo()
        r_out, token_sal = self._registrar_entrada_y_salida_qr(c_ext, insc)

        # Flujo A: registrar_salida_participante indica requiere_calificacion=True y url_calificacion
        self.assertEqual(r_out.status_code, 200)
        data = r_out.json()
        self.assertTrue(data['exito'])
        self.assertTrue(data['requiere_calificacion'])
        self.assertEqual(data['url_calificacion'], self.url_calificar)

        # Flujo B: escanear_salida redirige directamente a calificar si ya registró salida y no calificó
        r_scan = c_ext.get(self.url_escanear_salida)
        self.assertEqual(r_scan.status_code, 302)
        self.assertEqual(r_scan['Location'], self.url_calificar)

        # Flujo C: salida_evento muestra bloque obligatorio de calificación para el externo
        r_sal_get = c_ext.get(f"{self.url_salida_pub}?token_evento={token_sal}")
        self.assertEqual(r_sal_get.status_code, 200)
        self.assertTrue(r_sal_get.context['mostrar_calificacion_obligatoria'])
        self.assertEqual(r_sal_get.context['url_calificar_evento'], self.url_calificar)

        # GET pantalla de calificación sin login
        r_get = c_ext.get(self.url_calificar)
        self.assertEqual(r_get.status_code, 200)
        self.assertTrue(r_get.context['es_externo'])
        self.assertTrue(r_get.context['es_obligatoria'])
        self.assertEqual(r_get['Referrer-Policy'], 'no-referrer')

        # POST calificación de 4 estrellas
        r_post = c_ext.post(self.url_calificar, {'puntuacion': '4'})
        self.assertEqual(r_post.status_code, 302)
        self.assertEqual(r_post['Location'], f"{self.url_calificar}?confirmada=1")

        calif = CalificacionEvento.objects.get(inscripcion=insc)
        self.assertIsNone(calif.estudiante)
        self.assertEqual(calif.evento_id, self.evento.pk)
        self.assertEqual(calif.puntuacion, 4)
        self.assertTrue(calif.es_externa)

        # Confirmación muestra enlace de retorno al comprobante externo (no a mis_inscripciones)
        r_conf = c_ext.get(f"{self.url_calificar}?confirmada=1")
        self.assertEqual(r_conf.status_code, 200)
        self.assertContains(r_conf, self.url_portal)

        # Al regresar al comprobante ya NO redirige y muestra la calificación registrada
        r_portal = c_ext.get(self.url_portal)
        self.assertEqual(r_portal.status_code, 200)
        self.assertContains(r_portal, '4/5')
        self.assertContains(r_portal, 'Actualizar Calificación')

        # Auditoría persistida sin usuario institucional
        self.assertTrue(
            Auditoria.objects.filter(
                usuario__isnull=True,
                accion='CREAR_CALIFICACION_EVENTO',
                modulo='EVENTOS',
            ).exists()
        )

    def test_03_participante_externo_sin_salida_no_puede_calificar(self):
        """3. Participante externo sin entrada o sin salida confirmada recibe 403 al intentar calificar."""
        c_ext, insc, _ = self._inscribir_externo()

        # Sin entrada ni salida
        self.assertEqual(c_ext.get(self.url_calificar).status_code, 403)
        self.assertEqual(c_ext.post(self.url_calificar, {'puntuacion': '5'}).status_code, 403)

        # Solo entrada registrada (sin hora_salida)
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 30),
            hora_salida=None,
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        self.assertEqual(c_ext.get(self.url_calificar).status_code, 403)
        self.assertEqual(c_ext.post(self.url_calificar, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_04_participante_externo_con_acceso_revocado_no_puede_calificar(self):
        """4. Participante externo con acceso revocado no puede calificar (ni GET ni POST)."""
        c_ext, insc, acceso = self._inscribir_externo()
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 30),
            hora_salida=datetime.time(11, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        acceso.revocar()

        self.assertEqual(c_ext.get(self.url_calificar).status_code, 403)
        self.assertEqual(c_ext.post(self.url_calificar, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_05_participante_externo_con_acceso_expirado_bloqueado_hasta_recuperar(self):
        """5. Acceso expirado bloquea calificación (403) hasta que recupera acceso válido."""
        c_ext, insc, acceso = self._inscribir_externo()
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 30),
            hora_salida=datetime.time(11, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        acceso.fecha_expiracion = timezone.now() - datetime.timedelta(days=1)
        acceso.save(update_fields=['fecha_expiracion'])

        # Bloqueado mientras esté expirado
        self.assertEqual(c_ext.get(self.url_calificar).status_code, 403)
        self.assertEqual(c_ext.post(self.url_calificar, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

        # Recupera inscripción en el evento (renueva vigencia de acceso no revocado)
        r_rec = c_ext.post(self.url_cons, {
            'documento': self.datos_ext_1['documento'],
            'dato_verificacion': self.datos_ext_1['correo'],
        })
        self.assertEqual(r_rec.status_code, 302)
        self.assertEqual(r_rec['Location'], self.url_portal)

        # Al seguir al comprobante, redirige a calificación obligatoria y ahora sí permite calificar
        r_portal = c_ext.get(self.url_portal)
        self.assertEqual(r_portal.status_code, 302)
        self.assertEqual(r_portal['Location'], self.url_calificar)

        r_post = c_ext.post(self.url_calificar, {'puntuacion': '5'})
        self.assertEqual(r_post.status_code, 302)
        self.assertTrue(CalificacionEvento.objects.filter(inscripcion=insc, puntuacion=5).exists())

    def test_06_recuperacion_inscripcion_con_evaluacion_pendiente(self):
        """6. Recuperación por formulario de consulta y por formulario de registro redirige a evaluación pendiente."""
        _, insc, _ = self._inscribir_externo()
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 15),
            hora_salida=datetime.time(10, 45),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )

        # A) Recuperación vía formulario de consulta pública
        c_rec_1 = Client()
        r_cons = c_rec_1.post(self.url_cons, {
            'documento': self.datos_ext_1['documento'],
            'dato_verificacion': self.datos_ext_1['telefono'],
        })
        self.assertEqual(r_cons.status_code, 302)
        self.assertEqual(r_cons['Location'], self.url_portal)
        r_det = c_rec_1.get(self.url_portal)
        self.assertEqual(r_det.status_code, 302)
        self.assertEqual(r_det['Location'], self.url_calificar)

        # B) Recuperación vía formulario de inscripción pública (YA_INSCRITO con pendiente)
        c_rec_2 = Client()
        with patch('participantes.views.enviar_correo_confirmacion_externa', return_value=True):
            r_reg = c_rec_2.post(self.url_reg, self.datos_ext_1)
        self.assertEqual(r_reg.status_code, 302)
        self.assertEqual(r_reg['Location'], self.url_calificar)

    def test_07_cierre_navegador_tras_salida_y_middleware_sin_bucles(self):
        """7. Tras salida, el middleware exige calificación en rutas no exentas y respeta rutas exentas sin bucles."""
        c_ext, insc, _ = self._inscribir_externo()
        r_out, _ = self._registrar_entrada_y_salida_qr(c_ext, insc)
        self.assertTrue(r_out.json()['requiere_calificacion'])

        # Navegación normal mientras la sesión externa sigue activa -> redirige a calificar
        r_cat = c_ext.get(reverse('eventos:catalogo'))
        self.assertEqual(r_cat.status_code, 302)
        self.assertEqual(r_cat['Location'], self.url_calificar)

        # Solicitud AJAX en ruta no exenta -> 403 JSON con CALIFICACION_PENDIENTE_OBLIGATORIA
        r_ajax = c_ext.get(reverse('eventos:catalogo'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r_ajax.status_code, 403)
        self.assertEqual(r_ajax.json()['codigo'], 'CALIFICACION_PENDIENTE_OBLIGATORIA')

        # Ruta de calificación NO entra en bucle (retorna 200)
        self.assertEqual(c_ext.get(self.url_calificar).status_code, 200)

        # Ruta pública de otro evento es exenta (no queda atrapado si escanea QR de otro evento)
        r_reg_b = c_ext.get(reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_b.pk}))
        self.assertEqual(r_reg_b.status_code, 200)

    def test_08_recuperacion_desde_otro_navegador_y_retorno_al_comprobante(self):
        """8. Escenario completo: cierra navegador tras salida, recupera desde otro navegador, califica y vuelve al comprobante."""
        c_nav_1, insc, _ = self._inscribir_externo()
        r_out, _ = self._registrar_entrada_y_salida_qr(c_nav_1, insc)
        self.assertTrue(r_out.json()['exito'])
        self.assertTrue(r_out.json()['requiere_calificacion'])

        # Cierra navegador 1 y abre navegador 2 completamente limpio
        c_nav_2 = Client()
        r_rec = c_nav_2.post(
            self.url_cons,
            {
                'documento': self.datos_ext_1['documento'],
                'dato_verificacion': self.datos_ext_1['correo'],
            },
            follow=True,
        )
        # Sigue: consultar_inscripcion_publica -> ver_inscripcion_externa -> calificar_evento
        self.assertEqual(r_rec.status_code, 200)
        self.assertEqual(r_rec.request['PATH_INFO'], self.url_calificar)
        self.assertTrue(r_rec.context['es_externo'])
        self.assertTrue(r_rec.context['es_obligatoria'])

        # Envía su calificación desde navegador 2
        r_cal = c_nav_2.post(self.url_calificar, {'puntuacion': '5'}, follow=True)
        self.assertEqual(r_cal.status_code, 200)
        self.assertContains(r_cal, self.url_portal)

        # Regresa a su comprobante sin redirección adicional y sin inscripciones duplicadas
        r_comp = c_nav_2.get(self.url_portal)
        self.assertEqual(r_comp.status_code, 200)
        self.assertContains(r_comp, '5/5')
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento).count(), 1)
        self.assertEqual(CalificacionEvento.objects.filter(evento=self.evento).count(), 1)

    def test_09_prevencion_calificaciones_duplicadas(self):
        """9. Restricciones BD y servicio previenen duplicados por inscripción, doble envío o recuperación repetida."""
        c_ext, insc, acceso = self._inscribir_externo()
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 0),
            hora_salida=datetime.time(10, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )

        # Primer envío y segundo envío (doble clic / reenvío)
        r1 = c_ext.post(self.url_calificar, {'puntuacion': '3'})
        r2 = c_ext.post(self.url_calificar, {'puntuacion': '5'})
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(CalificacionEvento.objects.filter(inscripcion=insc).count(), 1)
        self.assertEqual(CalificacionEvento.objects.get(inscripcion=insc).puntuacion, 5)

        # Recuperación desde nuevo navegador NO genera una segunda calificación
        c_otro = Client()
        c_otro.post(self.url_cons, {
            'documento': self.datos_ext_1['documento'],
            'dato_verificacion': self.datos_ext_1['correo'],
        })
        c_otro.post(self.url_calificar, {'puntuacion': '4'})
        self.assertEqual(CalificacionEvento.objects.filter(inscripcion=insc).count(), 1)

        # A nivel BD: insertar una segunda CalificacionEvento para la misma inscripcion dispara IntegrityError
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalificacionEvento.objects.create(
                    evento=self.evento,
                    estudiante=None,
                    inscripcion=insc,
                    puntuacion=2,
                )

        # A nivel BD: CheckConstraint impide fila sin estudiante ni inscripcion
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CalificacionEvento.objects.create(
                    evento=self.evento,
                    estudiante=None,
                    inscripcion=None,
                    puntuacion=4,
                )

        # Coherencia de modelo: inscripcion de otro evento falla clean()
        calif_incoherente = CalificacionEvento(
            evento=self.evento_b,
            estudiante=None,
            inscripcion=insc,
            puntuacion=4,
        )
        with self.assertRaises(ValidationError):
            calif_incoherente.full_clean()

        # Coherencia de servicio: doble envío simultáneo capturado por IntegrityError actualiza sin duplicar
        res_upd = registrar_o_actualizar_calificacion_externa(insc, acceso, self.evento, '5')
        self.assertTrue(res_upd['exito'])
        self.assertTrue(res_upd['actualizada'])
        self.assertEqual(CalificacionEvento.objects.filter(inscripcion=insc).count(), 1)

    def test_10_actualizacion_de_la_propia_calificacion(self):
        """10. El participante externo puede actualizar su propia calificación conservando registro único."""
        c_ext, insc, _ = self._inscribir_externo()
        Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 0),
            hora_salida=datetime.time(10, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )

        c_ext.post(self.url_calificar, {'puntuacion': '2'})
        calif_inicial = CalificacionEvento.objects.get(inscripcion=insc)
        self.assertEqual(calif_inicial.puntuacion, 2)

        r_edit = c_ext.get(self.url_calificar)
        self.assertEqual(r_edit.status_code, 200)
        self.assertFalse(r_edit.context['es_obligatoria'])
        self.assertContains(r_edit, 'Actualizar calificación')

        r_upd = c_ext.post(self.url_calificar, {'puntuacion': '5'})
        self.assertEqual(r_upd.status_code, 302)

        calif_final = CalificacionEvento.objects.get(inscripcion=insc)
        self.assertEqual(calif_final.pk, calif_inicial.pk)
        self.assertEqual(calif_final.puntuacion, 5)

    def test_11_bloqueo_calificaciones_de_otros_participantes_y_anti_idor(self):
        """11. Un externo no puede calificar en nombre de otro ni manipular inscripcion_id/participante_id ni otro evento."""
        c_ext_1, insc_1, _ = self._inscribir_externo(self.datos_ext_1)
        c_ext_2, insc_2, _ = self._inscribir_externo(self.datos_ext_2)

        for insc in (insc_1, insc_2):
            Asistencia.objects.create(
                inscripcion=insc,
                fecha=self.evento.fecha,
                hora_entrada=datetime.time(8, 0),
                hora_salida=datetime.time(10, 0),
                metodo=MetodoAsistencia.QR,
                estado=EstadoAsistencia.REGISTRADA,
            )

        # Externo 2 registra su calificación = 5
        c_ext_2.post(self.url_calificar, {'puntuacion': '5'})

        # Externo 1 intenta suplantar enviando inscripcion_id y participante_id de Externo 2
        c_ext_1.post(self.url_calificar, {
            'puntuacion': '1',
            'inscripcion_id': str(insc_2.pk),
            'participante_id': str(insc_2.participante_id),
        })

        # La calificación de Externo 2 permanece intacta (5); la de Externo 1 es 1
        self.assertEqual(CalificacionEvento.objects.get(inscripcion=insc_2).puntuacion, 5)
        self.assertEqual(CalificacionEvento.objects.get(inscripcion=insc_1).puntuacion, 1)

        # Externo 1 intenta calificar evento_b usando sesión de evento_a -> 403
        self.assertEqual(c_ext_1.get(self.url_calificar_b).status_code, 403)
        self.assertEqual(c_ext_1.post(self.url_calificar_b, {'puntuacion': '4'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.filter(evento=self.evento_b).count(), 0)

        # Visitante completamente anónimo sin sesión externa recibe 302 a login (preserva RF-28)
        c_anon = Client()
        r_anon = c_anon.get(self.url_calificar)
        self.assertEqual(r_anon.status_code, 302)
        self.assertIn(reverse('usuarios:login'), r_anon['Location'])

    def test_12_docentes_coordinadores_y_administradores_continuan_bloqueados(self):
        """12. Docentes, coordinadores y administradores reciben 403 al intentar calificar."""
        for usuario in (self.docente, self.coordinador, self.admin):
            c = Client()
            c.force_login(usuario)
            self.assertEqual(c.get(self.url_calificar).status_code, 403)
            self.assertEqual(c.post(self.url_calificar, {'puntuacion': '5'}).status_code, 403)
        self.assertEqual(CalificacionEvento.objects.count(), 0)

    def test_13_estadisticas_analitica_y_admin_incluyen_institucionales_y_externos(self):
        """13. Promedio, conteo, distribución, porcentajes, analítica y Admin consolidan ambos tipos sin filtrar PII."""
        # Estudiante institucional califica con 5
        c_est = Client()
        c_est.force_login(self.estudiante)
        c_est.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento.pk}))
        insc_est = Inscripcion.objects.get(evento=self.evento, participante__usuario=self.estudiante)
        Asistencia.objects.create(
            inscripcion=insc_est,
            fecha=self.evento.fecha,
            hora_entrada=datetime.time(8, 0),
            hora_salida=datetime.time(10, 0),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )
        c_est.post(self.url_calificar, {'puntuacion': '5'})

        # Externo 1 califica con 3 y Externo 2 califica con 4 -> promedio (5+3+4)/3 = 4.0
        c_e1, insc_e1, _ = self._inscribir_externo(self.datos_ext_1)
        c_e2, insc_e2, _ = self._inscribir_externo(self.datos_ext_2)
        for c_e, insc_e, punt in ((c_e1, insc_e1, '3'), (c_e2, insc_e2, '4')):
            Asistencia.objects.create(
                inscripcion=insc_e,
                fecha=self.evento.fecha,
                hora_entrada=datetime.time(8, 0),
                hora_salida=datetime.time(10, 0),
                metodo=MetodoAsistencia.QR,
                estado=EstadoAsistencia.REGISTRADA,
            )
            c_e.post(self.url_calificar, {'puntuacion': punt})

        # Estadísticas por evento
        stats_ev = calcular_estadisticas_calificacion(self.evento)
        self.assertTrue(stats_ev['tiene_calificaciones'])
        self.assertEqual(stats_ev['total_calificaciones'], 3)
        self.assertEqual(stats_ev['promedio'], 4.0)
        self.assertEqual(stats_ev['conteos'], {1: 0, 2: 0, 3: 1, 4: 1, 5: 1})
        self.assertAlmostEqual(stats_ev['porcentajes'][5], 33.3, places=1)

        # Estadísticas globales y panel de analítica
        stats_glob = calcular_estadisticas_calificacion_global(Evento.objects.filter(pk=self.evento.pk))
        self.assertEqual(stats_glob['total_calificaciones'], 3)
        self.assertEqual(stats_glob['promedio'], 4.0)

        datos_an = calcular_metricas_dashboard(Evento.objects.filter(pk=self.evento.pk))
        self.assertEqual(datos_an['estadisticas_calificacion']['total_calificaciones'], 3)
        self.assertEqual(datos_an['estadisticas_calificacion']['promedio'], 4.0)
        fila_ev = next(r for r in datos_an['tabla_eventos'] if r['evento'].pk == self.evento.pk)
        self.assertEqual(fila_ev['total_calificaciones'], 3)
        self.assertEqual(fila_ev['promedio_calificacion'], 4.0)

        # Django Admin: identifica Institucional vs Externo sin exponer campos de identidad sensible
        admin_inst = CalificacionEventoAdmin(CalificacionEvento, AdminSite())
        calif_inst = CalificacionEvento.objects.get(inscripcion=insc_est)
        calif_ext = CalificacionEvento.objects.get(inscripcion=insc_e1)
        self.assertEqual(admin_inst.tipo_participante_admin(calif_inst), 'Institucional')
        self.assertEqual(admin_inst.tipo_participante_admin(calif_ext), 'Externo')
        self.assertNotIn('estudiante', admin_inst.list_display)
        self.assertNotIn('inscripcion', admin_inst.list_display)
        self.assertIn('estudiante', admin_inst.exclude)
        self.assertIn('inscripcion', admin_inst.exclude)

    def test_14_calificaciones_historicas_intactas_y_backfill_idempotente(self):
        """14. Las calificaciones históricas sin inscripción permanecen intactas y el backfill vincula cuando existe inscripción."""
        # A) Calificación histórica CON inscripción existente del estudiante en self.evento
        part_est, _ = Participante.objects.get_or_create(
            usuario=self.estudiante,
            defaults={
                'tipo': TipoParticipante.ESTUDIANTE,
                'documento': self.estudiante.documento,
                'nombres': self.estudiante.nombres,
                'apellidos': self.estudiante.apellidos,
                'correo': self.estudiante.email,
            },
        )
        insc_hist = Inscripcion.objects.create(
            evento=self.evento,
            participante=part_est,
            estado=EstadoInscripcion.ACTIVA,
        )
        calif_hist_con_insc = CalificacionEvento.objects.create(
            evento=self.evento,
            estudiante=self.estudiante,
            inscripcion=None,
            puntuacion=5,
        )

        # B) Calificación histórica SIN inscripción asociada en evento_b
        calif_hist_sin_insc = CalificacionEvento.objects.create(
            evento=self.evento_b,
            estudiante=self.estudiante,
            inscripcion=None,
            puntuacion=4,
        )

        # Ejecutar el backfill real de la migración 0005 dos veces (idempotencia)
        mig_0005 = importlib.import_module('eventos.migrations.0005_calificacionevento_inscripcion_externos')
        mig_0005.poblar_inscripcion_calificaciones_historicas(apps, None)
        mig_0005.poblar_inscripcion_calificaciones_historicas(apps, None)

        calif_hist_con_insc.refresh_from_db()
        calif_hist_sin_insc.refresh_from_db()

        self.assertEqual(calif_hist_con_insc.inscripcion_id, insc_hist.pk)
        self.assertEqual(calif_hist_con_insc.puntuacion, 5)
        self.assertIsNone(calif_hist_sin_insc.inscripcion_id)
        self.assertEqual(calif_hist_sin_insc.estudiante_id, self.estudiante.pk)
        self.assertEqual(calif_hist_sin_insc.puntuacion, 4)
        self.assertEqual(CalificacionEvento.objects.count(), 2)
