import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from usuarios.models import Rol, Usuario
from eventos.models import CategoriaEvento, Evento, ModalidadEvento, ModalidadInscripcion, EstadoEvento
from eventos.forms import EventoForm
from participantes.models import Participante, Inscripcion, TipoParticipante, EstadoInscripcion
from auditoria.models import Auditoria


class CatalogoEventosTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_coord = Rol.objects.create(nombre='Coordinador')
        self.organizador = Usuario.objects.create_user(
            username='organizador_cat',
            email='org@uniminuto.edu.co',
            password='TestPassword123*',
            documento='10102020',
            nombres='Coordinador',
            apellidos='Eventos',
            rol=self.rol_coord
        )
        self.cat_academica = CategoriaEvento.objects.create(nombre='Académico')
        self.cat_cultural = CategoriaEvento.objects.create(nombre='Cultural')

        self.evento_publicado = Evento.objects.create(
            nombre='Congreso de Innovación Social',
            descripcion='Espacio de divulgación científica y comunitaria.',
            fecha=datetime.date(2026, 11, 25),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(13, 0),
            lugar='Auditorio Principal UNIMINUTO',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=100,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.cat_academica,
            organizador=self.organizador
        )

        self.evento_virtual = Evento.objects.create(
            nombre='Taller Virtual de Fotografía',
            descripcion='Taller práctico mediante plataforma Teams.',
            fecha=datetime.date(2026, 11, 26),
            hora_inicio=datetime.time(14, 0),
            hora_fin=datetime.time(16, 0),
            lugar='Microsoft Teams',
            modalidad=ModalidadEvento.VIRTUAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.cat_cultural,
            organizador=self.organizador
        )

        self.evento_borrador = Evento.objects.create(
            nombre='Seminario Interno en Planificación',
            descripcion='Borrador no publicado.',
            fecha=datetime.date(2026, 12, 1),
            hora_inicio=datetime.time(10, 0),
            hora_fin=datetime.time(12, 0),
            lugar='Sala de Juntas',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=20,
            estado=EstadoEvento.BORRADOR,
            categoria=self.cat_academica,
            organizador=self.organizador
        )

    def test_catalogo_muestra_eventos_publicados_y_no_borradores(self):
        """El catálogo público lista únicamente los eventos en estado PUBLICADO por defecto."""
        response = self.client.get(reverse('eventos:catalogo'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Congreso de Innovación Social')
        self.assertContains(response, 'Taller Virtual de Fotografía')
        self.assertNotContains(response, 'Seminario Interno en Planificación')

    def test_catalogo_filtro_por_categoria(self):
        """El filtro de categoría retorna únicamente los eventos asociados a la categoría seleccionada."""
        response = self.client.get(reverse('eventos:catalogo'), {'categoria': self.cat_cultural.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Taller Virtual de Fotografía')
        self.assertNotContains(response, 'Congreso de Innovación Social')

    def test_catalogo_filtro_por_modalidad(self):
        """El filtro de modalidad retorna únicamente los eventos con dicha modalidad."""
        response = self.client.get(reverse('eventos:catalogo'), {'modalidad': ModalidadEvento.VIRTUAL})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Taller Virtual de Fotografía')
        self.assertNotContains(response, 'Congreso de Innovación Social')

    def test_catalogo_busqueda_por_texto(self):
        """La búsqueda por palabra clave filtra correctamente por nombre o descripción."""
        response = self.client.get(reverse('eventos:catalogo'), {'q': 'divulgación'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Congreso de Innovación Social')
        self.assertNotContains(response, 'Taller Virtual de Fotografía')

    def test_catalogo_sin_resultados_muestra_mensaje(self):
        """Cuando ningún evento coincide con los filtros, se muestra un estado amigable."""
        response = self.client.get(reverse('eventos:catalogo'), {'q': 'NoExisteNingunEventoConEsteNombreXYZ'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se encontraron eventos')

    def test_detalle_evento_muestra_informacion_completa(self):
        """La página de detalle muestra todos los campos informativos y cupo disponible."""
        response = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': self.evento_publicado.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Congreso de Innovación Social')
        self.assertContains(response, 'Auditorio Principal UNIMINUTO')
        self.assertContains(response, 'Académico')
        self.assertContains(response, 'Presencial')
        self.assertContains(response, '0 inscritos de 100 cupos')
        self.assertContains(response, 'Quedan <strong>100</strong> cupos disponibles.')

    def test_detalle_evento_no_existente_retorna_404(self):
        """Consultar un evento inexistente debe retornar código 404."""
        response = self.client.get(reverse('eventos:detalle', kwargs={'id_evento': 999999}))
        self.assertEqual(response.status_code, 404)


class GestionEventosTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_admin = Rol.objects.create(nombre='Administrador')
        self.rol_docente = Rol.objects.create(nombre='Docente')
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

        self.admin_user = Usuario.objects.create_user(
            username='admin_user',
            email='admin@uniminuto.edu.co',
            password='Password123*',
            documento='11111111',
            rol=self.rol_admin,
            is_staff=True
        )

        self.docente_user = Usuario.objects.create_user(
            username='docente_user',
            email='docente@uniminuto.edu.co',
            password='Password123*',
            documento='22222222',
            rol=self.rol_docente
        )

        self.docente_otro = Usuario.objects.create_user(
            username='docente_otro',
            email='docente2@uniminuto.edu.co',
            password='Password123*',
            documento='33333333',
            rol=self.rol_docente
        )

        self.estudiante_user = Usuario.objects.create_user(
            username='estudiante_user',
            email='estudiante@uniminuto.edu.co',
            password='Password123*',
            documento='44444444',
            rol=self.rol_estudiante
        )

        self.categoria = CategoriaEvento.objects.create(nombre='Científico')

        self.evento_docente = Evento.objects.create(
            nombre='Seminario de Inteligencia Artificial',
            descripcion='IA en la educación superior.',
            fecha=datetime.date(2026, 12, 10),
            hora_inicio=datetime.time(8, 0),
            hora_fin=datetime.time(11, 0),
            lugar='Laboratorio 402',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=30,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.docente_user
        )

    def test_gestion_anonimo_redirige_a_login(self):
        """Un usuario no autenticado es redirigido al login al intentar gestionar o crear eventos."""
        resp_gestion = self.client.get(reverse('eventos:mis_eventos'))
        self.assertEqual(resp_gestion.status_code, 302)
        self.assertIn(reverse('usuarios:login'), resp_gestion.url)

        resp_crear = self.client.get(reverse('eventos:crear'))
        self.assertEqual(resp_crear.status_code, 302)
        self.assertIn(reverse('usuarios:login'), resp_crear.url)

    def test_estudiante_no_puede_crear_eventos(self):
        """Un usuario con rol Estudiante no tiene permisos para crear eventos institucionales (403)."""
        self.client.login(username='estudiante_user', password='Password123*')
        response = self.client.get(reverse('eventos:crear'))
        self.assertEqual(response.status_code, 403)

    def test_docente_puede_crear_evento_con_auditoria(self):
        """Un docente autorizado puede crear un evento y se genera registro de auditoría."""
        self.client.login(username='docente_user', password='Password123*')
        response = self.client.post(reverse('eventos:crear'), {
            'nombre': 'Coloquio de Pedagogía',
            'descripcion': 'Innovaciones curriculares.',
            'fecha': '2026-12-15',
            'hora_inicio': '09:00',
            'hora_fin': '12:00',
            'lugar': 'Aula Máxima',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'cupo': 80,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        nuevo_evento = Evento.objects.filter(nombre='Coloquio de Pedagogía').first()
        self.assertIsNotNone(nuevo_evento)
        self.assertEqual(nuevo_evento.organizador, self.docente_user)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.docente_user,
            accion='CREAR_EVENTO',
            modulo='EVENTOS'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn(nuevo_evento.nombre, auditoria.registro_afectado)

    def test_validacion_horario_evento(self):
        """La validación del formulario rechaza eventos cuya hora fin sea menor o igual a la hora inicio."""
        self.client.login(username='docente_user', password='Password123*')
        response = self.client.post(reverse('eventos:crear'), {
            'nombre': 'Evento Horario Invalido',
            'descripcion': 'Prueba de validación.',
            'fecha': '2026-12-15',
            'hora_inicio': '14:00',
            'hora_fin': '10:00',  # Inválido: fin menor que inicio
            'lugar': 'Aula 101',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'cupo': 50,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La hora de fin debe ser posterior a la hora de inicio')
        self.assertFalse(Evento.objects.filter(nombre='Evento Horario Invalido').exists())

    def test_docente_puede_editar_su_propio_evento(self):
        """El organizador puede editar su propio evento y se genera auditoría."""
        self.client.login(username='docente_user', password='Password123*')
        response = self.client.post(
            reverse('eventos:editar', kwargs={'id_evento': self.evento_docente.pk}),
            {
                'nombre': 'Seminario de Inteligencia Artificial - Actualizado',
                'descripcion': 'Nueva descripción ampliada.',
                'fecha': '2026-12-10',
                'hora_inicio': '08:00',
                'hora_fin': '11:00',
                'lugar': 'Laboratorio 402',
                'modalidad': ModalidadEvento.PRESENCIAL,
                'cupo': 35,
                'estado': EstadoEvento.PUBLICADO,
                'categoria': self.categoria.pk,
            },
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.evento_docente.refresh_from_db()
        self.assertEqual(self.evento_docente.nombre, 'Seminario de Inteligencia Artificial - Actualizado')
        self.assertEqual(self.evento_docente.cupo, 35)

        # Auditoría de actualización
        auditoria = Auditoria.objects.filter(
            usuario=self.docente_user,
            accion='EDITAR_EVENTO',
            modulo='EVENTOS'
        ).first()
        self.assertIsNotNone(auditoria)

    def test_docente_no_puede_editar_evento_ajeno(self):
        """Un docente no organizador no puede modificar eventos de terceros (403)."""
        self.client.login(username='docente_otro', password='Password123*')
        response = self.client.post(
            reverse('eventos:editar', kwargs={'id_evento': self.evento_docente.pk}),
            {
                'nombre': 'Intento no autorizado',
                'descripcion': 'Hacking attempt.',
                'fecha': '2026-12-10',
                'hora_inicio': '08:00',
                'hora_fin': '11:00',
                'lugar': 'Laboratorio 402',
                'modalidad': ModalidadEvento.PRESENCIAL,
                'cupo': 35,
                'estado': EstadoEvento.PUBLICADO,
                'categoria': self.categoria.pk,
            }
        )
        self.assertEqual(response.status_code, 403)
        self.evento_docente.refresh_from_db()
        self.assertNotEqual(self.evento_docente.nombre, 'Intento no autorizado')

    def test_docente_puede_cancelar_su_propio_evento(self):
        """(RF-05) El organizador puede cancelar formalmente su evento con motivo obligatorio."""
        self.client.login(username='docente_user', password='Password123*')
        response = self.client.post(
            reverse('eventos:cancelar', kwargs={'id_evento': self.evento_docente.pk}),
            {'motivo_cancelacion': 'Indisposición de los ponentes principales.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.evento_docente.refresh_from_db()
        self.assertEqual(self.evento_docente.estado, EstadoEvento.CANCELADO)
        self.assertContains(response, 'fue cancelado formalmente')

        # Auditoría de cancelación
        auditoria = Auditoria.objects.filter(
            usuario=self.docente_user,
            accion='CANCELAR_EVENTO',
            modulo='EVENTOS'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn('Indisposición de los ponentes', auditoria.registro_afectado)

    def test_administrador_puede_cancelar_cualquier_evento(self):
        """(RF-05) Un Administrador institucional puede cancelar cualquier evento."""
        self.client.login(username='admin_user', password='Password123*')
        response = self.client.post(
            reverse('eventos:cancelar', kwargs={'id_evento': self.evento_docente.pk}),
            {'motivo_cancelacion': 'Fuerza mayor por mantenimiento de campus.'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.evento_docente.refresh_from_db()
        self.assertEqual(self.evento_docente.estado, EstadoEvento.CANCELADO)

        auditoria = Auditoria.objects.filter(
            usuario=self.admin_user,
            accion='CANCELAR_EVENTO',
            modulo='EVENTOS'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn('Fuerza mayor', auditoria.registro_afectado)

    def test_cancelar_evento_denegado_a_usuario_ajeno(self):
        """(RF-05) Un usuario ajeno o no autorizado no puede cancelar el evento (403)."""
        self.client.login(username='docente_otro', password='Password123*')
        resp = self.client.post(
            reverse('eventos:cancelar', kwargs={'id_evento': self.evento_docente.pk}),
            {'motivo_cancelacion': 'Intento no autorizado'}
        )
        self.assertEqual(resp.status_code, 403)
        self.evento_docente.refresh_from_db()
        self.assertNotEqual(self.evento_docente.estado, EstadoEvento.CANCELADO)

    def test_cancelar_evento_requiere_motivo(self):
        """(RF-05) La cancelación requiere un motivo formal obligatorio."""
        self.client.login(username='docente_user', password='Password123*')
        resp = self.client.post(
            reverse('eventos:cancelar', kwargs={'id_evento': self.evento_docente.pk}),
            {'motivo_cancelacion': '   '}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Debes proporcionar un motivo justificado')
        self.evento_docente.refresh_from_db()
        self.assertNotEqual(self.evento_docente.estado, EstadoEvento.CANCELADO)

    def test_evento_cancelado_impide_inscripciones_y_preserva_existentes(self):
        """(RF-05) El evento cancelado impide nuevas inscripciones y preserva el historial de las previas."""
        # 1. Crear inscripción previa
        part = Participante.objects.create(
            tipo=TipoParticipante.ESTUDIANTE,
            documento='44444444',
            usuario=self.estudiante_user
        )
        insc = Inscripcion.objects.create(
            evento=self.evento_docente,
            participante=part,
            estado=EstadoInscripcion.ACTIVA
        )

        # 2. Cancelar el evento
        self.evento_docente.estado = EstadoEvento.CANCELADO
        self.evento_docente.save()

        # 3. Verificar que la inscripción previa sigue existiendo intacta
        insc.refresh_from_db()
        self.assertEqual(insc.estado, EstadoInscripcion.ACTIVA)

        # 4. Intentar nueva inscripción sobre el evento cancelado (debe ser rechazada)
        self.client.login(username='estudiante_user', password='Password123*')
        resp_insc = self.client.post(
            reverse('participantes:inscribirse', kwargs={'id_evento': self.evento_docente.pk}),
            follow=True
        )
        self.assertEqual(resp_insc.status_code, 200)
        self.assertContains(resp_insc, 'Cancelado')


class ModalidadInscripcionModelTests(TestCase):
    """
    Pruebas unitarias de estructura y validación de la modalidad de inscripción (RF-01, Etapa 7.1).
    """
    def setUp(self):
        self.rol = Rol.objects.create(nombre='Docente')
        self.organizador = Usuario.objects.create_user(
            username='profesor_mod',
            email='profesor_mod@uniminuto.edu.co',
            password='TestPassword123*',
            documento='55556666',
            rol=self.rol
        )
        self.categoria = CategoriaEvento.objects.create(nombre='Investigación')

    def test_modalidad_inscripcion_default_seguro_solo_invitacion(self):
        """Al crear un evento sin especificar modalidad_inscripcion, se asigna SOLO_INVITACION por seguridad."""
        evento = Evento.objects.create(
            nombre='Evento Sin Modalidad Explicita',
            descripcion='Prueba de valor predeterminado seguro',
            fecha=datetime.date(2026, 12, 1),
            hora_inicio=datetime.time(9, 0),
            hora_fin=datetime.time(11, 0),
            lugar='Aula 201',
            modalidad=ModalidadEvento.PRESENCIAL,
            cupo=50,
            estado=EstadoEvento.PUBLICADO,
            categoria=self.categoria,
            organizador=self.organizador
        )
        self.assertEqual(evento.modalidad_inscripcion, ModalidadInscripcion.SOLO_INVITACION)

    def test_modalidad_inscripcion_valores_validos(self):
        """Permite guardar eventos con las tres modalidades canónicas: SOLO_INVITACION, ABIERTA y MIXTA."""
        for val in [ModalidadInscripcion.SOLO_INVITACION, ModalidadInscripcion.ABIERTA, ModalidadInscripcion.MIXTA]:
            evento = Evento.objects.create(
                nombre=f'Evento Modalidad {val}',
                descripcion='Prueba de opciones válidas',
                fecha=datetime.date(2026, 12, 2),
                hora_inicio=datetime.time(10, 0),
                hora_fin=datetime.time(12, 0),
                lugar='Virtual',
                modalidad=ModalidadEvento.VIRTUAL,
                modalidad_inscripcion=val,
                cupo=30,
                estado=EstadoEvento.PUBLICADO,
                categoria=self.categoria,
                organizador=self.organizador
            )
            self.assertEqual(evento.modalidad_inscripcion, val)

    def test_evento_form_contiene_modalidad_inscripcion(self):
        """El formulario EventoForm incluye el campo modalidad_inscripcion y permite su selección."""
        form = EventoForm()
        self.assertIn('modalidad_inscripcion', form.fields)

        form_data = {
            'nombre': 'Evento Form Test',
            'descripcion': 'Descripción formal del evento.',
            'fecha': '2026-12-20',
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'lugar': 'Auditorio Central',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'modalidad_inscripcion': ModalidadInscripcion.SOLO_INVITACION,
            'cupo': 40,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        }
        form_bound = EventoForm(data=form_data)
        self.assertTrue(form_bound.is_valid(), form_bound.errors)
        self.assertEqual(form_bound.cleaned_data['modalidad_inscripcion'], ModalidadInscripcion.SOLO_INVITACION)

    def test_evento_form_modalidad_inscripcion_default_cuando_omite(self):
        """Si en el POST de EventoForm se omite modalidad_inscripcion, se autocompleta con SOLO_INVITACION."""
        form_data = {
            'nombre': 'Evento Omitiendo Modalidad',
            'descripcion': 'Descripción formal.',
            'fecha': '2026-12-20',
            'hora_inicio': '08:00',
            'hora_fin': '10:00',
            'lugar': 'Auditorio Central',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'cupo': 40,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': self.categoria.pk,
        }
        form_bound = EventoForm(data=form_data)
        self.assertTrue(form_bound.is_valid(), form_bound.errors)
        self.assertEqual(form_bound.cleaned_data['modalidad_inscripcion'], ModalidadInscripcion.SOLO_INVITACION)
