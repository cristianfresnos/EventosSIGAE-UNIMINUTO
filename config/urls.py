"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from config.views import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='base.html'), name='inicio'),
    path('health/', health_check, name='health_check'),
    path('usuarios/', include('usuarios.urls', namespace='usuarios')),
    path('eventos/', include('eventos.urls', namespace='eventos')),
    path('participantes/', include('participantes.urls', namespace='participantes')),
    path('asistencia/', include('asistencia.urls', namespace='asistencia')),
    path('reportes/', include('reportes.urls', namespace='reportes')),
    path('analitica/', include('analitica.urls', namespace='analitica')),
    path('auditoria/', include('auditoria.urls', namespace='auditoria')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
