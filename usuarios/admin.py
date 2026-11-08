from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id_rol', 'nombre', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = (
        'username',
        'documento',
        'nombres',
        'apellidos',
        'email',
        'tipo_vinculacion',
        'rol',
        'tiene_perfil_participante',
        'estado',
        'is_active',
        'is_staff',
    )
    list_filter = (
        'tipo_vinculacion',
        'rol',
        'estado',
        'is_active',
        'is_staff',
        'is_superuser',
    )
    search_fields = (
        'username',
        'documento',
        'nombres',
        'apellidos',
        'email',
    )
    ordering = ('apellidos', 'nombres')

    @admin.display(boolean=True, description='¿Perfil Participante?')
    def tiene_perfil_participante(self, obj):
        return hasattr(obj, 'perfil_participante') and obj.perfil_participante is not None

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información Personal', {
            'fields': ('nombres', 'apellidos', 'documento', 'email', 'telefono')
        }),
        ('Vinculación Institucional y Rol', {
            'fields': ('tipo_vinculacion', 'rol', 'estado')
        }),
        ('Permisos', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            )
        }),
        ('Fechas Importantes', {
            'fields': ('last_login', 'date_joined')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Datos Institucionales', {
            'fields': (
                'nombres',
                'apellidos',
                'documento',
                'email',
                'telefono',
                'tipo_vinculacion',
                'rol',
                'estado',
            )
        }),
    )

