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
    docentes_asociados = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='DocenteEvento',
        through_fields=('evento', 'docente'),
        related_name='eventos_asociados',
        blank=True,
        verbose_name='Docentes asociados'
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
    Calificación obligatoria mediante escala de 1 a 5 estrellas emitida tras completar
    la asistencia (entrada y salida confirmadas) en un evento institucional (RF-24 a RF-31).
    Admite tanto estudiantes institucionales (estudiante + inscripcion) como participantes
    externos sin cuenta institucional (inscripcion con estudiante=NULL), garantizando
    unicidad e integridad referencial en base de datos y modelo.
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
        null=True,
        blank=True,
        related_name='calificaciones_eventos',
        verbose_name='Estudiante'
    )
    inscripcion = models.ForeignKey(
        'participantes.Inscripcion',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='calificaciones',
        verbose_name='Inscripción'
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
                condition=models.Q(estudiante__isnull=False),
                name='unique_calificacion_evento_estudiante'
            ),
            models.UniqueConstraint(
                fields=['inscripcion'],
                condition=models.Q(inscripcion__isnull=False),
                name='unique_calificacion_inscripcion'
            ),
            models.CheckConstraint(
                condition=models.Q(estudiante__isnull=False) | models.Q(inscripcion__isnull=False),
                name='check_calificacion_tiene_sujeto'
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
        if self.estudiante_id:
            sujeto = str(self.estudiante)
        else:
            sujeto = f"Externo (Inscripción #{self.inscripcion_id})"
        return f"Evento #{self.evento_id} - {sujeto} ({self.puntuacion}★)"

    @property
    def es_externa(self):
        """Indica si la calificación corresponde a un participante externo sin cuenta institucional."""
        return self.estudiante_id is None and self.inscripcion_id is not None

    @property
    def tipo_participante_label(self):
        """Clasificación no sensible del origen de la evaluación para paneles administrativos."""
        return 'Externo' if self.es_externa else 'Institucional'

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

        if not self.estudiante_id and not self.inscripcion_id:
            raise ValidationError(
                'La calificación debe estar asociada al menos a un estudiante o a una inscripción.'
            )

        if self.inscripcion_id:
            inscripcion = getattr(self, 'inscripcion', None)
            if inscripcion is None:
                from participantes.models import Inscripcion
                inscripcion = Inscripcion.objects.select_related('participante').filter(pk=self.inscripcion_id).first()
            if inscripcion is not None:
                if self.evento_id and inscripcion.evento_id != self.evento_id:
                    raise ValidationError({
                        'inscripcion': 'La inscripción no corresponde al evento que se está calificando.'
                    })
                part_usuario_id = getattr(inscripcion.participante, 'usuario_id', None) if getattr(inscripcion, 'participante', None) else None
                if self.estudiante_id:
                    if part_usuario_id != self.estudiante_id:
                        raise ValidationError({
                            'inscripcion': 'La inscripción no corresponde al estudiante asociado a esta calificación.'
                        })
                elif part_usuario_id is not None:
                    raise ValidationError({
                        'estudiante': 'Una inscripción perteneciente a un usuario institucional debe asociar su estudiante.'
                    })


class DocenteEvento(models.Model):
    """
    Relación N:M entre Evento y Usuario (rol Docente) para habilitar permisos operativos
    compartidos entre múltiples profesores asociados al mismo evento institucional.
    La asignación y revocación es responsabilidad exclusiva de Administrador o Coordinador.
    """
    id_asignacion = models.AutoField(primary_key=True)
    evento = models.ForeignKey(
        Evento,
        on_delete=models.CASCADE,
        related_name='docentes_asociados_rel',
        verbose_name='Evento'
    )
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='asignaciones_eventos',
        verbose_name='Docente asociado'
    )
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='docentes_asignados_por',
        verbose_name='Asignado por'
    )
    nrc = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='NRC / Curso asociado'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    fecha_asignacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de asignación'
    )

    class Meta:
        verbose_name = 'Docente asociado a evento'
        verbose_name_plural = 'Docentes asociados a eventos'
        ordering = ['docente__apellidos', 'docente__nombres']
        constraints = [
            models.UniqueConstraint(
                fields=['evento', 'docente'],
                name='unique_evento_docente_asociado'
            )
        ]
        indexes = [
            models.Index(fields=['evento', 'activo'], name='idx_docev_evento_activo'),
            models.Index(fields=['docente', 'activo'], name='idx_docev_docente_activo'),
        ]

    def __str__(self):
        nrc_txt = f" (NRC {self.nrc})" if self.nrc else ""
        return f"{self.docente} — {self.evento}{nrc_txt}"

    def clean(self):
        super().clean()
        if self.nrc:
            self.nrc = self.nrc.strip()
        if self.docente_id:
            docente = self.docente
            rol = getattr(docente, 'rol', None)
            if not rol or getattr(rol, 'nombre', None) != 'Docente':
                raise ValidationError({
                    'docente': 'Solo se pueden asociar usuarios con rol institucional Docente.'
                })
            if not docente.is_active:
                raise ValidationError({
                    'docente': 'No se puede asociar un usuario docente inactivo.'
                })
