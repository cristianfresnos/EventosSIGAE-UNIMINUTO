from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    path('evento/<int:id_evento>/planilla-pdf/', views.descargar_planilla_asistencia_pdf, name='planilla_asistencia_pdf'),
    path('evento/<int:id_evento>/reporte-pdf/', views.descargar_reporte_consolidado_pdf, name='reporte_consolidado_pdf'),
]
