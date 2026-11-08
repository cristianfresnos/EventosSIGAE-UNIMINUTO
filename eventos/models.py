from django.conf import settings
from django.core.exceptions import ValidationError
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
