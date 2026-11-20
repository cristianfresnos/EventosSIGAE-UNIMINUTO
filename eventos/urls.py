from django.urls import path
from . import views

app_name = 'eventos'

urlpatterns = [
    path('', views.catalogo_eventos, name='catalogo'),
    path('<int:id_evento>/', views.detalle_evento, name='detalle'),
    path('gestion/', views.mis_eventos, name='mis_eventos'),
    path('crear/', views.crear_evento, name='crear'),
    path('<int:id_evento>/editar/', views.editar_evento, name='editar'),
    path('<int:id_evento>/cancelar/', views.cancelar_evento, name='cancelar'),
    path('<int:id_evento>/calificar/', views.calificar_evento, name='calificar_evento'),
    path('<int:id_evento>/docentes/', views.gestionar_docentes_evento, name='gestionar_docentes'),
    path('<int:id_evento>/docentes/<int:id_docente>/remover/', views.remover_docente_evento, name='remover_docente'),
]

