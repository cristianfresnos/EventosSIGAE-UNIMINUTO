from django.urls import path
from . import views

app_name = 'participantes'

urlpatterns = [
    path('evento/<int:id_evento>/inscribirse/', views.inscribirse_evento, name='inscribirse'),
    path('mis-inscripciones/', views.mis_inscripciones, name='mis_inscripciones'),
    path('inscripcion/<int:id_inscripcion>/cancelar/', views.cancelar_inscripcion, name='cancelar_inscripcion'),

    # Flujo de invitaciones institucionales (RF-01 / Etapa 7.2.1 / Etapa 7.2.1.1)
    path('evento/<int:id_evento>/invitaciones/', views.gestionar_invitaciones, name='gestionar_invitaciones'),
    path('evento/<int:id_evento>/invitaciones/<int:id_invitacion>/reenviar/', views.reenviar_invitacion, name='reenviar_invitacion'),
    path('evento/<int:id_evento>/invitaciones/<int:id_invitacion>/cancelar/', views.cancelar_invitacion, name='cancelar_invitacion'),
    path('invitacion/<str:token>/', views.consultar_invitacion, name='consultar_invitacion'),
    path('invitacion/acceso/detalle/', views.ver_invitacion, name='ver_invitacion'),
    path('invitacion/acceso/responder/', views.responder_invitacion, name='responder_invitacion'),

    # Flujo de inscripción pública y participantes externos (Etapa 7.2.2)
    path('evento/<int:id_evento>/registro-publico/', views.inscripcion_publica_view, name='inscripcion_publica'),
    path('evento/<int:id_evento>/qr-inscripcion/', views.qr_inscripcion_publica, name='qr_inscripcion_publica'),
    path('externo/mi-inscripcion/', views.ver_inscripcion_externa, name='ver_inscripcion_externa'),
    path('externo/<str:token>/', views.consultar_acceso_externo, name='consultar_acceso_externo'),
]
