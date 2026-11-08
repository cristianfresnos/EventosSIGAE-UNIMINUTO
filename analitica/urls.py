from django.urls import path
from . import views

app_name = 'analitica'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('exportar/csv/', views.exportar_csv, name='exportar_csv'),
    path('exportar/excel/', views.exportar_excel, name='exportar_excel'),
]

