from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.http import HttpResponseRedirect
from .models import CategoriaEvento, Evento


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
