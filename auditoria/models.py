from django.conf import settings
from django.db import models


class Auditoria(models.Model):
    """
    Modelo de bitácora histórica para trazabilidad de seguridad y control de cambios en SIGAE.
    Registra operaciones realizadas en los diferentes módulos sin acoplarse directamente a las entidades de negocio.
    """
    id_auditoria = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registros_auditoria',
        verbose_name='Usuario'
    )
    accion = models.CharField(
        max_length=100,
        verbose_name='Acción'
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y hora'
    )
    modulo = models.CharField(
        max_length=100,
        verbose_name='Módulo'
    )
    registro_afectado = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Registro afectado'
    )
    ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name='Dirección IP'
    )

    class Meta:
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'
        ordering = ['-fecha']

    def __str__(self):
        usuario_str = self.usuario.username if self.usuario else "Sistema/Anónimo"
        return f"[{self.modulo}] {self.accion} - {usuario_str}"

