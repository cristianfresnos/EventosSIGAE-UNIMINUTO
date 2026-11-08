#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE CONSTRUCCIÓN (BUILD) PARA RENDER — EVENTOSSIGAE-UNIMINUTO
# Plataforma: Render (Linux PaaS)
# Propósito: Instalar dependencias de producción y compilar archivos estáticos.
# ==============================================================================
# NOTA CRÍTICA DE DESPLIEGUE:
# Por directriz estricta de arquitectura, este script NO ejecuta 'migrate' ni
# 'inicializar_roles'. Las migraciones sobre Neon PostgreSQL se deben ejecutar
# de manera controlada y manual desde la Render Shell o tarea de release
# una vez verificada la conectividad y autorizada la base de datos.
# ==============================================================================

# Detener la ejecución si ocurre cualquier error
set -o errexit

echo "=================================================="
echo ">> [1/2] Actualizando pip e instalando dependencias..."
echo "=================================================="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "=================================================="
echo ">> [2/2] Recolectando archivos estáticos con WhiteNoise..."
echo "=================================================="
python manage.py collectstatic --no-input

echo "=================================================="
echo ">> Construcción completada exitosamente."
echo ">> (Migraciones excluidas intencionalmente de la fase de build)"
echo "=================================================="
