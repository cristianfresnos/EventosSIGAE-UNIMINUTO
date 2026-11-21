# Generated for RF-31: Calificaciones para participantes externos en EventosSIGAE-UNIMINUTO

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def poblar_inscripcion_calificaciones_historicas(apps, schema_editor):
    """
    Backfill idempotente de inscripcion_id para calificaciones institucionales históricas.
    - Conserva intactas todas las calificaciones existentes.
    - Si un registro histórico no tiene Inscripcion asociada, mantiene inscripcion_id=NULL
      sin fallar ni eliminar datos (válido porque estudiante_id IS NOT NULL).
    - Evita colisiones de unicidad sobre inscripcion_id antes de crear la restricción única.
    """
    CalificacionEvento = apps.get_model('eventos', 'CalificacionEvento')
    Inscripcion = apps.get_model('participantes', 'Inscripcion')

    inscripciones_ocupadas = set(
        CalificacionEvento.objects
        .filter(inscripcion_id__isnull=False)
        .values_list('inscripcion_id', flat=True)
    )

    pendientes = (
        CalificacionEvento.objects
        .filter(inscripcion_id__isnull=True, estudiante_id__isnull=False)
        .order_by('pk')
    )
    for calif in list(pendientes.values('pk', 'evento_id', 'estudiante_id')):
        # 'ACTIVA' precede alfabéticamente a 'CANCELADA'
        insc = (
            Inscripcion.objects
            .filter(
                evento_id=calif['evento_id'],
                participante__usuario_id=calif['estudiante_id'],
            )
            .order_by('estado', '-fecha_inscripcion')
            .first()
        )
        if insc and insc.pk not in inscripciones_ocupadas:
            CalificacionEvento.objects.filter(pk=calif['pk']).update(inscripcion_id=insc.pk)
            inscripciones_ocupadas.add(insc.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('eventos', '0004_docenteevento_evento_docentes_asociados_and_more'),
        ('participantes', '0006_inscripcion_nrc'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='calificacionevento',
            name='unique_calificacion_evento_estudiante',
        ),
        migrations.AddField(
            model_name='calificacionevento',
            name='inscripcion',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='calificaciones',
                to='participantes.inscripcion',
                verbose_name='Inscripción',
            ),
        ),
        migrations.AlterField(
            model_name='calificacionevento',
            name='estudiante',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='calificaciones_eventos',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Estudiante',
            ),
        ),
        migrations.RunPython(
            poblar_inscripcion_calificaciones_historicas,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='calificacionevento',
            constraint=models.UniqueConstraint(
                condition=models.Q(('estudiante__isnull', False)),
                fields=('evento', 'estudiante'),
                name='unique_calificacion_evento_estudiante',
            ),
        ),
        migrations.AddConstraint(
            model_name='calificacionevento',
            constraint=models.UniqueConstraint(
                condition=models.Q(('inscripcion__isnull', False)),
                fields=('inscripcion',),
                name='unique_calificacion_inscripcion',
            ),
        ),
        migrations.AddConstraint(
            model_name='calificacionevento',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('estudiante__isnull', False),
                    ('inscripcion__isnull', False),
                    _connector='OR',
                ),
                name='check_calificacion_tiene_sujeto',
            ),
        ),
    ]
