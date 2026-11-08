from django.urls import path
from . import views

app_name = 'auditoria'

urlpatterns = [
    path('', views.consulta_auditoria, name='consulta_auditoria'),
]
