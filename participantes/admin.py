from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Participante,
    Inscripcion,
    InvitacionEvento,
    AccesoExternoInscripcion,
)


@admin.register(Participante)
class ParticipanteAdmin(admin.ModelAdmin):
    list_display = (
        'id_participante',
        'documento',
        'nombres',
        'apellidos',
        'correo',
        'tipo',
        'usuario',
        'tiene_cuenta_usuario',
        'institucion',
        'fecha_registro',
    )
    list_filter = ('tipo', 'fecha_registro')
    search_fields = (
        'documento',
        'nombres',
        'apellidos',
        'correo',
        'programa',
        'facultad',
        'institucion',
        'usuario__username',
        'usuario__email',
    )
    ordering = ('apellidos', 'nombres')

    @admin.display(boolean=True, description='¿Tiene Usuario?')
    def tiene_cuenta_usuario(self, obj):
        return obj.usuario is not None


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = (
        'id_inscripcion',
        'evento',
        'participante',
        'tipo_participante',
        'estado',
        'asistio_check',
        'fecha_inscripcion',
    )
    list_filter = ('estado', 'fecha_inscripcion', 'evento', 'participante__tipo')
    search_fields = (
        'evento__nombre',
        'participante__nombres',
        'participante__apellidos',
        'participante__documento',
        'participante__correo',
    )
    ordering = ('-fecha_inscripcion',)

    @admin.display(description='Tipo Participante')
    def tipo_participante(self, obj):
        return obj.participante.get_tipo_display()

    @admin.display(boolean=True, description='¿Asistió?')
    def asistio_check(self, obj):
        return obj.asistio


@admin.register(InvitacionEvento)
class InvitacionEventoAdmin(admin.ModelAdmin):
    list_display = (
        'id_invitacion',
        'evento',
        'correo',
        'nombres',
        'apellidos',
        'institucion',
        'estado_badge',
        'invitado_por',
        'fecha_creacion',
        'fecha_expiracion',
        'fecha_respuesta',
    )
    list_filter = ('estado', 'fecha_creacion', 'evento')
    search_fields = (
        'correo',
        'nombres',
        'apellidos',
        'institucion',
        'evento__nombre',
        'invitado_por__username',
        'invitado_por__email',
    )
    ordering = ('-fecha_creacion',)
    readonly_fields = ('fecha_creacion', 'token_seguridad_info')
    exclude = ('token_hash',)

    @admin.display(description='Estado')
    def estado_badge(self, obj):
        colores = {
            'PENDIENTE': '#f59e0b',
            'ACEPTADA': '#10b981',
            'RECHAZADA': '#ef4444',
            'EXPIRADA': '#6b7280',
        }
        color = colores.get(obj.estado, '#374151')
        return format_html(
            '<span style="background-color: {}; color: #ffffff; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_estado_display()
        )

    @admin.display(description='Seguridad Criptográfica')
    def token_seguridad_info(self, obj):
        return format_html(
            '<span style="color: #059669; font-weight: 600;">🔒 Token protegido mediante hash SHA-256 (no expuesto en panel)</span>'
        )


@admin.register(AccesoExternoInscripcion)
class AccesoExternoInscripcionAdmin(admin.ModelAdmin):
    list_display = (
        'id_acceso',
        'inscripcion',
        'get_participante',
        'get_evento',
        'estado_vigencia',
        'revocado',
        'fecha_creacion',
        'fecha_expiracion',
        'ultimo_acceso',
    )
    list_filter = ('revocado', 'fecha_creacion')
    search_fields = (
        'inscripcion__participante__nombres',
        'inscripcion__participante__apellidos',
        'inscripcion__participante__correo',
        'inscripcion__evento__nombre',
    )
    ordering = ('-fecha_creacion',)
    readonly_fields = ('fecha_creacion', 'fecha_revocacion', 'ultimo_acceso', 'token_seguridad_info')
    exclude = ('token_hash',)

    @admin.display(description='Participante')
    def get_participante(self, obj):
        return str(obj.inscripcion.participante)

    @admin.display(description='Evento')
    def get_evento(self, obj):
        return str(obj.inscripcion.evento.nombre)

    @admin.display(description='Vigencia')
    def estado_vigencia(self, obj):
        if obj.revocado:
            return format_html('<span style="color: #dc2626; font-weight: bold;">✕ Revocado</span>')
        elif not obj.es_valido:
            return format_html('<span style="color: #6b7280; font-weight: bold;">⏳ Expirado</span>')
        return format_html('<span style="color: #16a34a; font-weight: bold;">✓ Válido</span>')

    @admin.display(description='Seguridad Criptográfica')
    def token_seguridad_info(self, obj):
        return format_html(
            '<span style="color: #059669; font-weight: 600;">🔒 Token protegido mediante hash SHA-256 (no expuesto en panel)</span>'
        )
