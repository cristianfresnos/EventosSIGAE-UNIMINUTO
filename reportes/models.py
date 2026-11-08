from django.db import models

# ==============================================================================
# Módulo de Reportes - EventosSIGAE-UNIMINUTO
# ==============================================================================
# La generación de planillas imprimibles y reportes informativos de eventos se
# realiza bajo demanda (stateless on-the-fly) a partir de consultas en tiempo
# real, sin persistir archivos estáticos innecesarios en la base de datos.
# La trazabilidad de descargas se canaliza mediante el módulo 'auditoria'.
# ==============================================================================

