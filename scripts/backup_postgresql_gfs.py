"""
Script de Copias de Seguridad Automatizadas con Política GFS (Grandfather-Father-Son)
Proyecto: EventosSIGAE-UNIMINUTO (RNF-08, RNF-13)

Política de Retención Estricta GFS:
  - Son (Diario):          7 días de retención (subdirectorio daily/)
  - Father (Semanal):      4 semanas (28 días) de retención (subdirectorio weekly/, ejecutado domingos)
  - Grandfather (Mensual): 12 meses (365 días) de retención (subdirectorio monthly/, ejecutado día 1 del mes)

Cada nivel opera en un subdirectorio independiente, garantizando que la depuración diaria
no afecte los respaldos semanales ni mensuales.
"""
import os
import sys
import shutil
import hashlib
import datetime
import subprocess
from pathlib import Path

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Parámetros de conexión a PostgreSQL leídos desde variables de entorno
DB_NAME = os.environ.get('DB_NAME', 'sigae_test_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = os.environ.get('DB_PORT', '5433')

# Directorio de respaldos GFS por defecto
DEFAULT_BACKUP_ROOT = BASE_DIR / 'backups' / 'gfs'


def ensure_directories(backup_root: Path):
    """Crea los subdirectorios independientes para cada nivel de la jerarquía GFS."""
    for sub in ('daily', 'weekly', 'monthly'):
        d = backup_root / sub
        d.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass


def log_event(message: str, log_file: Path):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] {message}"
    print(entry)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry + '\n')
    except Exception as e:
        print(f"Advertencia: No se pudo escribir en log: {e}", file=sys.stderr)


def find_pg_binary(binary_name: str) -> str:
    """Localiza el binario de PostgreSQL en PATH o rutas estándar."""
    p = shutil.which(binary_name)
    if p:
        return p
    win_paths = [
        Path(r"C:\Users\cristian.fresnosG\pgsql\bin") / f"{binary_name}.exe",
        Path(r"C:\Program Files\PostgreSQL\16\bin") / f"{binary_name}.exe",
    ]
    for wp in win_paths:
        if wp.exists():
            return str(wp)
    return binary_name


def calcular_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def ejecutar_respaldo(backup_root: Path = None, db_name: str = None, forzar_semanal=False, forzar_mensual=False) -> Path:
    """
    Ejecuta el volcado pg_dump con formato Custom comprimido (-Fc),
    verifica la tabla de contenido con pg_restore --list y promueve a semanal/mensual según GFS.
    En caso de error, limpia archivos temporales y sale con código de error.
    """
    root = backup_root or DEFAULT_BACKUP_ROOT
    ensure_directories(root)

    target_db = db_name or os.environ.get('DB_NAME', 'sigae_test_db')
    target_user = os.environ.get('DB_USER', 'postgres')
    target_password = os.environ.get('DB_PASSWORD', '')
    target_host = os.environ.get('DB_HOST', '127.0.0.1')
    target_port = os.environ.get('DB_PORT', '5433')

    daily_dir = root / 'daily'
    weekly_dir = root / 'weekly'
    monthly_dir = root / 'monthly'
    log_file = root / 'backup_history.log'

    now = datetime.datetime.now()
    timestamp_str = now.strftime('%Y%m%d_%H%M%S')
    daily_filename = f"sigae_daily_{target_db}_{timestamp_str}.dump"
    daily_filepath = daily_dir / daily_filename

    log_event(f"Iniciando respaldo de base de datos '{target_db}' en {target_host}:{target_port}...", log_file)

    pg_dump_bin = find_pg_binary('pg_dump')
    pg_restore_bin = find_pg_binary('pg_restore')

    # Manejo seguro de credenciales mediante PGPASSWORD en el entorno del proceso (no en argumentos de línea de comandos)
    env = os.environ.copy()
    if target_password:
        env['PGPASSWORD'] = target_password

    cmd = [
        pg_dump_bin,
        '-h', target_host,
        '-p', str(target_port),
        '-U', target_user,
        '-Fc',  # Formato comprimido custom
        '-f', str(daily_filepath),
        target_db
    ]

    try:
        proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log_event(f"ERROR CRÍTICO al ejecutar pg_dump: {e.stderr.strip()}", log_file)
        if daily_filepath.exists():
            daily_filepath.unlink()
        raise RuntimeError(f"Fallo en pg_dump: {e.stderr.strip()}")

    # Verificar que el archivo generado tenga tamaño mayor a 0
    if not daily_filepath.exists() or daily_filepath.stat().st_size == 0:
        log_event("ERROR: El archivo de volcado no existe o está vacío.", log_file)
        if daily_filepath.exists():
            daily_filepath.unlink()
        raise RuntimeError("El archivo de volcado generado está vacío.")

    # Restringir permisos en sistemas POSIX
    if os.name != 'nt':
        try:
            os.chmod(daily_filepath, 0o600)
        except OSError:
            pass

    # Verificación estricta de integridad de tabla de contenido (TOC) con pg_restore --list
    check_cmd = [pg_restore_bin, '--list', str(daily_filepath)]
    try:
        check_proc = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        toc_lines = check_proc.stdout.splitlines()
        log_event(f"Verificación de integridad aprobada ({len(toc_lines)} entradas TOC válidas).", log_file)
    except subprocess.CalledProcessError as e:
        log_event(f"ERROR: El archivo de volcado falló la verificación de integridad con pg_restore: {e.stderr}", log_file)
        if daily_filepath.exists():
            daily_filepath.unlink()
        raise RuntimeError(f"Fallo en verificación pg_restore: {e.stderr}")

    file_size = daily_filepath.stat().st_size
    file_hash = calcular_sha256(daily_filepath)
    log_event(f"Respaldo Diario completado: {daily_filepath.name} ({file_size} bytes, SHA256: {file_hash})", log_file)

    # Política GFS: Promover a Semanal (Father) los domingos (weekday == 6) o si se fuerza
    is_sunday = now.weekday() == 6 or forzar_semanal
    if is_sunday:
        weekly_filename = f"sigae_weekly_{target_db}_{timestamp_str}.dump"
        weekly_filepath = weekly_dir / weekly_filename
        shutil.copy2(daily_filepath, weekly_filepath)
        if os.name != 'nt':
            try:
                os.chmod(weekly_filepath, 0o600)
            except OSError:
                pass
        log_event(f"Copia Semanal promovida a GFS Father: {weekly_filename}", log_file)

    # Política GFS: Promover a Mensual (Grandfather) el día 1 del mes o si se fuerza
    is_first_of_month = now.day == 1 or forzar_mensual
    if is_first_of_month:
        monthly_filename = f"sigae_monthly_{target_db}_{timestamp_str}.dump"
        monthly_filepath = monthly_dir / monthly_filename
        shutil.copy2(daily_filepath, monthly_filepath)
        if os.name != 'nt':
            try:
                os.chmod(monthly_filepath, 0o600)
            except OSError:
                pass
        log_event(f"Copia Mensual promovida a GFS Grandfather: {monthly_filename}", log_file)

    # Purgar archivos expirados según política estricta GFS
    purgar_expirados(root)

    return daily_filepath


def purgar_expirados(backup_root: Path = None):
    """
    Aplica la política de retención estricta GFS en subdirectorios independientes:
    - Diarios:   elimina si edad > 7 días (subdirectorio daily/)
    - Semanales: elimina si edad > 28 días (subdirectorio weekly/)
    - Mensuales: elimina si edad > 365 días (subdirectorio monthly/)
    """
    root = backup_root or DEFAULT_BACKUP_ROOT
    now = datetime.datetime.now()
    log_file = root / 'backup_history.log'

    politicas = [
        (root / 'daily', 7, "Diario"),
        (root / 'weekly', 28, "Semanal"),
        (root / 'monthly', 365, "Mensual"),
    ]

    for directorio, dias_retencion, nivel in politicas:
        if not directorio.exists():
            continue
        limite = now - datetime.timedelta(days=dias_retencion)
        for archivo in directorio.glob("*.dump"):
            mtime = datetime.datetime.fromtimestamp(archivo.stat().st_mtime)
            if mtime < limite:
                log_event(f"Depurando respaldo {nivel} expirado ({dias_retencion} días cumplidos): {archivo.name}", log_file)
                archivo.unlink()


if __name__ == '__main__':
    forzar_s = '--weekly' in sys.argv
    forzar_m = '--monthly' in sys.argv
    try:
        ejecutar_respaldo(forzar_semanal=forzar_s, forzar_mensual=forzar_m)
        sys.exit(0)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
