#!/bin/bash
# ==============================================================================
# SCRIPT DE RESPALDO CON POLÍTICA GFS (GRANDFATHER-FATHER-SON) — SIGAE-UNIMINUTO
# Archivo: /usr/local/bin/backup_sigae_gfs.sh
# Permisos: chmod 700 /usr/local/bin/backup_sigae_gfs.sh
# ==============================================================================
set -euo pipefail

# Configuración leída desde variables de entorno o archivo seguro .env
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/sigae/gfs}"
DAILY_DIR="$BACKUP_ROOT/daily"
WEEKLY_DIR="$BACKUP_ROOT/weekly"
MONTHLY_DIR="$BACKUP_ROOT/monthly"
LOG_FILE="$BACKUP_ROOT/backup_history.log"

DB_NAME="${DB_NAME:-sigae_production_db}"
DB_USER="${DB_USER:-sigae_app_user}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

# Crear directorios con permisos estrictos de acceso (solo root/sigae)
mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"
chmod 700 "$BACKUP_ROOT" "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DATE_DAY=$(date +"%d")
DATE_DOW=$(date +"%u") # 1=Lunes, 7=Domingo

DUMP_FILE="$DAILY_DIR/sigae_daily_${DB_NAME}_${TIMESTAMP}.dump"

# Trap para limpiar volcado trunco o corrupto si ocurre un fallo durante la ejecución
cleanup_on_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR FATAL: Fallo durante el respaldo. Limpiando archivos incompletos..." | tee -a "$LOG_FILE"
    if [ -f "$DUMP_FILE" ]; then
        rm -f "$DUMP_FILE"
    fi
    exit 1
}
trap cleanup_on_error ERR

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Iniciando respaldo GFS para base '$DB_NAME'..." | tee -a "$LOG_FILE"

# Ejecución de volcado seguro con formato comprimido custom (-Fc)
# Nota: PGPASSWORD debe estar configurada en el entorno o mediante ~/.pgpass (chmod 600)
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$DUMP_FILE" "$DB_NAME"
chmod 600 "$DUMP_FILE"

# Verificación inmediata de integridad con pg_restore (valida la tabla de contenido TOC)
pg_restore --list "$DUMP_FILE" > /dev/null
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Integridad verificada exitosamente: $DUMP_FILE" | tee -a "$LOG_FILE"

# Promover a Semanal (Father) si es domingo (7)
if [ "$DATE_DOW" -eq 7 ]; then
    WEEKLY_FILE="$WEEKLY_DIR/sigae_weekly_${DB_NAME}_${TIMESTAMP}.dump"
    cp "$DUMP_FILE" "$WEEKLY_FILE"
    chmod 600 "$WEEKLY_FILE"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Respaldo Semanal (Father) generado: $WEEKLY_FILE" | tee -a "$LOG_FILE"
fi

# Promover a Mensual (Grandfather) si es día 1 del mes
if [ "$DATE_DAY" -eq "01" ]; then
    MONTHLY_FILE="$MONTHLY_DIR/sigae_monthly_${DB_NAME}_${TIMESTAMP}.dump"
    cp "$DUMP_FILE" "$MONTHLY_FILE"
    chmod 600 "$MONTHLY_FILE"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Respaldo Mensual (Grandfather) generado: $MONTHLY_FILE" | tee -a "$LOG_FILE"
fi

# ==============================================================================
# POLÍTICA DE PURGA ESTRICTA GFS (Subdirectorios independientes)
# ==============================================================================
# 1. Diarios: Se eliminan archivos que superen los 7 días
find "$DAILY_DIR" -type f -name "sigae_daily_*.dump" -mtime +7 -delete

# 2. Semanales: Se eliminan archivos que superen los 28 días (4 semanas)
find "$WEEKLY_DIR" -type f -name "sigae_weekly_*.dump" -mtime +28 -delete

# 3. Mensuales: Se eliminan archivos que superen los 365 días (12 meses)
find "$MONTHLY_DIR" -type f -name "sigae_monthly_*.dump" -mtime +365 -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Proceso de respaldo y rotación GFS finalizado con éxito." | tee -a "$LOG_FILE"
