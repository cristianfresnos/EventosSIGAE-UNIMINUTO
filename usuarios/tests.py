import os
import datetime
import hashlib
from django.utils import timezone
from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from usuarios.models import Rol, Usuario, TokenVerificacionCorreo
from auditoria.models import Auditoria


class UsuariosPortalTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')
        self.usuario = Usuario.objects.create_user(
            username='user_portal',
            email='user_portal@uniminuto.edu.co',
            password='Password123*',
            documento='11223344',
            nombres='Portal',
            apellidos='Tester',
            rol=self.rol_estudiante
        )

    def test_login_page_renders(self):
        """La página de inicio de sesión carga correctamente."""
        response = self.client.get(reverse('usuarios:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Iniciar Sesión')
        self.assertContains(response, 'Acceso Seguro')
        self.assertContains(response, 'credenciales institucionales')

    def test_login_valid_credentials(self):
        """Inicio de sesión exitoso con credenciales correctas registra auditoría."""
        response = self.client.post(reverse('usuarios:login'), {
            'username': 'user_portal',
            'password': 'Password123*',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        # Verificar que el usuario quedó autenticado
        self.assertTrue(response.context['user'].is_authenticated)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.usuario,
            accion='INICIAR_SESION',
            modulo='USUARIOS'
        ).first()
        self.assertIsNotNone(auditoria)
        self.assertIn('user_portal', auditoria.registro_afectado)

    def test_login_invalid_credentials(self):
        """Inicio de sesión fallido muestra error y no autentica."""
        response = self.client.post(reverse('usuarios:login'), {
            'username': 'user_portal',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nombre de usuario o contraseña incorrectos')

    def test_logout_view(self):
        """Cierre de sesión desautentica al usuario y registra auditoría."""
        self.client.login(username='user_portal', password='Password123*')
        response = self.client.get(reverse('usuarios:logout'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(
            usuario=self.usuario,
            accion='CERRAR_SESION',
            modulo='USUARIOS'
        ).first()
        self.assertIsNotNone(auditoria)

    # --------------------------------------------------------------------------
    # PRUEBAS DE RECUPERACIÓN DE CONTRASEÑA (RF-02)
    # --------------------------------------------------------------------------

    def test_password_reset_formulario_renders(self):
        """(RF-02) La vista de solicitud de restablecimiento carga con diseño institucional."""
        response = self.client.get(reverse('usuarios:password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recuperar Contraseña')
        self.assertContains(response, 'Correo Electrónico Institucional')

    def test_password_reset_solicitud_envia_correo_y_audita(self):
        """(RF-02) La solicitud para un correo existente despacha correo con token y registra auditoría."""
        response = self.client.post(reverse('usuarios:password_reset'), {
            'email': 'user_portal@uniminuto.edu.co',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Instrucciones Enviadas')

        # Verificar envío de correo
        self.assertEqual(len(mail.outbox), 1)
        correo_enviado = mail.outbox[0]
        self.assertIn('Restablecimiento de contraseña', correo_enviado.subject)
        self.assertIn('user_portal@uniminuto.edu.co', correo_enviado.to)
        self.assertIn('/usuarios/reset/', correo_enviado.body)

        # Verificar auditoría
        auditoria = Auditoria.objects.filter(accion='SOLICITAR_RECUPERACION_PASSWORD').first()
        self.assertIsNotNone(auditoria)
        self.assertEqual(auditoria.modulo, 'USUARIOS')

    def test_password_reset_correo_inexistente_no_revela_existencia(self):
        """(RF-02) Un correo inexistente muestra la misma confirmación sin revelar si existe (Anti-Enumeration)."""
        response = self.client.post(reverse('usuarios:password_reset'), {
            'email': 'inexistente@noexiste.com',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Instrucciones Enviadas')
        # No se envía ningún correo
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_cambio_efectivo(self):
        """(RF-02) El enlace firmado permite establecer una nueva contraseña y registrar auditoría."""
        uid = urlsafe_base64_encode(force_bytes(self.usuario.pk))
        token = default_token_generator.make_token(self.usuario)

        # 1. Cargar formulario de confirmación con token válido (sigue redirect a set-password)
        url_confirm = reverse('usuarios:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        resp_get = self.client.get(url_confirm, follow=True)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'Nueva Contraseña')

        # 2. Enviar nueva contraseña válida a la URL de set-password
        set_password_url = reverse('usuarios:password_reset_confirm', kwargs={'uidb64': uid, 'token': 'set-password'})
        resp_post = self.client.post(set_password_url, {
            'new_password1': 'NuevoPassword2026*',
            'new_password2': 'NuevoPassword2026*',
        }, follow=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertContains(resp_post, 'Contraseña Restablecida')

        # 3. Comprobar que el usuario puede autenticarse con su nueva contraseña
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password('NuevoPassword2026*'))

        # 4. Verificar auditoría de cambio efectivo
        auditoria = Auditoria.objects.filter(
            usuario=self.usuario,
            accion='CAMBIO_PASSWORD_RECUPERACION'
        ).first()
        self.assertIsNotNone(auditoria)


class RolesYPermisosDocenteTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_comando_inicializar_roles_idempotente(self):
        """El comando inicializar_roles crea los 4 roles canónicos y puede ejecutarse repetidamente sin duplicados."""
        from django.core.management import call_command
        import io

        out = io.StringIO()
        call_command('inicializar_roles', stdout=out)
        salida = out.getvalue()

        self.assertIn('Administrador', salida)
        self.assertIn('Coordinador', salida)
        self.assertIn('Docente', salida)
        self.assertIn('Estudiante', salida)

        roles_esperados = ['Administrador', 'Coordinador', 'Docente', 'Estudiante']
        for nombre in roles_esperados:
            self.assertTrue(Rol.objects.filter(nombre=nombre).exists())

        conteo_inicial = Rol.objects.count()
        self.assertEqual(conteo_inicial, 4)

        # Segunda ejecución para certificar idempotencia
        out2 = io.StringIO()
        call_command('inicializar_roles', stdout=out2)
        salida2 = out2.getvalue()
        self.assertIn('0 creados, 4 conservados', salida2)
        self.assertEqual(Rol.objects.count(), 4)

    def test_permisos_efectivos_usuario_docente(self):
        """Un usuario con rol Docente puede gestionar eventos pero NO tiene privilegios de Administrador ni acceso a auditoría."""
        from django.core.management import call_command
        from eventos.views import es_usuario_gestion
        from eventos.models import Evento, CategoriaEvento, ModalidadEvento, EstadoEvento

        call_command('inicializar_roles')
        rol_docente = Rol.objects.get(nombre='Docente')

        docente = Usuario.objects.create_user(
            username='profesor_test',
            email='profesor_test@uniminuto.edu.co',
            password='DocentePass123*',
            documento='70707070',
            nombres='Profesor',
            apellidos='Titular',
            rol=rol_docente
        )

        # 1. No es staff ni superusuario
        self.assertFalse(docente.is_staff)
        self.assertFalse(docente.is_superuser)

        # 2. Tiene facultad de usuario de gestión
        self.assertTrue(es_usuario_gestion(docente))

        # 3. Puede crear eventos institucionales
        self.client.login(username='profesor_test', password='DocentePass123*')
        cat = CategoriaEvento.objects.create(nombre='Académica')
        resp_crear = self.client.post(reverse('eventos:crear'), {
            'nombre': 'Seminario de Investigación Docente',
            'descripcion': 'Evento académico.',
            'fecha': '2026-11-20',
            'hora_inicio': '09:00',
            'hora_fin': '11:00',
            'lugar': 'Aula 101',
            'modalidad': ModalidadEvento.PRESENCIAL,
            'cupo': 50,
            'estado': EstadoEvento.PUBLICADO,
            'categoria': cat.pk
        }, follow=True)
        self.assertEqual(resp_crear.status_code, 200)
        evento_creado = Evento.objects.filter(nombre='Seminario de Investigación Docente').first()
        self.assertIsNotNone(evento_creado)
        self.assertEqual(evento_creado.organizador, docente)

        # 4. NO tiene acceso a auditoría institucional (exclusivo para Administrador)
        resp_auditoria = self.client.get(reverse('auditoria:consulta_auditoria'))
        self.assertEqual(resp_auditoria.status_code, 403)


class CrearSuperusuarioInicialCommandTests(TestCase):
    """
    Pruebas automatizadas de seguridad e idempotencia para el comando
    crear_superusuario_inicial (FASE 3.1).
    """
    def setUp(self):
        # Asegurar un entorno limpio sin variables residuales
        self.env_vars = [
            'DJANGO_SUPERUSER_PASSWORD',
            'DJANGO_SUPERUSER_USERNAME',
            'DJANGO_SUPERUSER_EMAIL',
            'DJANGO_SUPERUSER_DOCUMENTO',
            'DJANGO_SUPERUSER_NOMBRES',
            'DJANGO_SUPERUSER_APELLIDOS'
        ]
        for var in self.env_vars:
            os.environ.pop(var, None)

    def tearDown(self):
        for var in self.env_vars:
            os.environ.pop(var, None)

    def test_crear_superusuario_exitoso_noinput(self):
        """1. Caso A: Crea correctamente el superusuario cuando no existe en modo --noinput."""
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        os.environ['DJANGO_SUPERUSER_PASSWORD'] = 'ClaveSeguraSuper2026*'
        call_command(
            'crear_superusuario_inicial',
            username='admin.despliegue',
            email='admin.despliegue@uniminuto.edu.co',
            documento='99001122',
            nombres='Admin',
            apellidos='Render',
            noinput=True,
            stdout=out
        )

        usuario = Usuario.objects.filter(username='admin.despliegue').first()
        self.assertIsNotNone(usuario)
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.is_active)
        self.assertEqual(usuario.rol.nombre, 'Administrador')
        self.assertEqual(usuario.email, 'admin.despliegue@uniminuto.edu.co')
        self.assertEqual(usuario.documento, '99001122')
        self.assertEqual(usuario.nombres, 'Admin')
        self.assertEqual(usuario.apellidos, 'Render')
        self.assertTrue(usuario.check_password('ClaveSeguraSuper2026*'))
        self.assertIn('[ÉXITO]', out.getvalue())

    def test_usuario_existente_no_es_modificado(self):
        """2. Caso B: Verifica que ningún atributo, contraseña ni permiso cambie cuando el usuario ya existe."""
        from io import StringIO
        from django.core.management import call_command

        rol_admin, _ = Rol.objects.get_or_create(
            nombre='Administrador',
            defaults={'descripcion': 'Rol admin', 'activo': True}
        )
        usuario_original = Usuario.objects.create_superuser(
            username='admin.existente',
            email='admin.existente@uniminuto.edu.co',
            password='PasswordOriginal2026*',
            documento='88776655',
            nombres='Original',
            apellidos='Usuario',
            rol=rol_admin,
            is_active=True,
            is_staff=True,
            is_superuser=True
        )

        # Captura de atributos originales antes de ejecutar el comando
        orig_username = usuario_original.username
        orig_email = usuario_original.email
        orig_documento = usuario_original.documento
        orig_nombres = usuario_original.nombres
        orig_apellidos = usuario_original.apellidos
        orig_is_active = usuario_original.is_active
        orig_is_staff = usuario_original.is_staff
        orig_is_superuser = usuario_original.is_superuser
        orig_rol_id = usuario_original.rol_id
        orig_password_hash = usuario_original.password

        out = StringIO()
        os.environ['DJANGO_SUPERUSER_PASSWORD'] = 'NuevaClaveDiferente2026*'
        call_command(
            'crear_superusuario_inicial',
            username='admin.existente',
            email='intento.modificar@uniminuto.edu.co',
            documento='00112233',
            nombres='NombreModificado',
            apellidos='ApellidoModificado',
            noinput=True,
            stdout=out
        )

        # Salida informativa requerida (no error)
        salida = out.getvalue()
        self.assertIn('[AVISO]', salida)
        self.assertIn("El usuario 'admin.existente' ya existe en el sistema. No se realizaron modificaciones.", salida)

        # Recargar y comparar exhaustivamente atributos anteriores y posteriores
        usuario_original.refresh_from_db()
        self.assertEqual(usuario_original.username, orig_username)
        self.assertEqual(usuario_original.email, orig_email)
        self.assertEqual(usuario_original.documento, orig_documento)
        self.assertEqual(usuario_original.nombres, orig_nombres)
        self.assertEqual(usuario_original.apellidos, orig_apellidos)
        self.assertEqual(usuario_original.is_active, orig_is_active)
        self.assertEqual(usuario_original.is_staff, orig_is_staff)
        self.assertEqual(usuario_original.is_superuser, orig_is_superuser)
        self.assertEqual(usuario_original.rol_id, orig_rol_id)
        self.assertEqual(usuario_original.password, orig_password_hash)

        # Verificación estricta de contraseña vía check_password
        self.assertTrue(usuario_original.check_password('PasswordOriginal2026*'))
        self.assertFalse(usuario_original.check_password('NuevaClaveDiferente2026*'))

    def test_falta_password_en_modo_noinput(self):
        """3. Caso C: Verifica que el comando falle con CommandError cuando falta la contraseña en modo --noinput."""
        from django.core.management import call_command, CommandError

        # Subcaso 3a: Variable de entorno no definida
        os.environ.pop('DJANGO_SUPERUSER_PASSWORD', None)
        with self.assertRaises(CommandError) as ctx1:
            call_command(
                'crear_superusuario_inicial',
                username='admin.sinpass1',
                email='admin.sinpass1@uniminuto.edu.co',
                noinput=True
            )
        self.assertIn('DJANGO_SUPERUSER_PASSWORD', str(ctx1.exception))

        # Subcaso 3b: Variable de entorno vacía o sólo espacios
        os.environ['DJANGO_SUPERUSER_PASSWORD'] = '   '
        with self.assertRaises(CommandError) as ctx2:
            call_command(
                'crear_superusuario_inicial',
                username='admin.sinpass2',
                email='admin.sinpass2@uniminuto.edu.co',
                noinput=True
            )
        self.assertIn('DJANGO_SUPERUSER_PASSWORD', str(ctx2.exception))

        # Asegurar que ningún usuario fue creado
        self.assertFalse(Usuario.objects.filter(username__in=['admin.sinpass1', 'admin.sinpass2']).exists())

    def test_crear_superusuario_interactivo(self):
        """4. Caso A interactivo: Verifica el flujo interactivo utilizando getpass y validación de contraseña."""
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command

        out = StringIO()
        # Mock de input() para username, email y documento; getpass() para password y confirmación
        with patch('builtins.input', side_effect=['admin.interactivo', 'admin.interactivo@uniminuto.edu.co', '44556677']), \
             patch('getpass.getpass', side_effect=['ClaveSeguraInteractivo2026*', 'ClaveSeguraInteractivo2026*']):
            call_command('crear_superusuario_inicial', stdout=out)

        usuario = Usuario.objects.filter(username='admin.interactivo').first()
        self.assertIsNotNone(usuario)
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.is_active)
        self.assertEqual(usuario.rol.nombre, 'Administrador')
        self.assertEqual(usuario.email, 'admin.interactivo@uniminuto.edu.co')
        self.assertEqual(usuario.documento, '44556677')
        self.assertTrue(usuario.check_password('ClaveSeguraInteractivo2026*'))
        self.assertIn('[ÉXITO]', out.getvalue())

    def test_usuario_existente_con_rol_diferente_no_es_modificado(self):
        """5. Caso B (rol diferente): Comprueba que tampoco se altere el rol institucional ni permisos."""
        from io import StringIO
        from django.core.management import call_command

        rol_docente, _ = Rol.objects.get_or_create(
            nombre='Docente',
            defaults={'descripcion': 'Rol docente', 'activo': True}
        )
        usuario_docente = Usuario.objects.create_user(
            username='docente.especial',
            email='docente.especial@uniminuto.edu.co',
            password='ClaveDocenteSegura2026*',
            documento='55443322',
            nombres='Docente',
            apellidos='Titular',
            rol=rol_docente,
            is_active=True
        )

        # Captura de valores originales
        orig_rol_id = usuario_docente.rol_id
        orig_rol_nombre = usuario_docente.rol.nombre
        orig_is_staff = usuario_docente.is_staff
        orig_is_superuser = usuario_docente.is_superuser
        orig_is_active = usuario_docente.is_active
        orig_password_hash = usuario_docente.password
        orig_email = usuario_docente.email
        orig_documento = usuario_docente.documento
        orig_nombres = usuario_docente.nombres
        orig_apellidos = usuario_docente.apellidos

        out = StringIO()
        os.environ['DJANGO_SUPERUSER_PASSWORD'] = 'ClaveInvasoraSuper2026*'
        call_command(
            'crear_superusuario_inicial',
            username='docente.especial',
            email='intento.cambio@uniminuto.edu.co',
            documento='99990000',
            noinput=True,
            stdout=out
        )

        # Salida informativa
        salida = out.getvalue()
        self.assertIn('[AVISO]', salida)
        self.assertIn("El usuario 'docente.especial' ya existe en el sistema. No se realizaron modificaciones.", salida)

        # Recargar y comparar
        usuario_docente.refresh_from_db()
        self.assertEqual(usuario_docente.rol_id, orig_rol_id)
        self.assertEqual(usuario_docente.rol.nombre, orig_rol_nombre)
        self.assertEqual(usuario_docente.rol.nombre, 'Docente')
        self.assertNotEqual(usuario_docente.rol.nombre, 'Administrador')
        self.assertFalse(usuario_docente.is_staff)
        self.assertFalse(usuario_docente.is_superuser)
        self.assertTrue(usuario_docente.is_active)
        self.assertEqual(usuario_docente.password, orig_password_hash)
        self.assertEqual(usuario_docente.email, orig_email)
        self.assertEqual(usuario_docente.documento, orig_documento)
        self.assertEqual(usuario_docente.nombres, orig_nombres)
        self.assertEqual(usuario_docente.apellidos, orig_apellidos)

        # Contraseña intacta
        self.assertTrue(usuario_docente.check_password('ClaveDocenteSegura2026*'))
        self.assertFalse(usuario_docente.check_password('ClaveInvasoraSuper2026*'))


class UsuariosRegistroTests(TestCase):
    """
    Pruebas para el registro de nuevos usuarios en el sistema SIGAE.
    """
    def setUp(self):
        self.client = Client()
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')

    def test_registro_page_renders(self):
        """La página de registro institucional carga correctamente."""
        response = self.client.get(reverse('usuarios:registro'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear Cuenta de Usuario')
        self.assertContains(response, 'Registro Institucional')

    def test_registro_usuario_valido(self):
        """Registro exitoso crea usuario con rol Estudiante, contraseña cifrada y audita la acción."""
        response = self.client.post(reverse('usuarios:registro'), {
            'username': 'nuevo_estudiante',
            'documento': '1234567890',
            'nombres': 'Carlos',
            'apellidos': 'Giraldo',
            'email': 'carlos.giraldo@uniminuto.edu.co',
            'telefono': '3009876543',
            'password': 'PasswordSegura2026*',
            'confirm_password': 'PasswordSegura2026*',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)

        user = Usuario.objects.filter(username='nuevo_estudiante').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'carlos.giraldo@uniminuto.edu.co')
        self.assertEqual(user.rol.nombre, 'Estudiante')
        self.assertTrue(user.check_password('PasswordSegura2026*'))

        # Auditoría
        self.assertTrue(Auditoria.objects.filter(usuario=user, accion='REGISTRO_USUARIO').exists())

    def test_registro_contrasenas_no_coinciden(self):
        """Error al intentar registrar con contraseñas no coincidentes."""
        response = self.client.post(reverse('usuarios:registro'), {
            'username': 'error_password',
            'documento': '1234567891',
            'nombres': 'Error',
            'apellidos': 'Clave',
            'email': 'error.clave@uniminuto.edu.co',
            'password': 'PasswordSegura2026*',
            'confirm_password': 'OtraPasswordDiferente*',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Las contraseñas no coinciden')
        self.assertFalse(Usuario.objects.filter(username='error_password').exists())

    def test_registro_correo_duplicado(self):
        """Error si el correo electrónico ya se encuentra registrado."""
        Usuario.objects.create_user(
            username='existente_email',
            email='correo.duplicado@uniminuto.edu.co',
            password='Password123*',
            documento='11112222',
            rol=self.rol_estudiante
        )
        response = self.client.post(reverse('usuarios:registro'), {
            'username': 'otro_user',
            'documento': '33334444',
            'nombres': 'Otro',
            'apellidos': 'Usuario',
            'email': 'correo.duplicado@uniminuto.edu.co',
            'password': 'PasswordSegura2026*',
            'confirm_password': 'PasswordSegura2026*',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya existe un usuario registrado con este correo')
        self.assertFalse(Usuario.objects.filter(username='otro_user').exists())


class VerificacionCorreoTests(TestCase):
    """
    Pruebas para el mecanismo de verificación de correo electrónico (Etapa 7.2.1.1):
    - Token de un solo uso con hash SHA-256.
    - Expiración de 24 horas.
    - Reinicio de verificación al modificar el correo en el perfil.
    - Registro de nuevos usuarios con email_verificado=False.
    - Vistas de solicitud y confirmación de verificación.
    """
    def setUp(self):
        self.client = Client()
        self.rol_estudiante = Rol.objects.create(nombre='Estudiante')
        self.usuario = Usuario.objects.create_user(
            username='user_verificar',
            email='verificar@uniminuto.edu.co',
            password='Password123*',
            documento='44556677',
            nombres='Verificar',
            apellidos='Usuario',
            rol=self.rol_estudiante,
            email_verificado=False
        )
        mail.outbox.clear()

    def test_crear_token_almacena_hash_sha256(self):
        """El token generado se almacena como SHA-256 y nunca en texto claro."""
        token_obj, raw_token = TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        self.assertIsNotNone(token_obj)
        self.assertNotEqual(token_obj.token_hash, raw_token)
        esperado_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        self.assertEqual(token_obj.token_hash, esperado_hash)
        self.assertFalse(token_obj.usado)
        self.assertFalse(token_obj.ha_expirado)

    def test_verificar_token_exitoso(self):
        """Verificación exitosa activa email_verificado y consume el token."""
        token_obj, raw_token = TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        valido, user, msg = TokenVerificacionCorreo.verificar_token(raw_token)
        self.assertTrue(valido)
        self.assertEqual(user, self.usuario)

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.email_verificado)

        token_obj.refresh_from_db()
        self.assertTrue(token_obj.usado)

    def test_token_expirado_es_rechazado(self):
        """Token con más de 24 horas es rechazado y no verifica la cuenta."""
        token_obj, raw_token = TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        token_obj.fecha_expiracion = timezone.now() - datetime.timedelta(hours=2)
        token_obj.save()

        valido, user, msg = TokenVerificacionCorreo.verificar_token(raw_token)
        self.assertFalse(valido)

        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.email_verificado)

    def test_token_un_solo_uso(self):
        """Un token no puede reutilizarse una vez consumido."""
        token_obj, raw_token = TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        primera_vez, _, _ = TokenVerificacionCorreo.verificar_token(raw_token)
        self.assertTrue(primera_vez)

        # Segundo intento con el mismo token
        segunda_vez, _, _ = TokenVerificacionCorreo.verificar_token(raw_token)
        self.assertFalse(segunda_vez)

    def test_token_falso_o_manipulado_es_rechazado(self):
        """Un token inexistente o alterado es rechazado."""
        TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        valido, _, _ = TokenVerificacionCorreo.verificar_token('token_completamente_falso_12345')
        self.assertFalse(valido)

    def test_cambio_email_en_perfil_reinicia_verificacion(self):
        """Si un usuario verificado cambia su correo en el perfil, email_verificado vuelve a False."""
        from usuarios.forms import PerfilUsuarioForm
        self.usuario.email_verificado = True
        self.usuario.save()

        # Cambiar el correo
        form = PerfilUsuarioForm(
            data={
                'nombres': self.usuario.nombres,
                'apellidos': self.usuario.apellidos,
                'email': 'nuevo_correo_cambiado@uniminuto.edu.co',
                'telefono': '3001234567',
            },
            instance=self.usuario
        )
        self.assertTrue(form.is_valid())
        user_actualizado = form.save()
        self.assertFalse(user_actualizado.email_verificado)

    def test_mismo_email_en_perfil_preserva_verificacion(self):
        """Si el usuario actualiza otros datos sin cambiar su correo, mantiene email_verificado=True."""
        from usuarios.forms import PerfilUsuarioForm
        self.usuario.email_verificado = True
        self.usuario.save()

        form = PerfilUsuarioForm(
            data={
                'nombres': 'Nombre Editado',
                'apellidos': self.usuario.apellidos,
                'email': self.usuario.email,
                'telefono': '3009998877',
            },
            instance=self.usuario
        )
        self.assertTrue(form.is_valid())
        user_actualizado = form.save()
        self.assertTrue(user_actualizado.email_verificado)

    def test_nuevo_usuario_registro_inicializa_no_verificado(self):
        """Un usuario nuevo registrado inicia con email_verificado=False y recibe correo."""
        response = self.client.post(reverse('usuarios:registro'), {
            'username': 'nuevo_no_verificado',
            'documento': '98765432',
            'nombres': 'Nuevo',
            'apellidos': 'NoVerif',
            'email': 'nuevo.noverif@uniminuto.edu.co',
            'password': 'PasswordSegura2026*',
            'confirm_password': 'PasswordSegura2026*',
        })
        user = Usuario.objects.get(username='nuevo_no_verificado')
        self.assertFalse(user.email_verificado)
        # Se envía correo de bienvenida y verificación
        self.assertTrue(len(mail.outbox) >= 1)

    def test_vistas_solicitar_y_verificar_correo(self):
        """Flujo web: Solicitar verificación -> Despacha correo -> Acceder con token verifica la cuenta."""
        self.client.force_login(self.usuario)
        url_solicitar = reverse('usuarios:solicitar_verificacion')
        resp_solicitar = self.client.post(url_solicitar, follow=True)
        self.assertEqual(resp_solicitar.status_code, 200)
        self.assertContains(resp_solicitar, 'enlace de verificación')

        # Debe haberse enviado el correo
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertIn('verificar-correo', correo.body)

        # Extraer token creado
        token_obj = self.usuario.tokens_verificacion_correo.filter(usado=False).first()
        self.assertIsNotNone(token_obj)

        # Generar un token de prueba para verificar vía GET
        _, raw_token = TokenVerificacionCorreo.crear_para_usuario(self.usuario)
        url_verificar = reverse('usuarios:verificar_correo', kwargs={'token': raw_token})
        resp_verificar = self.client.get(url_verificar, follow=True)
        self.assertEqual(resp_verificar.status_code, 200)
        self.assertContains(resp_verificar, 'verificado exitosamente')

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.email_verificado)




