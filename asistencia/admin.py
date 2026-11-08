from django.contrib import admin
from .models import Asistencia, ControlSalidaEvento


@admin.register(ControlSalidaEvento)
class ControlSalidaEventoAdmin(admin.ModelAdmin):
    list_display = (
        'evento',
        'salidas_habilitadas',
        'sesion_id',
        'fecha_habilitacion',
        'habilitado_por',
        'fecha_cierre',
        'cerrado_por',
        'fecha_modificacion',
    )
    list_filter = ('salidas_habilitadas', 'fecha_habilitacion')
    search_fields = ('evento__nombre', 'sesion_id')
    readonly_fields = ('sesion_id', 'fecha_modificacion')
    exclude = ('nonce_vigente',)


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = (
        'id_asistencia',
        'get_participante',
        'get_evento',
        'fecha',
        'hora_entrada',
        'hora_salida',
        'metodo',
        'estado',
    )
    list_filter = ('estado', 'metodo', 'fecha', 'inscripcion__evento')
    search_fields = (
        'inscripcion__evento__nombre',
        'inscripcion__participante__nombres',
        'inscripcion__participante__apellidos',
        'inscripcion__participante__documento',
        'observaciones',
    )
    ordering = ('-fecha', '-fecha_registro')

    @admin.display(description='Participante')
    def get_participante(self, obj):
        return f"{obj.inscripcion.participante} ({obj.inscripcion.participante.get_tipo_display()})"

    @admin.display(description='Evento')
    def get_evento(self, obj):
        return obj.inscripcion.evento.nombre
