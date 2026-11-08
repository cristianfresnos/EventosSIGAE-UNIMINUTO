from django.urls import path
from . import views

app_name = 'asistencia'

urlpatterns = [
    # Pase digital del participante y descarga del QR
    path('inscripcion/<int:id_inscripcion>/pase/', views.pase_digital, name='pase_digital'),
    path('inscripcion/<int:id_inscripcion>/qr-imagen/', views.descargar_qr_imagen, name='qr_imagen'),
    path('inscripcion/<int:id_inscripcion>/qr-dinamico/', views.qr_dinamico, name='qr_dinamico'),

    # Panel de control de asistencia para organizadores (Cámara + Búsqueda Manual)
    path('evento/<int:id_evento>/control/', views.control_asistencia, name='control_asistencia'),

    # Gestión de sesión de salidas colectivas del organizador
    path('evento/<int:id_evento>/iniciar-sesion-salida/', views.iniciar_sesion_salida, name='iniciar_sesion_salida'),
    path('evento/<int:id_evento>/cerrar-sesion-salida/', views.cerrar_sesion_salida, name='cerrar_sesion_salida'),
    path('evento/<int:id_evento>/rotar-nonce-salida/', views.rotar_nonce_salida, name='rotar_nonce_salida'),
    path('evento/<int:id_evento>/proyector-salida/', views.proyector_salida, name='proyector_salida'),

    # Registro de salida del participante (cámara y validación por sesión)
    path('evento/<int:id_evento>/escanear-salida/', views.escanear_salida, name='escanear_salida'),
    path('evento/<int:id_evento>/registrar-salida/', views.registrar_salida_participante, name='registrar_salida_participante'),

    # QR común de salida del evento y control de habilitación
    path('evento/<int:id_evento>/salida/', views.salida_evento_publica, name='salida_evento_publica'),
    path('evento/<int:id_evento>/toggle-salidas/', views.toggle_salidas_evento, name='toggle_salidas_evento'),
    path('evento/<int:id_evento>/qr-salida-imagen/', views.descargar_qr_salida_imagen, name='descargar_qr_salida_imagen'),

    # Anulación controlada de asistencia
    path('asistencia/<int:id_asistencia>/anular/', views.anular_asistencia, name='anular_asistencia'),
]

