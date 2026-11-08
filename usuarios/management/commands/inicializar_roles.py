"""
Comando de gestión de Django para inicializar y garantizar los roles canónicos
del sistema EventosSIGAE-UNIMINUTO:
- Administrador
- Coordinador
- Docente
- Estudiante

Condiciones de seguridad:
- Idempotente: puede ejecutarse múltiples veces sin duplicar registros.
- Seguro: no altera asignaciones de usuarios ni concede privilegios extra.
- Preserva el esquema de base de datos intacto (cero migraciones).
"""

from django.core.management.base import BaseCommand
from usuarios.models import Rol


class Command(BaseCommand):
    help = 'Inicializa los roles institucionales canónicos del sistema de forma segura e idempotente.'

    ROLES_CANONICOS = [
        {
            'nombre': 'Administrador',
            'descripcion': 'Administrador general del sistema con acceso a gestión institucional y auditoría.',
            'activo': True
        },
        {
            'nombre': 'Coordinador',
            'descripcion': 'Coordinador académico o administrativo de área/facultad con permisos de gestión de eventos.',
            'activo': True
        },
        {
            'nombre': 'Docente',
            'descripcion': 'Docente institucional con facultades para organizar eventos y gestionar asistencia de sus asignaturas o proyectos.',
            'activo': True
        },
        {
            'nombre': 'Estudiante',
            'descripcion': 'Estudiante UNIMINUTO participante en eventos académicos y culturales.',
            'activo': True
        },
    ]

    def handle(self, *args, **options):
        creados = 0
        conservados = 0

        self.stdout.write(self.style.MIGRATE_HEADING("Inicializando roles canónicos en EventosSIGAE-UNIMINUTO..."))

        for data in self.ROLES_CANONICOS:
            nombre = data['nombre']
            rol, created = Rol.objects.get_or_create(
                nombre=nombre,
                defaults={
                    'descripcion': data['descripcion'],
                    'activo': data['activo']
                }
            )
            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(f" [+] Rol creado: {nombre} (ID {rol.pk})"))
            else:
                conservados += 1
                self.stdout.write(f" [OK] Rol existente conservado: {nombre} (ID {rol.pk})")

        self.stdout.write(self.style.SUCCESS(
            f"Inicialización completada exitosamente: {creados} creados, {conservados} conservados (Total: {Rol.objects.count()} roles)."
        ))
