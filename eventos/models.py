from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class CategoriaEvento(models.Model):
    """
    Modelo para la clasificación temática o tipología de los eventos en SIGAE.
    """
    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Nombre'
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descripción'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )

    class Meta:
        verbose_name = 'Categoría de evento'
        verbose_name_plural = 'Categorías de eventos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class ModalidadEvento(models.TextChoices):
    PRESENCIAL = 'PRESENCIAL', 'Presencial'
    VIRTUAL = 'VIRTUAL', 'Virtual'
    HIBRIDA = 'HIBRIDA', 'Híbrida'


class ModalidadInscripcion(models.TextChoices):
    SOLO_INVITACION = 'SOLO_INVITACION', 'Solo por invitación'
    ABIERTA = 'ABIERTA', 'Inscripción abierta'
    MIXTA = 'MIXTA', 'Modalidad mixta (Invitaciones y abierta)'


class EstadoEvento(models.TextChoices):
    BORRADOR = 'BORRADOR', 'Borrador'
    PUBLICADO = 'PUBLICADO', 'Publicado'
    CERRADO = 'CERRADO', 'Cerrado'
    CANCELADO = 'CANCELADO', 'Cancelado'
    FINALIZADO = 'FINALIZADO', 'Finalizado'


class Evento(models.Model):
    """
    Modelo representativo de los eventos institucionales, académicos y culturales de UNIMINUTO.
    """
    id_evento = models.AutoField(primary_key=True)
    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre'
    )
    descripcion = models.TextField(
        verbose_name='Descripción'
    )
    fecha = models.DateField(
        verbose_name='Fecha'
    )
    hora_inicio = models.TimeField(
        verbose_name='Hora de inicio'
    )
    hora_fin = models.TimeField(
        verbose_name='Hora de fin'
    )
    lugar = models.CharField(
        max_length=200,
        verbose_name='Lugar'
    )
    modalidad = models.CharField(
        max_length=30,
        choices=ModalidadEvento.choices,
        verbose_name='Modalidad'
    )
    modalidad_inscripcion = models.CharField(
        max_length=30,
        choices=ModalidadInscripcion.choices,
        default=ModalidadInscripcion.SOLO_INVITACION,
        verbose_name='Modalidad de inscripción',
        help_text='Define la política de admisión: solo por invitación, registro abierto o mixta.'
    )
    cupo = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Cupo'
    )
    estado = models.CharField(
        max_length=30,
        choices=EstadoEvento.choices,
        default=EstadoEvento.BORRADOR,
        verbose_name='Estado'
    )
    categoria = models.ForeignKey(
        CategoriaEvento,
        on_delete=models.PROTECT,
        related_name='eventos',
        verbose_name='Categoría'
    )
    organizador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='eventos_organizados',
        verbose_name='Organizador'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Fecha de actualización'
    )

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'
        ordering = ['-fecha', 'hora_inicio']

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        if self.hora_inicio and self.hora_fin:
            if self.hora_fin <= self.hora_inicio:
                raise ValidationError({
                    'hora_fin': 'La hora de fin no puede ser anterior o igual a la hora de inicio.'
                })


class CalificacionEvento(models.Model):
    """
    Calificación obligatoria mediante escala de 1 a 5 estrellas emitida por un estudiante
    tras completar su asistencia (entrada y salida confirmadas) en un evento institucional.
    Garantiza unicidad por combinación Evento + Estudiante y validación de rango en BD y modelo.
    """
    ETIQUETAS_PUNTUACION = {
        1: 'Muy malo',
        2: 'Malo',
        3: 'Regular',
        4: 'Bueno',
        5: 'Excelente',
    }

    id_calificacion = models.AutoField(primary_key=True)
    evento = models.ForeignKey(
        Evento,
        on_delete=models.CASCADE,
        related_name='calificaciones',
        verbose_name='Evento'
    )
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calificaciones_eventos',
        verbose_name='Estudiante'
    )
    puntuacion = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Puntuación'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Fecha de última actualización'
    )

    class Meta:
        verbose_name = 'Calificación de evento'
        verbose_name_plural = 'Calificaciones de eventos'
        ordering = ['-fecha_actualizacion', '-fecha_creacion']
        constraints = [
            models.UniqueConstraint(
                fields=['evento', 'estudiante'],
                name='unique_calificacion_evento_estudiante'
            ),
            models.CheckConstraint(
                condition=models.Q(puntuacion__gte=1, puntuacion__lte=5),
                name='check_calificacion_puntuacion_1_5'
            ),
        ]
        indexes = [
            models.Index(fields=['evento', 'puntuacion'], name='idx_calif_evento_punt'),
            models.Index(fields=['estudiante', 'fecha_creacion'], name='idx_calif_est_fecha'),
        ]

    def __str__(self):
        return f"Evento #{self.evento_id} - {self.estudiante} ({self.puntuacion}★)"

    @property
    def etiqueta_puntuacion(self):
        """Retorna la descripción textual correspondiente a la puntuación de 1 a 5."""
        return self.ETIQUETAS_PUNTUACION.get(self.puntuacion, '')

    def clean(self):
        super().clean()
        if self.puntuacion is None or isinstance(self.puntuacion, bool):
            raise ValidationError({
                'puntuacion': 'Debes seleccionar una calificación válida entre 1 y 5 estrellas.'
            })
        try:
            valor = int(self.puntuacion)
        except (TypeError, ValueError):
            raise ValidationError({
                'puntuacion': 'La puntuación debe ser un número entero entre 1 y 5.'
            })
        if valor < 1 or valor > 5:
            raise ValidationError({
                'puntuacion': 'La calificación debe estar comprendida entre 1 y 5 estrellas.'
            })
        self.puntuacion = valor
