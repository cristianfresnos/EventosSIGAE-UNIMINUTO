import uuid
import secrets
import hmac
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class MetodoAsistencia(models.TextChoices):
    QR = 'QR', 'QR'
    MANUAL = 'MANUAL', 'Manual'
    LISTA = 'LISTA', 'Lista'
    OTRO = 'OTRO', 'Otro'


class EstadoAsistencia(models.TextChoices):
    REGISTRADA = 'REGISTRADA', 'Registrada'
    ANULADA = 'ANULADA', 'Anulada'


class Asistencia(models.Model):
    """
    Modelo representativo del registro de asistencia a un evento en SIGAE.
    Se vincula exclusivamente a través de la inscripción del participante al evento.
    """
    id_asistencia = models.AutoField(primary_key=True)
    inscripcion = models.OneToOneField(
        'participantes.Inscripcion',
        on_delete=models.PROTECT,
        related_name='asistencia',
        verbose_name='Inscripción'
    )
    fecha = models.DateField(
        verbose_name='Fecha'
    )
    hora_entrada = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Hora de entrada'
    )
    hora_salida = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Hora de salida'
    )
    metodo = models.CharField(
        max_length=30,
        choices=MetodoAsistencia.choices,
        default=MetodoAsistencia.MANUAL,
        verbose_name='Método de registro'
    )
    estado = models.CharField(
        max_length=30,
        choices=EstadoAsistencia.choices,
        default=EstadoAsistencia.REGISTRADA,
        verbose_name='Estado de asistencia'
    )
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones'
    )
    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de registro'
    )

    class Meta:
        verbose_name = 'Asistencia'
        verbose_name_plural = 'Asistencias'
        ordering = ['-fecha', '-fecha_registro']

    def __str__(self):
        return f"Asistencia #{self.id_asistencia} - {self.inscripcion}"

    @property
    def es_valida(self):
        """
        Indica si el registro de asistencia es formalmente válido (estado REGISTRADA).
        Propiedad de solo lectura para evaluación en servicios y modelo.
        """
        return self.estado == EstadoAsistencia.REGISTRADA

    @property
    def permanencia(self):
        """
        Calcula la permanencia del participante en horas y minutos.
        Retorna un diccionario estructurado o None si no se ha registrado hora_salida.
        Maneja transiciones que cruzan la medianoche añadiendo un día al cómputo de salida.
        """
        if not (self.hora_entrada and self.hora_salida):
            return None
        import datetime
        fecha_ref = self.fecha or datetime.date.today()
        entrada_dt = datetime.datetime.combine(fecha_ref, self.hora_entrada)
        salida_dt = datetime.datetime.combine(fecha_ref, self.hora_salida)

        cruce_medianoche = False
        if salida_dt < entrada_dt:
            # Salida en la madrugada siguiente (evento nocturno / trasnoche)
            salida_dt += datetime.timedelta(days=1)
            cruce_medianoche = True

        delta = salida_dt - entrada_dt
        total_minutos = int(delta.total_seconds() // 60)
        horas = total_minutos // 60
        minutos = total_minutos % 60
        texto = f"{horas}h {minutos}m" if horas > 0 else f"{minutos} min"
        return {
            'horas': horas,
            'minutos': minutos,
            'total_minutos': total_minutos,
            'texto': texto,
            'cruce_medianoche': cruce_medianoche,
        }

    @property
    def tiempo_permanencia_str(self):
        """Texto legible de permanencia para plantillas y reportes."""
        p = self.permanencia
        return p['texto'] if p else '-'

    def clean(self):
        super().clean()
        errors = {}

        # 1. Si no existe hora_entrada, no debe existir hora_salida
        if self.hora_salida and not self.hora_entrada:
            errors['hora_salida'] = 'No se puede registrar una hora de salida sin haber registrado una hora de entrada.'

        # 2. Si hora_salida tiene valor, validar coherencia temporal
        if self.hora_entrada and self.hora_salida:
            if self.hora_salida == self.hora_entrada:
                errors['hora_salida'] = 'La hora de salida no puede ser idéntica a la hora de entrada.'
            elif self.hora_salida < self.hora_entrada:
                # Validar si corresponde a cruce de medianoche verosímil
                es_cruce_valido = (self.hora_entrada.hour >= 18 and self.hora_salida.hour <= 8)
                if not es_cruce_valido:
                    errors['hora_salida'] = 'La hora de salida debe ser posterior a la hora de entrada.'

        # 3. La inscripción debe pertenecer a un evento cuyo estado no sea CANCELADO
        try:
            if self.inscripcion and self.inscripcion.evento:
                if self.inscripcion.evento.estado == 'CANCELADO':
                    errors['inscripcion'] = 'No se puede registrar asistencia para un evento en estado CANCELADO.'
        except (AttributeError, models.ObjectDoesNotExist):
            pass

        # 4. Validar unicidad de asistencia por inscripción a nivel de formulario
        try:
            if self.inscripcion_id:
                asistencia_existente = Asistencia.objects.filter(inscripcion_id=self.inscripcion_id)
                if self.pk:
                    asistencia_existente = asistencia_existente.exclude(pk=self.pk)
                if asistencia_existente.exists():
                    errors['inscripcion'] = 'Esta inscripción ya cuenta con un registro de asistencia.'
        except Exception:
            pass

        if errors:
            raise ValidationError(errors)


class ControlSalidaEvento(models.Model):
    """
    Control operativo del organizador para habilitar o deshabilitar
    el registro masivo de salidas mediante QR común del evento.
    Soporta sesiones de salida colectiva, nonces de rotación y auditoría de operadores.
    """
    evento = models.OneToOneField(
        'eventos.Evento',
        on_delete=models.CASCADE,
        related_name='control_salida',
        primary_key=True,
        verbose_name='Evento'
    )
    salidas_habilitadas = models.BooleanField(
        default=False,
        verbose_name='Registro de salidas habilitado'
    )
    fecha_habilitacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de habilitación'
    )
    habilitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salidas_habilitadas_set',
        verbose_name='Habilitado por'
    )
    sesion_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name='Identificador de sesión de salida'
    )
    nonce_vigente = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name='Identificador de generación o nonce vigente'
    )
    fecha_cierre = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de cierre'
    )
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salidas_cerradas_set',
        verbose_name='Cerrado por'
    )
    fecha_modificacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Fecha de última modificación'
    )

    class Meta:
        verbose_name = 'Control de salida de evento'
        verbose_name_plural = 'Controles de salida de eventos'
        constraints = [
            models.UniqueConstraint(
                fields=['sesion_id'],
                condition=models.Q(sesion_id__isnull=False),
                name='unique_sesion_id_control_salida'
            )
        ]

    def __str__(self):
        estado_str = "Habilitadas" if self.salidas_habilitadas else "Deshabilitadas"
        return f"Control Salida Evento #{self.pk} - {estado_str}"

    def clean(self):
        super().clean()
        if not self.sesion_id:
            self.sesion_id = None
        if not self.nonce_vigente:
            self.nonce_vigente = None

    def save(self, *args, **kwargs):
        if not self.sesion_id:
            self.sesion_id = None
        if not self.nonce_vigente:
            self.nonce_vigente = None
        super().save(*args, **kwargs)

    def iniciar_sesion(self, operador=None):
        """
        Inicia una nueva sesión de salida colectiva para el evento bajo transacción y bloqueo.
        Garantiza:
        - Asignación de un nuevo identificador de sesión único e irrepetible.
        - Generación de un nonce criptográfico inicial.
        - Registro del operador y marca temporal de habilitación.
        - Anulación de fechas y operadores de cierres previos.
        - Protección frente a condiciones de carrera concurrentes.
        """
        with transaction.atomic():
            control = ControlSalidaEvento.objects.select_for_update().filter(pk=self.pk).first()
            target = control if control is not None else self

            target.salidas_habilitadas = True
            target.sesion_id = f"SES-{self.evento_id}-{uuid.uuid4().hex[:16]}"
            target.nonce_vigente = secrets.token_urlsafe(24)
            target.fecha_habilitacion = timezone.now()
            target.habilitado_por = operador
            target.fecha_cierre = None
            target.cerrado_por = None
            target.save()

            self.salidas_habilitadas = target.salidas_habilitadas
            self.sesion_id = target.sesion_id
            self.nonce_vigente = target.nonce_vigente
            self.fecha_habilitacion = target.fecha_habilitacion
            self.habilitado_por = target.habilitado_por
            self.fecha_cierre = target.fecha_cierre
            self.cerrado_por = target.cerrado_por
            return self.sesion_id, self.nonce_vigente

    def cerrar_sesion(self, operador=None):
        """
        Cierra de forma definitiva la sesión activa de salida colectiva bajo transacción.
        Garantiza:
        - Invalida de inmediato el nonce vigente (nonce_vigente = None).
        - Deshabilita el registro de salidas (salidas_habilitadas = False).
        - Registra la marca temporal de cierre y el operador responsable.
        - Impide que cualquier QR emitido con el nonce o sesión anterior pueda ser reutilizado.
        """
        with transaction.atomic():
            control = ControlSalidaEvento.objects.select_for_update().filter(pk=self.pk).first()
            target = control if control is not None else self

            target.salidas_habilitadas = False
            target.nonce_vigente = None
            target.fecha_cierre = timezone.now()
            target.cerrado_por = operador
            target.save()

            self.salidas_habilitadas = target.salidas_habilitadas
            self.nonce_vigente = target.nonce_vigente
            self.fecha_cierre = target.fecha_cierre
            self.cerrado_por = target.cerrado_por

    def rotar_nonce(self):
        """
        Rota el nonce vigente de la sesión activa para evitar captura y reutilización estática.
        Si la sesión está cerrada o deshabilitada, rechaza la operación.
        """
        with transaction.atomic():
            control = ControlSalidaEvento.objects.select_for_update().filter(pk=self.pk).first()
            target = control if control is not None else self

            if not target.salidas_habilitadas or not target.sesion_id or target.fecha_cierre:
                raise ValidationError("No se puede rotar el nonce de una sesión inactiva o cerrada.")
            target.nonce_vigente = secrets.token_urlsafe(24)
            target.save(update_fields=['nonce_vigente', 'fecha_modificacion'])

            self.nonce_vigente = target.nonce_vigente
            self.fecha_modificacion = target.fecha_modificacion
            return self.nonce_vigente

    def es_sesion_activa(self, sesion_id, nonce=None):
        """
        Verifica si la sesión y el nonce corresponden a la ventana de salida actualmente abierta.
        Garantiza que ningún QR de una sesión anterior o con nonce revocado/antiguo sea válido.
        """
        if not self.salidas_habilitadas:
            return False
        if self.fecha_cierre is not None:
            return False
        if not self.sesion_id or self.sesion_id != sesion_id:
            return False
        if nonce is not None:
            if not self.nonce_vigente or not hmac.compare_digest(self.nonce_vigente, nonce):
                return False
        return True
