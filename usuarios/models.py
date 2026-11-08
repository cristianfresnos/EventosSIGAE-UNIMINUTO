import datetime
import hashlib
import secrets
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class Rol(models.Model):
    """
    Modelo para la gestión de roles en el sistema EventosSIGAE-UNIMINUTO.
    """
    id_rol = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    """
    Modelo de usuario para EventosSIGAE-UNIMINUTO, extendiendo AbstractUser de Django.
    Mantiene las funcionalidades nativas de autenticación, contraseñas, sesiones y permisos,
    utilizando nombres, apellidos y correo como datos principales.
    """
    # Desactivar first_name y last_name para evitar duplicidad con nombres y apellidos
    first_name = None
    last_name = None

    # Datos principales del usuario
    documento = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Documento de identidad'
    )
    nombres = models.CharField(
        max_length=100,
        verbose_name='Nombres'
    )
    apellidos = models.CharField(
        max_length=100,
        verbose_name='Apellidos'
    )
    email = models.EmailField(
        unique=True,
        verbose_name='Correo electrónico',
        error_messages={
            'unique': 'Ya existe un usuario registrado con este correo electrónico.'
        }
    )
    email_verificado = models.BooleanField(
        default=False,
        verbose_name='Correo electrónico verificado',
        help_text='Indica si el usuario ha demostrado el control de su correo institucional.'
    )

    # Datos de contacto y vinculación
    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono'
    )
    tipo_vinculacion = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name='Tipo de vinculación'
    )

    # Estado y rol institucional
    estado = models.BooleanField(
        default=True,
        verbose_name='Estado'
    )
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        related_name='usuarios',
        verbose_name='Rol'
    )

    # Auditoría de fechas
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Fecha de actualización'
    )

    REQUIRED_FIELDS = ['nombres', 'apellidos', 'documento', 'email']

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        nombre_completo = self.get_full_name()
        return nombre_completo if nombre_completo else self.username

    def get_full_name(self):
        full_name = f"{self.nombres} {self.apellidos}".strip()
        return full_name if full_name else self.username

    def get_short_name(self):
        return self.nombres if self.nombres else self.username

    @property
    def correo(self):
        return self.email

    @correo.setter
    def correo(self, value):
        self.email = value


class TokenVerificacionCorreo(models.Model):
    """
    Token criptográfico de un solo uso para verificar el control de una dirección de correo institucional.
    """
    id_token = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        'Usuario',
        on_delete=models.CASCADE,
        related_name='tokens_verificacion_correo',
        verbose_name='Usuario'
    )
    email = models.EmailField(
        verbose_name='Correo a verificar'
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Hash del token'
    )
    usado = models.BooleanField(
        default=False,
        verbose_name='Usado'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_expiracion = models.DateTimeField(
        verbose_name='Fecha de expiración'
    )

    class Meta:
        verbose_name = 'Token de verificación de correo'
        verbose_name_plural = 'Tokens de verificación de correo'
        ordering = ['-fecha_creacion']

    @property
    def ha_expirado(self):
        return timezone.now() > self.fecha_expiracion

    @classmethod
    def generar_token(cls):
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        return raw_token, token_hash

    @classmethod
    def crear_para_usuario(cls, usuario, horas_vigencia=24):
        """
        Crea un nuevo token de verificación para el correo actual del usuario
        e invalida tokens anteriores no usados para ese correo.
        """
        with transaction.atomic():
            cls.objects.filter(
                usuario=usuario,
                email__iexact=usuario.email.strip().lower(),
                usado=False
            ).update(usado=True)

            raw_token, token_hash = cls.generar_token()
            expiracion = timezone.now() + datetime.timedelta(hours=horas_vigencia)
            token_obj = cls.objects.create(
                usuario=usuario,
                email=usuario.email.strip().lower(),
                token_hash=token_hash,
                fecha_expiracion=expiracion
            )
            return token_obj, raw_token

    @classmethod
    def verificar_token(cls, raw_token):
        """
        Valida el token en tiempo constante. Si es válido y no ha expirado,
        marca el token como usado y el email del usuario como verificado.
        Retorna (exito, usuario, mensaje).
        """
        if not raw_token or len(raw_token.strip()) < 10:
            return False, None, "Token de verificación inválido."

        token_hash = hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()
        with transaction.atomic():
            token_obj = cls.objects.select_for_update().select_related('usuario').filter(
                token_hash=token_hash
            ).first()

            if not token_obj:
                return False, None, "Token de verificación no encontrado o ya utilizado."

            if token_obj.usado:
                return False, None, "Este token de verificación ya fue utilizado."

            if timezone.now() > token_obj.fecha_expiracion:
                token_obj.usado = True
                token_obj.save(update_fields=['usado'])
                return False, None, "El enlace de verificación ha expirado. Por favor solicita uno nuevo."

            user = token_obj.usuario
            if user.email.strip().lower() != token_obj.email.strip().lower():
                token_obj.usado = True
                token_obj.save(update_fields=['usado'])
                return False, None, "El correo de la cuenta no coincide con el token de verificación."

            token_obj.usado = True
            token_obj.save(update_fields=['usado'])

            user.email_verificado = True
            user.save(update_fields=['email_verificado'])

            return True, user, "Correo electrónico verificado exitosamente."


