"""
Comando de gestión de Django para la creación segura e idempotente del superusuario
inicial en EventosSIGAE-UNIMINUTO.

Resuelve la restricción del modelo Usuario institucional, el cual exige una llave
foránea obligatoria no nula al modelo Rol ('Administrador').

Medidas de Seguridad y Reglas de Negocio (FASE 3.1):
- Caso A (Usuario inexistente):
  * Crea el superusuario con rol canónico 'Administrador'.
  * Establece is_active=True, is_staff=True, is_superuser=True.
  * Exige contraseña segura conforme a las políticas de AUTH_PASSWORD_VALIDATORS.
  * En modo interactivo utiliza getpass con confirmación y validación.
  * En modo --noinput obtiene la contraseña exclusivamente desde DJANGO_SUPERUSER_PASSWORD.
- Caso B (Usuario ya existente):
  * No modifica absolutamente ningún atributo (contraseña, correo, permisos, rol, estado).
  * Muestra mensaje informativo indicando que el usuario ya existe y no se realizaron cambios.
  * Finaliza de forma limpia sin generar errores ni excepciones.
- Caso C (Falta de contraseña):
  * En modo interactivo la solicita de manera segura.
  * En modo --noinput aborta de inmediato mediante CommandError.
  * Nunca crea usuarios con contraseñas vacías, nulas o predeterminadas.
- Confidencialidad:
  * Nunca expone contraseñas en consola, historial de shell, bitácora de auditoría ni logs.
"""

import os
import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from usuarios.models import Usuario, Rol


class Command(BaseCommand):
    help = 'Crea de forma segura e idempotente un superusuario inicial con rol institucional Administrador.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Nombre de usuario para el superusuario (ej. admin.institucional).'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Correo electrónico institucional (ej. admin@uniminuto.edu.co).'
        )
        parser.add_argument(
            '--documento',
            type=str,
            help='Documento de identidad institucional (ej. 00000001).'
        )
        parser.add_argument(
            '--nombres',
            type=str,
            default='Administrador',
            help='Nombres del usuario (por defecto: Administrador).'
        )
        parser.add_argument(
            '--apellidos',
            type=str,
            default='SIGAE UNIMINUTO',
            help='Apellidos del usuario (por defecto: SIGAE UNIMINUTO).'
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_true',
            help='Modo no interactivo. Requiere DJANGO_SUPERUSER_PASSWORD en variables de entorno.'
        )

    def handle(self, *args, **options):
        no_input = options.get('noinput', False)

        # 1. Obtener o solicitar nombre de usuario
        username = options.get('username') or os.environ.get('DJANGO_SUPERUSER_USERNAME')
        if not username:
            if no_input:
                raise CommandError("En modo --noinput debe especificarse --username o la variable DJANGO_SUPERUSER_USERNAME.")
            try:
                username = input("Nombre de usuario (ej. admin.institucional): ").strip()
            except (EOFError, KeyboardInterrupt):
                raise CommandError("Operación interactiva cancelada por el usuario.")
            if not username:
                raise CommandError("El nombre de usuario no puede estar vacío.")

        # 2. Verificar existencia previa por username (Caso B: no modificar nada)
        if Usuario.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(
                f"[AVISO] El usuario '{username}' ya existe en el sistema. No se realizaron modificaciones."
            ))
            return

        # 3. Obtener o solicitar correo electrónico
        email = options.get('email') or os.environ.get('DJANGO_SUPERUSER_EMAIL')
        if not email:
            if no_input:
                raise CommandError("En modo --noinput debe especificarse --email o la variable DJANGO_SUPERUSER_EMAIL.")
            try:
                email = input("Correo electrónico (ej. admin@uniminuto.edu.co): ").strip()
            except (EOFError, KeyboardInterrupt):
                raise CommandError("Operación interactiva cancelada por el usuario.")
            if not email:
                raise CommandError("El correo electrónico no puede estar vacío.")

        if Usuario.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(
                f"[AVISO] Ya existe un usuario registrado con el correo '{email}'. No se realizaron modificaciones."
            ))
            return

        # 4. Obtener o solicitar documento de identidad
        documento = options.get('documento') or os.environ.get('DJANGO_SUPERUSER_DOCUMENTO')
        if not documento:
            if no_input:
                documento = '00000001'
            else:
                try:
                    doc_in = input("Documento de identidad [00000001]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    raise CommandError("Operación interactiva cancelada por el usuario.")
                documento = doc_in if doc_in else '00000001'

        if Usuario.objects.filter(documento=documento).exists():
            self.stdout.write(self.style.WARNING(
                f"[AVISO] Ya existe un usuario registrado con el documento '{documento}'. No se realizaron modificaciones."
            ))
            return

        nombres = options.get('nombres') or os.environ.get('DJANGO_SUPERUSER_NOMBRES', 'Administrador')
        apellidos = options.get('apellidos') or os.environ.get('DJANGO_SUPERUSER_APELLIDOS', 'SIGAE UNIMINUTO')

        # 5. Obtener o solicitar contraseña de forma segura (Caso A / C)
        password = None
        if no_input:
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
            if not password or not password.strip():
                raise CommandError(
                    "En modo --noinput es obligatorio definir la variable de entorno DJANGO_SUPERUSER_PASSWORD."
                )
            try:
                validate_password(password)
            except ValidationError as e:
                raise CommandError(f"Contraseña insegura según políticas: {'; '.join(e.messages)}")
        else:
            while not password:
                try:
                    p1 = getpass.getpass("Contraseña: ")
                except (EOFError, KeyboardInterrupt):
                    raise CommandError("Operación interactiva cancelada por el usuario.")
                if not p1 or not p1.strip():
                    self.stdout.write(self.style.ERROR("La contraseña no puede estar vacía."))
                    continue
                try:
                    p2 = getpass.getpass("Confirmar contraseña: ")
                except (EOFError, KeyboardInterrupt):
                    raise CommandError("Operación interactiva cancelada por el usuario.")
                if p1 != p2:
                    self.stdout.write(self.style.ERROR("Las contraseñas no coinciden. Inténtelo nuevamente."))
                    continue
                try:
                    validate_password(p1)
                    password = p1
                except ValidationError as e:
                    for msg in e.messages:
                        self.stdout.write(self.style.ERROR(f" - {msg}"))

        # 6. Garantizar existencia del rol institucional Administrador
        rol_admin, created = Rol.objects.get_or_create(
            nombre='Administrador',
            defaults={
                'descripcion': 'Administrador general del sistema con acceso a gestión institucional y auditoría.',
                'activo': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(" [+] Rol canónico 'Administrador' creado en base de datos."))

        # 7. Crear el superusuario institucional (Caso A)
        try:
            usuario = Usuario.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                documento=documento,
                nombres=nombres,
                apellidos=apellidos,
                rol=rol_admin,
                is_active=True,
                is_staff=True,
                is_superuser=True
            )
            self.stdout.write(self.style.SUCCESS(
                f"[ÉXITO] Superusuario '{usuario.username}' creado satisfactoriamente con rol '{rol_admin.nombre}'."
            ))
        except Exception as exc:
            raise CommandError(f"Error inesperado al crear el superusuario: {exc}")
