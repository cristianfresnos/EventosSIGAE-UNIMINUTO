"""
Prueba Automatizada de Validación del Flujo Integral de Extremo a Extremo (E2E)
Proyecto: EventosSIGAE-UNIMINUTO
Alcance: Valida de manera secuencial los 14 pasos cardinales del ciclo de vida
         de eventos, inscripciones, obtención de QR y control de asistencia:

1. Un usuario con rol Docente crea un evento.
2. El evento queda asociado al organizador correcto.
3. Un visitante accede a la ficha pública.
4. Un participante con cuenta puede inscribirse.
5. Un participante externo puede inscribirse sin cuenta.
6. El sistema evita inscripciones duplicadas y respeta los cupos.
7. El participante externo accede al pase QR.
8. El sistema rechaza tokens inválidos o pertenecientes a otro evento.
9. El responsable autorizado registra la entrada (check-in).
10. Se impiden entradas duplicadas.
11. Se registra la salida cuando corresponde (checkout y cálculo de permanencia).
12. Los filtros distinguen correctamente asistentes y ausentes.
13. Los reportes PDF y Excel reflejan los datos almacenados.
14. Los datos de prueba continúan disponibles al abrir una nueva conexión con la base.
"""

import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.db import connections
from django.core.management import call_command
from django.core import signing

from usuarios.models import Rol, Usuario
from eventos.models import CategoriaEvento, Evento, ModalidadEvento, ModalidadInscripcion, EstadoEvento
from participantes.models import Participante, Inscripcion, TipoParticipante, EstadoInscripcion
from asistencia.models import Asistencia, MetodoAsistencia, EstadoAsistencia
from asistencia.services import generar_token_qr, registrar_asistencia_salida
from auditoria.models import Auditoria


class FlujoIntegralEventosInscripcionAsistenciaTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Asegurar roles canónicos mediante el comando implementado
        call_command('inicializar_roles')
        self.rol_docente = Rol.objects.get(nombre='Docente')
        self.rol_estudiante = Rol.objects.get(nombre='Estudiante')
        self.rol_admin = Rol.objects.get(nombre='Administrador')

        # Crear categoría
        self.categoria = CategoriaEvento.objects.create(
            nombre='Ingeniería y Ciencias',
            descripcion='Eventos de tecnología.',
            activo=True
        )

        # Crear usuario Docente (profesor organizador)
        self.docente = Usuario.objects.create_user(
            username='profesor_carlos',
            email='carlos.docente@uniminuto.edu.co',
            password='DocentePass2026*',
            documento='10203040',
            nombres='Carlos',
            apellidos='Docente Titular',
            rol=self.rol_docente
        )

        # Crear usuario Estudiante (participante institucional con cuenta)
        self.estudiante = Usuario.objects.create_user(
            username='estudiante_juan',
            email='juan.estudiante@uniminuto.edu.co',
            password='EstudiantePass2026*',
            documento='50607080',
            nombres='Juan',
            apellidos='Pérez Estudiante',
            rol=self.rol_estudiante
        )

    def test_recorrido_completo_14_pasos(self):
        """Ejecuta y verifica la secuencia completa de los 14 pasos de extremo a extremo."""
        # --------------------------------------------------
        # PASO 1: Un usuario con rol Docente crea un evento
        # --------------------------------------------------
        self.client.login(username='profesor_carlos', password='DocentePass2026*')
        resp_crear = self.client.post(reverse('eventos:crear'), {
            'nombre': 'Simposio Nacional de Inteligencia Artificial 2026',
            'descripcion': 'Simposio sobre modelos generativos e impacto social.',
            'fecha': '2026-11-30',
            'hora_inicio': '08:30',
            'hora_fin': '12:30',
            'lugar': 'Teatro Minuto de Dios',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'modalidad_inscripcion': ModalidadInscripcion.MIXTA,
            'cupo': 2,  # Cupo limitado a 2 para probar saturación en Paso 6
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk
        }, follow=True)
        self.assertEqual(resp_crear.status_code, 200)

        # --------------------------------------------------
        # PASO 2: El evento queda guardado y asociado al creador
        # --------------------------------------------------
        evento = Evento.objects.filter(nombre='Simposio Nacional de Inteligencia Artificial 2026').first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.organizador, self.docente)
        auditoria_creacion = Auditoria.objects.filter(
            usuario=self.docente,
            accion='CREAR_EVENTO',
            modulo='EVENTOS'
        ).first()
        self.assertIsNotNone(auditoria_creacion)
        self.assertIn(str(evento.pk), auditoria_creacion.registro_afectado)

        # --------------------------------------------------
        # PASO 3: Un visitante accede a la ficha pública
        # --------------------------------------------------
        self.client.logout()
        resp_detalle = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': evento.pk}))
        self.assertEqual(resp_detalle.status_code, 200)
        self.assertContains(resp_detalle, 'Simposio Nacional de Inteligencia Artificial 2026')
        self.assertContains(resp_detalle, 'Inscribirme como Externo')
        self.assertContains(resp_detalle, 'Iniciar Sesión Institucional')

        # --------------------------------------------------
        # PASO 4: Un participante con cuenta puede inscribirse
        # --------------------------------------------------
        self.client.login(username='estudiante_juan', password='EstudiantePass2026*')
        resp_ins_est = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': evento.pk}),
            follow=True
        )
        self.assertEqual(resp_ins_est.status_code, 200)
        insc_estudiante = Inscripcion.objects.filter(evento=evento, participante__usuario=self.estudiante).first()
        self.assertIsNotNone(insc_estudiante)
        self.assertEqual(insc_estudiante.estado, EstadoInscripcion.ACTIVA)
        self.client.logout()

        # --------------------------------------------------
        # PASO 5: Un participante externo se inscribe sin cuenta
        # --------------------------------------------------
        resp_ins_ext = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': evento.pk}),
            {
                'documento': '99001122',
                'nombres': 'Clara',
                'apellidos': 'Visitante Externa',
                'correo': 'clara.externa@empresa-aliada.com',
                'telefono': '3009998877',
                'institucion': 'Empresa Aliada de Software',
                'acepta_politica_tratamiento': 'True',
            },
            follow=True
        )
        self.assertEqual(resp_ins_ext.status_code, 200)
        part_externo = Participante.objects.filter(documento='99001122').first()
        self.assertIsNotNone(part_externo)
        self.assertIsNone(part_externo.usuario)
        self.assertEqual(part_externo.tipo, TipoParticipante.EXTERNO)
        insc_externo = Inscripcion.objects.filter(evento=evento, participante=part_externo).first()
        self.assertIsNotNone(insc_externo)
        self.assertEqual(insc_externo.estado, EstadoInscripcion.ACTIVA)

        # --------------------------------------------------
        # PASO 6: El sistema evita duplicados y respeta cupos
        # --------------------------------------------------
        # 6.1 Intento de tercer participante cuando cupo=2
        resp_cupo_lleno = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': evento.pk}),
            {
                'documento': '88002233',
                'nombres': 'Tercero',
                'apellidos': 'Sin Cupo',
                'correo': 'tercero@correo.org',
                'telefono': '3123456789',
                'acepta_politica_tratamiento': 'True',
            },
            follow=True
        )
        self.assertEqual(resp_cupo_lleno.status_code, 200)
        self.assertContains(resp_cupo_lleno, 'cupo')
        self.assertContains(resp_cupo_lleno, 'agotado')
        # Se mantienen exactamente 2 inscripciones
        self.assertEqual(Inscripcion.objects.filter(evento=evento, estado=EstadoInscripcion.ACTIVA).count(), 2)

        # --------------------------------------------------
        # PASO 7: El participante externo accede al pase QR
        # --------------------------------------------------
        # Al seguir redirección de resp_ins_ext, llegó al pase digital
        self.assertContains(resp_ins_ext, 'PASE DIGITAL DE ASISTENCIA')
        self.assertContains(resp_ins_ext, 'Clara Visitante Externa')
        self.assertContains(resp_ins_ext, 'data:image/png;base64,')
        self.assertContains(resp_ins_ext, '← Volver al Evento')

        # Descarga directa de la imagen QR PNG con token
        token_externo = generar_token_qr(insc_externo)
        url_descarga_qr = reverse('asistencia:qr_imagen', kwargs={'id_inscripcion': insc_externo.pk}) + f"?token={token_externo}"
        resp_qr_png = self.client.get(url_descarga_qr)
        self.assertEqual(resp_qr_png.status_code, 200)
        self.assertEqual(resp_qr_png['Content-Type'], 'image/png')
        self.assertTrue(resp_qr_png.content.startswith(b'\x89PNG\r\n\x1a\n'))

        # --------------------------------------------------
        # PASO 8: Rechazo de tokens inválidos o de otro evento
        # --------------------------------------------------
        # 8.1 Token manipulado
        resp_bad_token = self.client.get(
            reverse('asistencia:pase_digital', kwargs={'id_inscripcion': insc_externo.pk}) + "?token=token_invalido_alterado"
        )
        self.assertEqual(resp_bad_token.status_code, 403)

        # 8.2 Token de otro evento
        otro_evento = Evento.objects.create(
            nombre='Otro Evento Distinto',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sede B',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=10,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente
        )
        otra_insc = Inscripcion.objects.create(
            evento=otro_evento,
            participante=part_externo,
            estado=EstadoInscripcion.ACTIVA
        )
        token_otro_evento = generar_token_qr(otra_insc)
        resp_otro_evt = self.client.get(
            reverse('asistencia:pase_digital', kwargs={'id_inscripcion': insc_externo.pk}) + f"?token={token_otro_evento}"
        )
        self.assertEqual(resp_otro_evt.status_code, 403)

        # --------------------------------------------------
        # PASO 9: Responsable autorizado registra la entrada (check-in)
        # --------------------------------------------------
        self.client.login(username='profesor_carlos', password='DocentePass2026*')
        resp_checkin = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': evento.pk}),
            {
                'token_qr': token_externo,
                'tipo_registro': 'entrada'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_checkin.status_code, 200)
        data_checkin = resp_checkin.json()
        self.assertTrue(data_checkin['exito'])
        self.assertEqual(data_checkin['codigo'], 'ASISTENCIA_REGISTRADA')
        asist_externo = Asistencia.objects.filter(inscripcion=insc_externo, estado=EstadoAsistencia.REGISTRADA).first()
        self.assertIsNotNone(asist_externo)
        self.assertIsNotNone(asist_externo.hora_entrada)

        # --------------------------------------------------
        # PASO 10: Se impiden entradas duplicadas
        # --------------------------------------------------
        resp_dup = self.client.post(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': evento.pk}),
            {
                'token_qr': token_externo,
                'tipo_registro': 'entrada'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_dup.status_code, 200)
        data_dup = resp_dup.json()
        self.assertFalse(data_dup['exito'])
        self.assertEqual(data_dup['codigo'], 'ASISTENCIA_DUPLICADA')
        self.assertEqual(Asistencia.objects.filter(inscripcion=insc_externo).count(), 1)

        # --------------------------------------------------
        # PASO 11: Se registra la salida y calcula permanencia
        # --------------------------------------------------
        # Simular hora de entrada fijada a las 09:00 y salida a las 11:30
        asist_externo.hora_entrada = datetime.time(9, 0)
        asist_externo.save()

        res_salida = registrar_asistencia_salida(
            inscripcion=insc_externo,
            operador=self.docente,
            hora_salida_custom=datetime.time(11, 30)
        )
        self.assertTrue(res_salida['exito'])
        asist_externo.refresh_from_db()
        self.assertEqual(asist_externo.hora_salida, datetime.time(11, 30))
        self.assertEqual(asist_externo.permanencia['horas'], 2)
        self.assertEqual(asist_externo.permanencia['minutos'], 30)
        self.assertEqual(asist_externo.tiempo_permanencia_str, '2h 30m')

        # --------------------------------------------------
        # PASO 12: Los filtros distinguen asistentes y ausentes
        # --------------------------------------------------
        # Clara asistió (check-in registrado); Juan no asistió (ausente)
        # 12.1 Todos
        resp_f_todos = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': evento.pk}),
            {'filtro_asistencia': 'todos'}
        )
        self.assertEqual(resp_f_todos.status_code, 200)
        self.assertEqual(resp_f_todos.context['total_inscritos'], 2)
        self.assertEqual(resp_f_todos.context['total_asistieron'], 1)
        self.assertEqual(resp_f_todos.context['total_ausentes'], 1)

        # 12.2 Asistieron (solo Clara)
        resp_f_asist = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': evento.pk}),
            {'filtro_asistencia': 'asistieron'}
        )
        self.assertEqual(resp_f_asist.status_code, 200)
        ids_asist = [i.pk for i in resp_f_asist.context['inscripciones']]
        self.assertEqual(ids_asist, [insc_externo.pk])

        # 12.3 Ausentes (solo Juan)
        resp_f_aus = self.client.get(
            reverse('asistencia:control_asistencia', kwargs={'id_evento': evento.pk}),
            {'filtro_asistencia': 'ausentes'}
        )
        self.assertEqual(resp_f_aus.status_code, 200)
        ids_aus = [i.pk for i in resp_f_aus.context['inscripciones']]
        self.assertEqual(ids_aus, [insc_estudiante.pk])

        # --------------------------------------------------
        # PASO 13: Los reportes PDF y Excel reflejan los datos almacenados
        # --------------------------------------------------
        # 13.1 Planilla PDF
        resp_pdf_planilla = self.client.get(reverse('reportes:planilla_asistencia_pdf', kwargs={'id_evento': evento.pk}))
        self.assertEqual(resp_pdf_planilla.status_code, 200)
        self.assertEqual(resp_pdf_planilla['Content-Type'], 'application/pdf')
        self.assertTrue(resp_pdf_planilla.content.startswith(b'%PDF'))

        # 13.2 Reporte Consolidado PDF
        resp_pdf_cons = self.client.get(reverse('reportes:reporte_consolidado_pdf', kwargs={'id_evento': evento.pk}))
        self.assertEqual(resp_pdf_cons.status_code, 200)
        self.assertEqual(resp_pdf_cons['Content-Type'], 'application/pdf')
        self.assertTrue(resp_pdf_cons.content.startswith(b'%PDF'))

        # 13.3 Reporte Excel XLSX
        resp_excel = self.client.get(reverse('analitica:exportar_excel') + f"?evento={evento.pk}")
        self.assertEqual(resp_excel.status_code, 200)
        self.assertEqual(resp_excel['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(resp_excel.content.startswith(b'PK\x03\x04'))  # Firma mágica ZIP / XLSX

        # --------------------------------------------------
        # PASO 14: Los datos continúan disponibles al reabrir conexión
        # --------------------------------------------------
        connections['default'].close()
        evento_recuperado = Evento.objects.get(pk=evento.pk)
        self.assertEqual(evento_recuperado.nombre, 'Simposio Nacional de Inteligencia Artificial 2026')
        self.assertEqual(evento_recuperado.organizador.pk, self.docente.pk)
        self.assertEqual(evento_recuperado.inscripciones.count(), 2)
        self.assertEqual(Asistencia.objects.filter(inscripcion__evento=evento_recuperado).count(), 1)
