import datetime
import hashlib
import hmac
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction, IntegrityError
from django.utils import timezone


class TipoParticipante(models.TextChoices):
    ESTUDIANTE = 'ESTUDIANTE', 'Estudiante'
    DOCENTE = 'DOCENTE', 'Docente'
    ADMINISTRATIVO = 'ADMINISTRATIVO', 'Administrativo'
    EGRESADO = 'EGRESADO', 'Egresado'
    EXTERNO = 'EXTERNO', 'Externo'
    OTRO = 'OTRO', 'Otro'


class Participante(models.Model):
    """
    Permite vincular usuarios registrados (ej. comunidad UNIMINUTO) o personas externas sin cuenta.
    """
    id_participante = models.AutoField(primary_key=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='perfil_participante',
        verbose_name='Usuario'
    )
    tipo = models.CharField(
        max_length=30,
        choices=TipoParticipante.choices,
        verbose_name='Tipo de participante'
    )
    documento = models.CharField(
        max_length=20,
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
    correo = models.EmailField(
        max_length=254,
        verbose_name='Correo electrónico'
    )
    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono'
    )
    programa = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Programa académico'
    )
    facultad = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Facultad'
    )
    institucion = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Institución de procedencia'
    )
    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de registro'
    )

    class Meta:
        verbose_name = 'Participante'
        verbose_name_plural = 'Participantes'
        ordering = ['apellidos', 'nombres']

    def __str__(self):
        return f"{self.nombres} {self.apellidos}".strip()


class EstadoInscripcion(models.TextChoices):
    ACTIVA = 'ACTIVA', 'Activa'
    CANCELADA = 'CANCELADA', 'Cancelada'


class Inscripcion(models.Model):
    """
    Modelo de relación N:M entre Evento y Participante.
    Representa el registro formal de un participante a un evento específico.
    """
    id_inscripcion = models.AutoField(primary_key=True)
    evento = models.ForeignKey(
        'eventos.Evento',
        on_delete=models.PROTECT,
        related_name='inscripciones',
        verbose_name='Evento'
    )
    participante = models.ForeignKey(
        Participante,
        on_delete=models.PROTECT,
        related_name='inscripciones',
        verbose_name='Participante'
    )
    fecha_inscripcion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de inscripción'
    )
    estado = models.CharField(
        max_length=30,
        choices=EstadoInscripcion.choices,
        default=EstadoInscripcion.ACTIVA,
        verbose_name='Estado'
    )

    class Meta:
        verbose_name = 'Inscripción'
        verbose_name_plural = 'Inscripciones'
        ordering = ['-fecha_inscripcion']
        constraints = [
            models.UniqueConstraint(
                fields=['evento', 'participante'],
                name='unique_evento_participante'
            )
        ]

    def __str__(self):
        return f"{self.participante} - {self.evento}"

    @property
    def asistio(self):
        """
        Determina si el participante cuenta con un registro de asistencia formal y válido.
        Considera exclusivamente el estado REGISTRADA de la entidad Asistencia.
        """
        try:
            asistencia = getattr(self, 'asistencia', None)
            if asistencia is not None:
                return asistencia.estado == 'REGISTRADA'
        except Exception:
            pass
        return False

    @property
    def asistencias(self):
        """
        Propiedad de compatibilidad temporal hacia atrás para consultas existentes.
        """
        from asistencia.models import Asistencia
        return Asistencia.objects.filter(inscripcion=self)


class EstadoInvitacion(models.TextChoices):
    PENDIENTE = 'PENDIENTE', 'Pendiente'
    ACEPTADA = 'ACEPTADA', 'Aceptada'
    RECHAZADA = 'RECHAZADA', 'Rechazada'
    EXPIRADA = 'EXPIRADA', 'Expirada'
    CANCELADA = 'CANCELADA', 'Cancelada'


class InvitacionEvento(models.Model):
    """
    Representa una invitación formal enviada por un organizador/docente
    para participar en un evento institucional.
    Regla: La invitación no genera una inscripción confirmada hasta que el invitado
    inicie sesión o cree su cuenta y acepte explícitamente.
    """
    id_invitacion = models.AutoField(primary_key=True)
    evento = models.ForeignKey(
        'eventos.Evento',
        on_delete=models.CASCADE,
        related_name='invitaciones',
        verbose_name='Evento'
    )
    correo = models.EmailField(
        max_length=254,
        verbose_name='Correo del invitado'
    )
    nombres = models.CharField(
        max_length=100,
        verbose_name='Nombres'
    )
    apellidos = models.CharField(
        max_length=100,
        verbose_name='Apellidos'
    )
    institucion = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Institución'
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Hash del token de invitación'
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoInvitacion.choices,
        default=EstadoInvitacion.PENDIENTE,
        verbose_name='Estado'
    )
    invitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='invitaciones_enviadas',
        verbose_name='Invitado por'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_expiracion = models.DateTimeField(
        verbose_name='Fecha de expiración'
    )
    fecha_aceptacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de aceptación'
    )
    fecha_respuesta = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de respuesta'
    )
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitaciones_canceladas',
        verbose_name='Cancelado por'
    )
    fecha_cancelacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de cancelación'
    )

    class Meta:
        verbose_name = 'Invitación a evento'
        verbose_name_plural = 'Invitaciones a eventos'
        ordering = ['-fecha_creacion']
        constraints = [
            models.UniqueConstraint(
                fields=['evento', 'correo'],
                condition=models.Q(estado='PENDIENTE'),
                name='unique_invitacion_pendiente_por_evento'
            )
        ]

    def __str__(self):
        return f"Invitación a {self.correo} para {self.evento.nombre} ({self.get_estado_display()})"

    def clean(self):
        super().clean()
        if self.correo:
            self.correo = self.correo.strip().lower()

    def save(self, *args, **kwargs):
        if self.correo:
            self.correo = self.correo.strip().lower()
        super().save(*args, **kwargs)

    @classmethod
    def generar_token(cls):
        """Genera un token seudoaleatorio seguro de 32 bytes URL-safe y su hash SHA-256."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        return raw_token, token_hash

    def verificar_token(self, raw_token):
        """Valida si el token en plano coincide con el hash almacenado usando tiempo constante."""
        if not raw_token:
            return False
        calculated = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        return hmac.compare_digest(self.token_hash, calculated)

    def renovar_token(self, dias_vigencia=3):
        """
        Invalida de inmediato el token previo generando uno nuevo y actualizando la fecha de expiración.
        Garantiza que el enlace anterior no siga siendo válido (el hash anterior se sobreescribe).
        Retorna el nuevo raw_token para el reenvío.
        """
        raw_token, nuevo_hash = self.generar_token()
        self.token_hash = nuevo_hash
        self.fecha_expiracion = timezone.now() + datetime.timedelta(days=dias_vigencia)
        self.estado = EstadoInvitacion.PENDIENTE
        self.save(update_fields=['token_hash', 'fecha_expiracion', 'estado'])
        return raw_token

    @classmethod
    def crear_o_renovar_invitacion(cls, evento, correo, nombres, apellidos, invitado_por, institucion=None, dias_vigencia=3):
        """
        Crea o renueva una invitación para un correo y evento específicos protegiendo contra concurrencia.
        Si ya existe una invitación PENDIENTE, renueva el token e invalida el enlace previo sin violar
        la restricción de unicidad ni generar duplicados.
        Retorna (instancia_invitacion, raw_token).
        """
        correo_limpio = correo.strip().lower()
        with transaction.atomic():
            inv_pendiente = cls.objects.select_for_update().filter(
                evento=evento,
                correo=correo_limpio,
                estado=EstadoInvitacion.PENDIENTE
            ).first()

            if inv_pendiente:
                raw_token = inv_pendiente.renovar_token(dias_vigencia=dias_vigencia)
                return inv_pendiente, raw_token

            raw_token, token_hash = cls.generar_token()
            expiracion = timezone.now() + datetime.timedelta(days=dias_vigencia)
            try:
                invitacion = cls.objects.create(
                    evento=evento,
                    correo=correo_limpio,
                    nombres=nombres.strip(),
                    apellidos=apellidos.strip(),
                    institucion=institucion.strip() if institucion else '',
                    token_hash=token_hash,
                    estado=EstadoInvitacion.PENDIENTE,
                    invitado_por=invitado_por,
                    fecha_expiracion=expiracion
                )
                return invitacion, raw_token
            except IntegrityError:
                # Si una solicitud concurrente creó la invitación en paralelo, recuperarla y renovar
                inv_concurrente = cls.objects.select_for_update().filter(
                    evento=evento,
                    correo=correo_limpio,
                    estado=EstadoInvitacion.PENDIENTE
                ).first()
                if inv_concurrente:
                    raw_token = inv_concurrente.renovar_token(dias_vigencia=dias_vigencia)
                    return inv_concurrente, raw_token
                raise

    @property
    def ha_expirado(self):
        """Determina si la fecha de expiración ha sido superada."""
        if self.fecha_expiracion and timezone.now() > self.fecha_expiracion:
            return True
        return False

    @property
    def puede_ser_aceptada(self):
        """
        Determina si la invitación está en condiciones de ser aceptada:
        debe encontrarse en estado PENDIENTE y no haber superado su fecha de expiración.
        """
        if self.estado != EstadoInvitacion.PENDIENTE:
            return False
        if self.ha_expirado:
            return False
        return True

    def marcar_como_aceptada(self):
        """
        Valida rigurosamente la vigencia y transición a estado ACEPTADA registrando marcas temporales.
        Impide que invitaciones canceladas, expiradas, rechazadas o ya respondidas sean aceptadas.
        """
        if not self.puede_ser_aceptada:
            if self.estado == EstadoInvitacion.CANCELADA:
                raise ValidationError("La invitación ha sido cancelada y no puede ser aceptada.")
            if self.ha_expirado:
                self.estado = EstadoInvitacion.EXPIRADA
                self.save(update_fields=['estado'])
                raise ValidationError("La invitación ha expirado y no puede ser aceptada.")
            raise ValidationError(f"La invitación en estado '{self.get_estado_display()}' no puede ser aceptada.")
        self.estado = EstadoInvitacion.ACEPTADA
        ahora = timezone.now()
        self.fecha_aceptacion = ahora
        self.fecha_respuesta = ahora
        self.save(update_fields=['estado', 'fecha_aceptacion', 'fecha_respuesta'])

    def marcar_como_rechazada(self):
        """
        Valida rigurosamente la vigencia y transición a estado RECHAZADA.
        Impide que invitaciones canceladas, expiradas o ya respondidas sean rechazadas posteriormente.
        """
        if self.estado == EstadoInvitacion.CANCELADA:
            raise ValidationError("La invitación ha sido cancelada y no puede ser rechazada.")
        if self.ha_expirado:
            self.estado = EstadoInvitacion.EXPIRADA
            self.save(update_fields=['estado'])
            raise ValidationError("La invitación ha expirado y no puede ser rechazada.")
        if self.estado != EstadoInvitacion.PENDIENTE:
            raise ValidationError(f"La invitación en estado '{self.get_estado_display()}' no puede ser rechazada.")
        self.estado = EstadoInvitacion.RECHAZADA
        self.fecha_respuesta = timezone.now()
        self.save(update_fields=['estado', 'fecha_respuesta'])

    def cancelar_invitacion(self, responsable=None):
        """
        Permite al organizador cancelar una invitación pendiente marcándola como CANCELADA.
        Invalida inmediatamente el token previo y registra fecha y usuario responsable.
        """
        if self.estado != EstadoInvitacion.PENDIENTE:
            raise ValidationError("Solo se pueden cancelar invitaciones en estado PENDIENTE.")
        self.estado = EstadoInvitacion.CANCELADA
        ahora = timezone.now()
        self.fecha_cancelacion = ahora
        self.fecha_respuesta = ahora
        if responsable:
            self.cancelado_por = responsable
        # Invalidar de inmediato el token previo para impedir uso del enlace anterior
        _, nuevo_hash = self.generar_token()
        self.token_hash = nuevo_hash
        self.save(update_fields=['estado', 'fecha_cancelacion', 'fecha_respuesta', 'cancelado_por', 'token_hash'])


class AccesoExternoInscripcion(models.Model):
    """
    Permite que un participante externo (sin cuenta institucional) acceda de forma
    personal, segura y persistente a su inscripción y funcionalidades del evento.
    El token se genera de forma aleatoria, se entrega exclusivamente por enlace seguro
    y en base de datos se guarda únicamente su hash SHA-256.
    """
    id_acceso = models.AutoField(primary_key=True)
    inscripcion = models.OneToOneField(
        Inscripcion,
        on_delete=models.CASCADE,
        related_name='acceso_externo',
        verbose_name='Inscripción asociada'
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Hash del token de acceso'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_expiracion = models.DateTimeField(
        verbose_name='Fecha de expiración'
    )
    revocado = models.BooleanField(
        default=False,
        verbose_name='Revocado'
    )
    fecha_revocacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de revocación'
    )
    ultimo_acceso = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Último acceso'
    )

    class Meta:
        verbose_name = 'Acceso externo a inscripción'
        verbose_name_plural = 'Accesos externos a inscripciones'
        ordering = ['-fecha_creacion']

    def __str__(self):
        estado_str = "Revocado" if self.revocado else ("Expirado" if not self.es_valido else "Válido")
        return f"Acceso externo #{self.id_acceso} - Inscripción #{self.inscripcion_id} ({estado_str})"

    def clean(self):
        super().clean()
        if self.inscripcion_id:
            try:
                inscripcion = self.inscripcion
            except Exception:
                from .models import Inscripcion
                inscripcion = Inscripcion.objects.select_related('participante').filter(pk=self.inscripcion_id).first()
            if inscripcion and hasattr(inscripcion, 'participante') and inscripcion.participante:
                if inscripcion.participante.usuario is not None:
                    raise ValidationError({
                        'inscripcion': 'El acceso externo solo puede asociarse a participantes sin cuenta de usuario institucional.'
                    })

    def save(self, *args, **kwargs):
        # Validación obligatoria en save() para evitar bypass si no se invoca full_clean()
        self.clean()
        super().save(*args, **kwargs)

    @classmethod
    def crear_para_inscripcion(cls, inscripcion, duracion_dias=30):
        """
        Servicio de fábrica seguro para emitir un AccesoExternoInscripcion.
        Garantiza que el token en texto plano solo exista en memoria durante la creación,
        persiste únicamente su hash SHA-256 y valida que el participante carezca de cuenta institucional.
        Retorna (instancia_acceso, raw_token).
        """
        if inscripcion.participante.usuario is not None:
            raise ValidationError(
                'No se puede generar un acceso externo para un participante con cuenta de usuario institucional.'
            )
        raw_token, token_hash = cls.generar_token()
        expiracion = timezone.now() + datetime.timedelta(days=duracion_dias)
        acceso = cls(
            inscripcion=inscripcion,
            token_hash=token_hash,
            fecha_expiracion=expiracion
        )
        acceso.save()
        return acceso, raw_token

    @classmethod
    def generar_token(cls):
        """Genera un token seguro URL-safe de 32 bytes y su hash SHA-256."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        return raw_token, token_hash

    def verificar_token(self, raw_token):
        """Valida si el token en plano coincide con el hash almacenado usando tiempo constante y vigencia."""
        if not raw_token:
            return False
        if not self.es_valido:
            return False
        calculated = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        return hmac.compare_digest(self.token_hash, calculated)

    @classmethod
    def validar_token(cls, raw_token):
        """
        Busca y valida de forma segura un AccesoExternoInscripcion a partir del token en plano.
        Retorna la instancia válida y vigente, o None si el token es inválido, revocado o expirado.
        """
        if not raw_token or not isinstance(raw_token, str):
            return None
        token_clean = raw_token.strip()
        if len(token_clean) < 10:
            return None
        token_hash = hashlib.sha256(token_clean.encode('utf-8')).hexdigest()
        acceso = (
            cls.objects
            .select_related('inscripcion', 'inscripcion__evento', 'inscripcion__participante')
            .filter(token_hash=token_hash)
            .first()
        )
        if acceso and acceso.verificar_token(token_clean):
            return acceso
        return None

    @property
    def es_valido(self):
        """Indica si el acceso está habilitado y vigente."""
        if self.revocado:
            return False
        if self.fecha_expiracion and timezone.now() > self.fecha_expiracion:
            return False
        if hasattr(self, 'inscripcion') and self.inscripcion and hasattr(self.inscripcion, 'participante') and self.inscripcion.participante:
            if self.inscripcion.participante.usuario is not None:
                return False
        return True

    def revocar(self):
        """Revoca de inmediato el acceso externo y registra la fecha."""
        self.revocado = True
        self.fecha_revocacion = timezone.now()
        self.save(update_fields=['revocado', 'fecha_revocacion'])
