"""
Pruebas funcionales y de seguridad para la consulta y recuperación de inscripciones públicas
en EventosSIGAE-UNIMINUTO (Fases 2 a 7).
"""

import datetime
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from asistencia.models import Asistencia, EstadoAsistencia, MetodoAsistencia
from asistencia.services import (
    decodificar_token_qr,
    inicializar_controles_sesiones_evento,
    iniciar_sesion_entrada_service,
    cerrar_sesion_entrada_service,
    iniciar_sesion_salida_service,
)
from auditoria.models import Auditoria
from eventos.models import (
    CategoriaEvento,
    Evento,
    ModalidadEvento,
    ModalidadInscripcion,
    EstadoEvento,
    CalificacionEvento,
)
from participantes.models import (
    Participante,
    Inscripcion,
    EstadoInscripcion,
    TipoParticipante,
    AccesoExternoInscripcion,
)
from participantes.services import CONSULTA_MAX_INTENTOS
from usuarios.models import Rol, Usuario


FAST_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class RecuperacionInscripcionPublicaTests(TestCase):
    """Valida los 11 escenarios funcionales, seguridad, comprobante y preservación de asistencia y RF-24..RF-30."""

    def setUp(self):
        cache.clear()
        self.rol_doc = Rol.objects.create(nombre='Docente')
        self.rol_est = Rol.objects.create(nombre='Estudiante')

        self.docente = Usuario.objects.create_user(
            username='doc_recup',
            email='doc_recup@uniminuto.edu.co',
            password='Password123*',
            documento='71000001',
            nombres='Carolina',
            apellidos='Docente',
            rol=self.rol_doc,
        )
        self.estudiante = Usuario.objects.create_user(
            username='est_recup',
            email='est_recup@uniminuto.edu.co',
            password='Password123*',
            documento='71000050',
            nombres='Sebastián',
            apellidos='Estudiante',
            rol=self.rol_est,
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Conferencia Pública')
        self.evento_a = Evento.objects.create(
            nombre='Foro Abierto de Innovación Social',
            descripcion='Evento público con registro y recuperación sin cuenta.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Auditorio Principal',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.MIXTA,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente,
        )
        inicializar_controles_sesiones_evento(self.evento_a)

        self.evento_b = Evento.objects.create(
            nombre='Seminario de Emprendimiento Digital',
            descripcion='Segundo evento independiente para validar aislamiento.',
            fecha=timezone.localdate(),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(17, 0),
            lugar='Sala 205',
            modalidad=ModalidadEvento.PRESENCIAL,
            modalidad_inscripcion=ModalidadInscripcion.ABIERTA,
            cupo=40,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente,
        )
        inicializar_controles_sesiones_evento(self.evento_b)

        self.url_reg_a = reverse('participantes:inscripcion_publica', kwargs={'id_evento': self.evento_a.pk})
        self.url_cons_a = reverse('participantes:consultar_inscripcion_publica', kwargs={'id_evento': self.evento_a.pk})
        self.url_cons_b = reverse('participantes:consultar_inscripcion_publica', kwargs={'id_evento': self.evento_b.pk})
        self.url_portal = reverse('participantes:ver_inscripcion_externa')

        self.datos_externo = {
            'documento': '1045678901',
            'nombres': 'María Fernanda',
            'apellidos': 'López Ramírez',
            'correo': 'maria.lopez@externo.org',
            'telefono': '3158901234',
            'institucion': 'Fundación Aliada',
            'acepta_politica_tratamiento': 'True',
        }

    def tearDown(self):
        cache.clear()

    def test_01_inscripcion_publica_muestra_comprobante_completo_y_qr_personal(self):
        """1. Una persona se inscribe en un evento público sin iniciar sesión y recibe comprobante completo con QR."""
        c = Client()
        resp_get = c.get(self.url_reg_a)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, '¿Ya estás inscrito? Consulta tu inscripción')

        resp_post = c.post(self.url_reg_a, self.datos_externo)
        self.assertEqual(resp_post.status_code, 200)
        self.assertEqual(resp_post.context['estado'], 'EXITOSA')
        self.assertEqual(resp_post['Referrer-Policy'], 'no-referrer')

        # Comprobante con todos los elementos exigidos en Fase 5
        self.assertContains(resp_post, 'Foro Abierto de Innovación Social')
        self.assertContains(resp_post, 'Auditorio Principal')
        self.assertContains(resp_post, 'María Fernanda López Ramírez')
        self.assertContains(resp_post, 'Activa')
        self.assertContains(resp_post, 'data:image/png;base64,')
        self.assertContains(resp_post, 'Guardar / Imprimir Comprobante')
        self.assertContains(resp_post, 'Descargar QR (PNG)')
        self.assertContains(resp_post, '¿Cómo recuperar tu inscripción si cierras el navegador?')

        insc = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')
        self.assertEqual(insc.estado, EstadoInscripcion.ACTIVA)

    def test_02_y_03_cerrar_navegador_y_recuperar_por_correo_y_por_telefono(self):
        """2 y 3. Tras cerrar navegador (nuevo Client sin sesión), recupera la inscripción con documento + correo o teléfono."""
        c_inicial = Client()
        c_inicial.post(self.url_reg_a, self.datos_externo)
        insc_orig = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')
        acceso_orig = AccesoExternoInscripcion.objects.get(inscripcion=insc_orig)
        hash_orig = acceso_orig.token_hash

        # Simular cierre de navegador (cliente limpio sin cookies ni sesión)
        c_nuevo = Client()
        # Recuperación mediante documento + correo electrónico (insensible a mayúsculas/espacios)
        resp_rec_correo = c_nuevo.post(self.url_cons_a, {
            'documento': ' 1045678901 ',
            'dato_verificacion': ' MARIA.LOPEZ@EXTERNO.ORG ',
        })
        self.assertEqual(resp_rec_correo.status_code, 302)
        self.assertEqual(resp_rec_correo['Location'], self.url_portal)
        self.assertNotIn('token', resp_rec_correo['Location'])
        self.assertNotIn('1045678901', resp_rec_correo['Location'])

        # Verifica acceso al portal personal con el QR correspondiente
        resp_portal = c_nuevo.get(self.url_portal)
        self.assertEqual(resp_portal.status_code, 200)
        self.assertContains(resp_portal, 'María Fernanda López Ramírez')
        self.assertContains(resp_portal, 'Foro Abierto de Innovación Social')
        self.assertContains(resp_portal, 'data:image/png;base64,')

        # El token_hash original NO fue invalidado ni se creó una inscripción duplicada
        acceso_orig.refresh_from_db()
        self.assertEqual(acceso_orig.token_hash, hash_orig)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_a).count(), 1)

        # Simular otro dispositivo y recuperar usando documento + teléfono (con formato separado por espacios/guiones)
        c_tel = Client()
        resp_rec_tel = c_tel.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': '315-890-1234',
        })
        self.assertEqual(resp_rec_tel.status_code, 302)
        self.assertEqual(resp_rec_tel['Location'], self.url_portal)
        self.assertEqual(c_tel.session.get('acceso_externo_inscripcion_id'), insc_orig.pk)
        self.assertTrue(Auditoria.objects.filter(accion='RECUPERAR_INSCRIPCION_PUBLICA').exists())

    def test_04_datos_incorrectos_rechazados_con_mensaje_generico_y_rate_limit(self):
        """4. No recupera con datos incorrectos, no filtra PII y aplica limitación de intentos (HTTP 429)."""
        Client().post(self.url_reg_a, self.datos_externo)

        c_atacante = Client()
        # Caso A: documento inexistente
        resp_inex = c_atacante.post(self.url_cons_a, {
            'documento': '9999999999',
            'dato_verificacion': 'nadie@ejemplo.com',
        })
        self.assertEqual(resp_inex.status_code, 200)
        self.assertIsNone(c_atacante.session.get('acceso_externo_id'))
        err_inex = resp_inex.context['consulta_error']

        # Caso B: documento real pero correo incorrecto
        resp_mal_correo = c_atacante.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'impostor@otro.org',
        })
        self.assertEqual(resp_mal_correo.status_code, 200)
        self.assertIsNone(c_atacante.session.get('acceso_externo_id'))
        err_mal_correo = resp_mal_correo.context['consulta_error']

        # Mensaje estrictamente idéntico (anti-enumeración) y sin PII
        self.assertEqual(err_inex, err_mal_correo)
        self.assertNotContains(resp_mal_correo, 'María Fernanda')
        self.assertNotContains(resp_mal_correo, 'maria.lopez@externo.org')

        # Caso C: documento real pero teléfono incorrecto
        resp_mal_tel = c_atacante.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': '3000000000',
        })
        self.assertEqual(resp_mal_tel.status_code, 200)
        self.assertIsNone(c_atacante.session.get('acceso_externo_id'))

        # Completar intentos restantes hasta alcanzar el límite (CONSULTA_MAX_INTENTOS=5)
        for _ in range(CONSULTA_MAX_INTENTOS - 3):
            c_atacante.post(self.url_cons_a, {
                'documento': '1045678901',
                'dato_verificacion': 'otro@mal.com',
            })

        # El siguiente intento debe quedar bloqueado con HTTP 429 (incluso con datos válidos)
        resp_429 = c_atacante.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(resp_429.status_code, 429)
        self.assertIsNone(c_atacante.session.get('acceso_externo_id'))
        self.assertTrue(Auditoria.objects.filter(accion='CONSULTA_INSCRIPCION_BLOQUEADA_RATE_LIMIT').exists())

    def test_05_no_puede_consultar_inscripciones_de_otros_eventos(self):
        """5. Una inscripción en Evento A no puede consultarse ni recuperarse desde Evento B."""
        Client().post(self.url_reg_a, self.datos_externo)

        c_b = Client()
        resp_b = c_b.post(self.url_cons_b, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(resp_b.status_code, 200)
        self.assertIn('consulta_error', resp_b.context)
        self.assertIsNone(c_b.session.get('acceso_externo_id'))
        self.assertFalse(Inscripcion.objects.filter(evento=self.evento_b).exists())

    def test_06_y_07_no_duplica_inscripciones_ni_invalida_qr_original(self):
        """6 y 7. Reinscribirse o recuperar no crea duplicados y conserva el QR del registro original."""
        c1 = Client()
        resp1 = c1.post(self.url_reg_a, self.datos_externo)
        token_qr_1 = resp1.context['token_qr']
        payload_1 = decodificar_token_qr(token_qr_1)
        insc_orig = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')
        hash_orig = AccesoExternoInscripcion.objects.get(inscripcion=insc_orig).token_hash

        # Segundo envío del formulario de inscripción desde otro navegador
        c2 = Client()
        resp2 = c2.post(self.url_reg_a, self.datos_externo)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.context['estado'], 'YA_INSCRITO')
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_a).count(), 1)
        self.assertEqual(AccesoExternoInscripcion.objects.get(inscripcion=insc_orig).token_hash, hash_orig)

        # Recuperación mediante formulario dedicado -> mismo QR ligado al mismo registro
        c3 = Client()
        c3.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        resp_portal = c3.get(self.url_portal)
        payload_rec = decodificar_token_qr(resp_portal.context['token_qr'])
        self.assertEqual(payload_rec['ins'], insc_orig.pk)
        self.assertEqual(payload_rec['evt'], self.evento_a.pk)
        self.assertEqual(payload_rec['ins'], payload_1['ins'])

    def test_08_y_09_recuperacion_no_modifica_asistencia_y_flujo_completo_sin_login(self):
        """8 y 9. Flujo sin iniciar sesión: inscripción -> entrada -> cierre navegador -> recuperación -> asistencia intacta -> salida."""
        c1 = Client()
        c1.post(self.url_reg_a, self.datos_externo)
        insc = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')

        # Activar sesión de entrada y registrar llegada con QR
        iniciar_sesion_entrada_service(self.evento_a, operador=self.docente)
        resp_qr_din = c1.get(reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': insc.pk}))
        self.assertEqual(resp_qr_din.status_code, 200)
        token_entrada = resp_qr_din.json()['token']

        c_doc = Client()
        c_doc.force_login(self.docente)
        resp_in = c_doc.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento_a.pk}),
            {'accion': 'qr', 'token_qr': token_entrada},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(resp_in.json()['exito'])

        asist_antes = Asistencia.objects.get(inscripcion=insc)
        asist_antes.hora_entrada = datetime.time(8, 30)
        asist_antes.save(update_fields=['hora_entrada'])

        # El participante cierra el navegador y vuelve horas después a recuperar su inscripción
        c_despues = Client()
        resp_rec = c_despues.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(resp_rec.status_code, 302)

        # Verificar que la asistencia previa NO fue reiniciada ni alterada
        asist_despues = Asistencia.objects.get(inscripcion=insc)
        self.assertEqual(asist_despues.pk, asist_antes.pk)
        self.assertEqual(asist_despues.hora_entrada, datetime.time(8, 30))
        self.assertEqual(asist_despues.estado, EstadoAsistencia.REGISTRADA)
        self.assertIsNone(asist_despues.hora_salida)

        # Docente cierra entrada, abre salida y participante recupera sesión y registra salida por QR colectivo
        cerrar_sesion_entrada_service(self.evento_a, operador=self.docente)
        ctrl_sal = iniciar_sesion_salida_service(self.evento_a, operador=self.docente)
        from asistencia.services import generar_token_salida_evento
        token_salida = generar_token_salida_evento(self.evento_a, control=ctrl_sal)

        resp_out = c_despues.post(
            reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento_a.pk}),
            {'token_salida': token_salida},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp_out.status_code, 200)
        self.assertTrue(resp_out.json()['exito'])

        asist_final = Asistencia.objects.get(inscripcion=insc)
        self.assertEqual(asist_final.hora_entrada, datetime.time(8, 30))
        self.assertIsNotNone(asist_final.hora_salida)

    def test_10_y_11_flujo_autenticado_entrada_salida_y_calificacion_rf24_rf30_intactos(self):
        """10 y 11. Usuario autenticado conserva inscripción, entrada, salida y calificación obligatoria RF-24..RF-30, y la consulta pública maneja cuentas institucionales sin error."""
        c_est = Client()
        c_est.force_login(self.estudiante)
        resp_insc = c_est.post(reverse('participantes:inscribirse', kwargs={'id_evento': self.evento_a.pk}))
        self.assertEqual(resp_insc.status_code, 302)

        insc_est = Inscripcion.objects.get(evento=self.evento_a, participante__usuario=self.estudiante)

        # Si el estudiante intenta consultar sin sesión desde el enlace público, NO hay error 500 ni AccesoExterno
        c_anon = Client()
        resp_inst = c_anon.post(self.url_cons_a, {
            'documento': self.estudiante.documento,
            'dato_verificacion': self.estudiante.email,
        })
        self.assertEqual(resp_inst.status_code, 200)
        self.assertEqual(resp_inst.context['estado'], 'CUENTA_INSTITUCIONAL')
        self.assertFalse(AccesoExternoInscripcion.objects.filter(inscripcion=insc_est).exists())

        # Flujo institucional completo: entrada -> salida -> calificación obligatoria RF-24..RF-30
        iniciar_sesion_entrada_service(self.evento_a, operador=self.docente)
        token_qr_est = c_est.get(
            reverse('asistencia:qr_dinamico', kwargs={'id_inscripcion': insc_est.pk})
        ).json()['token']

        c_doc = Client()
        c_doc.force_login(self.docente)
        r_in = c_doc.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': self.evento_a.pk}),
            {'accion': 'qr', 'token_qr': token_qr_est},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(r_in.json()['exito'])

        cerrar_sesion_entrada_service(self.evento_a, operador=self.docente)
        ctrl_sal = iniciar_sesion_salida_service(self.evento_a, operador=self.docente)
        from asistencia.services import generar_token_salida_evento
        tok_sal = generar_token_salida_evento(self.evento_a, control=ctrl_sal)

        r_out = c_est.post(
            reverse('asistencia:registrar_salida_participante', kwargs={'id_evento': self.evento_a.pk}),
            {'token_salida': tok_sal},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(r_out.status_code, 200)
        self.assertTrue(r_out.json()['exito'])
        self.assertTrue(r_out.json()['requiere_calificacion'])

        # Calificar evento (5 estrellas) funciona sin regresiones
        r_cal = c_est.post(
            reverse('eventos:calificar_evento', kwargs={'id_evento': self.evento_a.pk}),
            {'puntuacion': '5'},
        )
        self.assertEqual(r_cal.status_code, 302)
        self.assertTrue(
            CalificacionEvento.objects.filter(
                evento=self.evento_a,
                estudiante=self.estudiante,
                puntuacion=5,
            ).exists()
        )

    def test_12_acceso_vigente_se_reutiliza_y_acceso_expirado_se_renueva(self):
        """Hallazgo 1: acceso vigente conserva token_hash; acceso expirado (no revocado) se renueva correctamente."""
        Client().post(self.url_reg_a, self.datos_externo)
        insc = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')
        acceso = AccesoExternoInscripcion.objects.get(inscripcion=insc)
        hash_inicial = acceso.token_hash

        # 1. Acceso vigente: recuperar no rota token_hash
        c_vig = Client()
        r_vig = c_vig.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(r_vig.status_code, 302)
        acceso.refresh_from_db()
        self.assertEqual(acceso.token_hash, hash_inicial)
        self.assertFalse(acceso.revocado)

        # 2. Acceso expirado (revocado=False): renovar vigencia y rotar token permitiendo acceso
        acceso.fecha_expiracion = timezone.now() - datetime.timedelta(days=2)
        acceso.save(update_fields=['fecha_expiracion'])
        self.assertFalse(acceso.es_valido)

        c_exp = Client()
        r_exp = c_exp.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(r_exp.status_code, 302)
        self.assertEqual(r_exp['Location'], self.url_portal)

        acceso.refresh_from_db()
        self.assertFalse(acceso.revocado)
        self.assertNotEqual(acceso.token_hash, hash_inicial)
        self.assertTrue(acceso.es_valido)
        self.assertEqual(c_exp.get(self.url_portal).status_code, 200)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_a).count(), 1)

    def test_13_acceso_revocado_bloquea_recuperacion_y_registro_sin_modificar_bd(self):
        """Hallazgo 1: acceso revocado (revocado=True) rechaza recuperación y reinscripción con 403 sin alterar BD ni asistencia."""
        Client().post(self.url_reg_a, self.datos_externo)
        insc = Inscripcion.objects.get(evento=self.evento_a, participante__documento='1045678901')
        asist_previa = Asistencia.objects.create(
            inscripcion=insc,
            fecha=self.evento_a.fecha,
            hora_entrada=datetime.time(8, 20),
            metodo=MetodoAsistencia.QR,
            estado=EstadoAsistencia.REGISTRADA,
        )

        # Revocación administrativa del acceso externo
        acceso = AccesoExternoInscripcion.objects.get(inscripcion=insc)
        acceso.revocar()
        acceso.refresh_from_db()
        hash_revocado = acceso.token_hash
        exp_revocada = acceso.fecha_expiracion
        fecha_rev = acceso.fecha_revocacion

        # A) Intento vía consulta pública -> 403 ACCESO_REVOCADO
        c_cons = Client()
        r_cons = c_cons.post(self.url_cons_a, {
            'documento': '1045678901',
            'dato_verificacion': 'maria.lopez@externo.org',
        })
        self.assertEqual(r_cons.status_code, 403)
        self.assertEqual(r_cons.context['estado'], 'ACCESO_REVOCADO')
        self.assertContains(r_cons, 'administrador', status_code=403)
        self.assertIsNone(c_cons.session.get('acceso_externo_id'))

        # B) Intento vía formulario de registro público -> 403 ACCESO_REVOCADO
        c_reg = Client()
        r_reg = c_reg.post(self.url_reg_a, self.datos_externo)
        self.assertEqual(r_reg.status_code, 403)
        self.assertEqual(r_reg.context['estado'], 'ACCESO_REVOCADO')
        self.assertIsNone(c_reg.session.get('acceso_externo_id'))

        # Confirmar integridad total: revocado sigue True, token/expiración/inscripción/asistencia intactos
        acceso.refresh_from_db()
        self.assertTrue(acceso.revocado)
        self.assertEqual(acceso.token_hash, hash_revocado)
        self.assertEqual(acceso.fecha_expiracion, exp_revocada)
        self.assertEqual(acceso.fecha_revocacion, fecha_rev)
        self.assertEqual(Inscripcion.objects.filter(evento=self.evento_a).count(), 1)
        asist_previa.refresh_from_db()
        self.assertEqual(asist_previa.hora_entrada, datetime.time(8, 20))
        self.assertEqual(asist_previa.estado, EstadoAsistencia.REGISTRADA)
        self.assertTrue(Auditoria.objects.filter(accion='RECUPERACION_ACCESO_REVOCADO_BLOQUEADA').exists())

    def test_14_rate_limit_por_documento_resiste_rotacion_ips_normalizacion_y_aisla_eventos(self):
        """Hallazgo 2: bloqueo por (evento, HMAC(documento normalizado)) resiste rotación de IPs, no expone PII y no afecta otros participantes ni eventos."""
        Client().post(self.url_reg_a, self.datos_externo)
        # Inscribir un segundo participante legítimo en el mismo evento
        datos_legitimo_2 = {
            'documento': '2098765432',
            'nombres': 'Carlos',
            'apellidos': 'Legítimo',
            'correo': 'carlos.legitimo@externo.org',
            'telefono': '3112223344',
            'institucion': 'Entidad Aliada',
            'acepta_politica_tratamiento': 'True',
        }
        Client().post(self.url_reg_a, datos_legitimo_2)

        # 5 intentos fallidos contra el mismo documento con variaciones de formato y 5 IPs distintas
        variaciones_doc = [
            '1045678901',
            ' 1045678901 ',
            '10.456.789-01',
            '10 456 789 01',
            '10456-78901',
        ]
        for idx, doc_var in enumerate(variaciones_doc, start=1):
            c_rot = Client()
            resp = c_rot.post(
                self.url_cons_a,
                {'documento': doc_var, 'dato_verificacion': f'fallo{idx}@mal.com'},
                REMOTE_ADDR=f'198.51.100.{idx}',
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIsNone(c_rot.session.get('acceso_externo_id'))

        # Intento #6 desde una 6ª IP completamente distinta (incluso con datos válidos) -> HTTP 429
        c_ip6 = Client()
        r_429 = c_ip6.post(
            self.url_cons_a,
            {'documento': '1045678901', 'dato_verificacion': 'maria.lopez@externo.org'},
            REMOTE_ADDR='198.51.100.66',
        )
        self.assertEqual(r_429.status_code, 429)
        self.assertIsNone(c_ip6.session.get('acceso_externo_id'))
        self.assertNotContains(r_429, 'María Fernanda', status_code=429)
        self.assertNotContains(r_429, 'maria.lopez@externo.org', status_code=429)

        # Verificar que NINGÚN registro de rate limit en Auditoria almacena el documento en texto plano
        logs_rl = list(Auditoria.objects.filter(accion='CONSULTA_PUBLICA_FALLIDA'))
        self.assertEqual(len(logs_rl), 5)
        for lg in logs_rl:
            self.assertNotIn('1045678901', lg.registro_afectado)
            self.assertNotIn('10.456.789-01', lg.registro_afectado)
            self.assertNotIn('maria.lopez', lg.registro_afectado)

        # Otro participante legítimo del MISMO evento desde otra IP NO queda bloqueado
        c_p2 = Client()
        r_p2 = c_p2.post(
            self.url_cons_a,
            {'documento': '2098765432', 'dato_verificacion': 'carlos.legitimo@externo.org'},
            REMOTE_ADDR='203.0.113.77',
        )
        self.assertEqual(r_p2.status_code, 302)
        self.assertEqual(r_p2['Location'], self.url_portal)

        # Independencia entre eventos: el mismo documento bloqueado en evento_a NO queda bloqueado en evento_b
        c_evb = Client()
        r_evb = c_evb.post(
            self.url_cons_b,
            {'documento': '1045678901', 'dato_verificacion': 'maria.lopez@externo.org'},
            REMOTE_ADDR='198.51.100.88',
        )
        self.assertNotEqual(r_evb.status_code, 429)

    def test_15_rate_limit_compartido_en_inscripcion_nueva_y_proteccion_spoofing_xff(self):
        """Hallazgo 2: el rate limiting aplica en inscripción nueva y resiste suplantación del primer salto de X-Forwarded-For."""
        Client().post(self.url_reg_a, self.datos_externo)

        # 5 intentos fallidos de validación en inscripcion_publica_view con XFF izquierdo suplantado pero IP proxy fija
        for idx in range(1, CONSULTA_MAX_INTENTOS + 1):
            c_atk = Client()
            datos_mal = dict(self.datos_externo, correo=f'impostor{idx}@otro.org')
            resp = c_atk.post(
                self.url_reg_a,
                datos_mal,
                HTTP_X_FORWARDED_FOR=f'10.0.0.{idx}, 203.0.113.50',
                REMOTE_ADDR='127.0.0.1',
            )
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.context['estado'], 'DATOS_NO_COINCIDEN')

        # El intento #6 en inscripcion_publica_view (incluso con otro documento y XFF izquierdo distinto) -> HTTP 429 por IP proxy real
        c_blk_reg = Client()
        r_429_reg = c_blk_reg.post(
            self.url_reg_a,
            dict(self.datos_externo, documento='9998887776', correo='otro@correo.org'),
            HTTP_X_FORWARDED_FOR='10.0.0.99, 203.0.113.50',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(r_429_reg.status_code, 429)
        self.assertEqual(r_429_reg.context['estado'], 'RATE_LIMIT')

        # Y si intenta saltar a consultar_inscripcion_publica desde la misma IP proxy -> también HTTP 429 compartido
        c_blk_cons = Client()
        r_429_cons = c_blk_cons.post(
            self.url_cons_a,
            {'documento': '1045678901', 'dato_verificacion': 'maria.lopez@externo.org'},
            HTTP_X_FORWARDED_FOR='10.0.0.123, 203.0.113.50',
            REMOTE_ADDR='127.0.0.1',
        )
        self.assertEqual(r_429_cons.status_code, 429)
        self.assertTrue(Auditoria.objects.filter(accion='CONSULTA_INSCRIPCION_BLOQUEADA_RATE_LIMIT').exists())
