# ==============================================================================
# CONFIGURACIÓN DE GUNICORN — SIGAE-UNIMINUTO (PRODUCCIÓN LINUX)
# Archivo: deploy/gunicorn_conf.py
# ==============================================================================
import multiprocessing
import os

# Dirección de enlace (Socket UNIX para alto rendimiento o TCP local)
# Para socket UNIX en Linux: 'unix:/run/gunicorn/sigae.sock'
# Para TCP local: '127.0.0.1:8000'
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# Número de procesos trabajadores (Workers)
# Fórmula estándar: (2 * CPU_CORES) + 1
# CONTROL DE CONSUMO DE MEMORIA:
# Cada worker Django consume aproximadamente entre 100MB y 150MB de RAM.
# En servidores con muchos núcleos (ej. 16 o 32 vCPUs), calcular sin tope causaría
# consumo excesivo (ej. 65 workers = >8 GB RAM). Se establece un tope prudente
# por defecto de 8 workers, modificable vía variable GUNICORN_WORKERS.
cores = multiprocessing.cpu_count()
default_workers = min((cores * 2) + 1, 8)
workers = int(os.environ.get('GUNICORN_WORKERS', default_workers))

# Clase de worker: sync es la más probada y confiable con Django WSGI y psycopg 3
worker_class = 'sync'

# Conexiones simultáneas máximas por worker
worker_connections = 1000

# Tiempo máximo de espera para una solicitud (timeout en segundos)
timeout = 60
keepalive = 5

# Máximo de solicitudes que un worker procesará antes de reiniciarse (mitiga fugas de memoria)
max_requests = 1000
max_requests_jitter = 50

# Seguridad: máscara de permisos estricta para archivos y sockets creados por Gunicorn
# 0o027 otorga rwxr-x--- (usuario lectura/escritura, grupo lectura/ejecución, otros nada)
umask = 0o027

# Registro y diagnóstico de logs
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '/var/log/sigae/sigae_access.log')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '/var/log/sigae/sigae_error.log')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# Nombre del proceso en la tabla de procesos del sistema
proc_name = 'sigae_gunicorn'
