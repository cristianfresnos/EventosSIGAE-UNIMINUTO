from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import CategoriaEvento, Evento, CalificacionEvento, DocenteEvento


@admin.register(CategoriaEvento)
class CategoriaEventoAdmin(admin.ModelAdmin):
    list_display = ('id_categoria', 'nombre', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        'id_evento',
        'nombre',
        'categoria',
        'organizador',
        'fecha',
        'hora_inicio',
        'hora_fin',
        'modalidad',
        'modalidad_inscripcion',
        'total_inscripciones',
        'cupo',
        'estado',
        'documentos_pdf',
    )
    list_filter = ('estado', 'modalidad', 'modalidad_inscripcion', 'categoria', 'fecha')
    search_fields = (
        'nombre',
        'descripcion',
        'lugar',
        'organizador__username',
        'organizador__email',
    )
    ordering = ('-fecha', 'hora_inicio')
    actions = ['descargar_planilla_action', 'descargar_reporte_action']

    @admin.display(description='Inscritos')
    def total_inscripciones(self, obj):
        return obj.inscripciones.count()

    @admin.display(description='Documentos PDF')
    def documentos_pdf(self, obj):
        url_planilla = reverse('reportes:planilla_asistencia_pdf', args=[obj.pk])
        url_reporte = reverse('reportes:reporte_consolidado_pdf', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" title="Descargar planilla imprimible" style="padding: 2px 6px; margin-right: 4px; font-size: 11px;">📄 Planilla</a>'
            '<a class="button" href="{}" target="_blank" title="Descargar reporte consolidado" style="padding: 2px 6px; font-size: 11px;">📊 Reporte</a>',
            url_planilla,
            url_reporte
        )

    @admin.action(description='Descargar Planilla de Asistencia (PDF) del evento seleccionado')
    def descargar_planilla_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Por favor seleccione exactamente un (1) evento para generar la planilla.", level=messages.WARNING)
            return None
        evento = queryset.first()
        return HttpResponseRedirect(reverse('reportes:planilla_asistencia_pdf', args=[evento.pk]))

    @admin.action(description='Descargar Reporte Consolidado (PDF) del evento seleccionado')
    def descargar_reporte_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Por favor seleccione exactamente un (1) evento para generar el reporte.", level=messages.WARNING)
            return None
        evento = queryset.first()
        return HttpResponseRedirect(reverse('reportes:reporte_consolidado_pdf', args=[evento.pk]))

    def save_model(self, request, obj, form, change):
        from django.db import transaction
        from asistencia.services import inicializar_controles_sesiones_evento
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if not change:
                inicializar_controles_sesiones_evento(obj)


@admin.register(CalificacionEvento)
class CalificacionEventoAdmin(admin.ModelAdmin):
    list_display = (
        'id_calificacion',
        'evento',
        'tipo_participante_admin',
        'puntuacion',
        'etiqueta_admin',
        'fecha_creacion',
        'fecha_actualizacion',
    )
    list_filter = ('puntuacion', 'evento', 'fecha_creacion')
    search_fields = ('evento__nombre',)
    readonly_fields = (
        'id_calificacion',
        'evento',
        'tipo_participante_admin',
        'puntuacion',
        'fecha_creacion',
        'fecha_actualizacion',
    )
    exclude = ('estudiante', 'inscripcion')
    ordering = ('-fecha_actualizacion',)

    @admin.display(description='Tipo de participante')
    def tipo_participante_admin(self, obj):
        return obj.tipo_participante_label

    @admin.display(description='Valoración')
    def etiqueta_admin(self, obj):
        return obj.etiqueta_puntuacion

    def has_add_permission(self, request):
        # Los administradores no pueden registrar calificaciones en nombre de participantes (RF-28, RF-31)
        return False

    def has_change_permission(self, request, obj=None):
        # Solo lectura para preservar la autenticidad e integridad de las calificaciones
        return False


@admin.register(DocenteEvento)
class DocenteEventoAdmin(admin.ModelAdmin):
    list_display = (
        'id_asignacion',
        'evento',
        'docente',
        'nrc',
        'activo',
        'asignado_por',
        'fecha_asignacion',
    )
    list_filter = ('activo', 'evento', 'fecha_asignacion')
    search_fields = (
        'evento__nombre',
        'docente__username',
        'docente__nombres',
        'docente__apellidos',
        'nrc',
    )
    ordering = ('-fecha_asignacion',)
