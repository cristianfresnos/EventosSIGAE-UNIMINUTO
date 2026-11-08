from django.contrib import admin
from .models import Auditoria


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = (
        'id_auditoria',
        'usuario',
        'accion',
        'fecha',
        'modulo',
        'registro_afectado',
        'ip',
    )
    list_filter = (
        'accion',
        'modulo',
        'fecha',
    )
    search_fields = (
        'usuario__username',
        'usuario__email',
        'accion',
        'modulo',
        'registro_afectado',
    )
    ordering = ('-fecha',)

