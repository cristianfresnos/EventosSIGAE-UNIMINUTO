# GUÍA DE DESPLIEGUE Y PROTOCOLO DE CONTINGENCIA EN SERVIDOR LINUX
## EVENTOSSIGAE-UNIMINUTO

**Entorno Destino:** Ubuntu Server 22.04 LTS / 24.04 LTS o Debian 12  
**Arquitectura:** Nginx (Proxy Inverso + TLS) -> Gunicorn 23 (WSGI) -> Django 6.1.1 (Python 3.13) -> PostgreSQL 16  
**Dominio:** `eventos.uniminuto.edu.co` (*Dominio de ejemplo pendiente de asignación oficial por la Dirección de TI*)  

---

## 1. PREPARACIÓN DEL SISTEMA OPERATIVO Y DEPENDENCIAS

```bash
# 1. Actualizar repositorios del sistema
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependencias del sistema, Python y PostgreSQL
sudo apt install -y python3.13 python3.13-venv python3.13-dev \
    postgresql postgresql-contrib libpq-dev nginx certbot python3-certbot-nginx \
    git curl libjpeg-dev zlib1g-dev

# 3. Crear usuario de servicio sin privilegios de shell interactivo (mínimo privilegio)
sudo adduser --system --group --home /var/www/sigae-uniminuto --shell /bin/bash sigae
sudo usermod -a -G www-data sigae
```

---

## 2. INSTALACIÓN DE LA APLICACIÓN

```bash
# 1. Clonar el repositorio en el directorio institucional
sudo -u sigae git clone <URL_REPOSITORIO_INSTITUCIONAL> /var/www/sigae-uniminuto
cd /var/www/sigae-uniminuto

# 2. Crear entorno virtual de producción aislado
sudo -u sigae python3.13 -m venv .venv
sudo -u sigae .venv/bin/pip install --upgrade pip

# 3. Instalar dependencias de producción (incluye Gunicorn y psycopg)
sudo -u sigae .venv/bin/pip install -r requirements-prod.txt

# 4. Configurar variables de entorno desde la plantilla
sudo -u sigae cp .env.example .env
sudo -u sigae chmod 600 .env
# Editar .env con credenciales seguras generadas localmente (NUNCA usar valores de ejemplo)
sudo -u sigae nano .env
```

---

## 3. CONFIGURACIÓN DE POSTGRESQL PARA PRODUCCIÓN (PRINCIPIO DE PRIVILEGIO MÍNIMO)

```bash
sudo -u postgres psql
```

```sql
-- 1. Crear base de datos de producción con codificación UTF-8
CREATE DATABASE sigae_production_db WITH ENCODING 'UTF8' LC_COLLATE = 'es_CO.UTF-8' LC_CTYPE = 'es_CO.UTF-8';

-- 2. Crear usuario de la aplicación con contraseña segura y cifrado SCRAM-SHA-256
CREATE USER sigae_app_user WITH ENCRYPTED PASSWORD '<GENERAR_PASSWORD_ALEATORIA_COMPLEJA>';

-- 3. Asignar conexión y privilegios de esquema
GRANT CONNECT ON DATABASE sigae_production_db TO sigae_app_user;
\c sigae_production_db

-- Privilegios de ejecución normal (DML únicamente)
GRANT USAGE ON SCHEMA public TO sigae_app_user;
GRANT CREATE ON SCHEMA public TO sigae_app_user; -- Requerido solo para aplicar migraciones
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sigae_app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sigae_app_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sigae_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sigae_app_user;
\q
```

---

## 4. MIGRACIONES, ESTÁTICOS Y PERMISOS

```bash
cd /var/www/sigae-uniminuto

# 1. Aplicar migraciones del esquema
sudo -u sigae .venv/bin/python manage.py migrate

# 2. Sincronizar secuencias de claves primarias
sudo -u sigae .venv/bin/python manage.py sqlsequencereset usuarios eventos participantes asistencia reportes analitica auditoria | sudo -u postgres psql -d sigae_production_db

# 3. Recolectar archivos estáticos para servicio directo por Nginx
sudo -u sigae .venv/bin/python manage.py collectstatic --noinput

# 4. Crear y ajustar permisos de carpetas de medios y logs
sudo mkdir -p /var/www/sigae-uniminuto/media /var/log/sigae
sudo chown -R sigae:www-data /var/www/sigae-uniminuto/media /var/log/sigae
sudo chmod 750 /var/www/sigae-uniminuto/media
sudo chmod 755 /var/log/sigae
```

---

## 5. CONFIGURACIÓN DE SYSTEMD Y GUNICORN

```bash
# 1. Instalar la unidad de servicio
sudo cp deploy/sigae.service /etc/systemd/system/sigae.service

# 2. Recargar configuración y arrancar servicio
sudo systemctl daemon-reload
sudo systemctl enable sigae.service
sudo systemctl start sigae.service

# 3. Verificar estado del proceso
sudo systemctl status sigae.service
```

---

## 6. CONFIGURACIÓN DE NGINX Y CERTIFICADO TLS

```bash
# 1. Instalar configuración de proxy inverso
sudo cp deploy/nginx_sigae.conf /etc/nginx/sites-available/sigae
sudo ln -s /etc/nginx/sites-available/sigae /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 2. Verificar sintaxis
sudo nginx -t

# 3. Solicitar certificado TLS institucional (o Let's Encrypt mediante Certbot)
sudo certbot --nginx -d eventos.uniminuto.edu.co

# 4. Recargar Nginx
sudo systemctl reload nginx
```

---

## 7. PROTOCOLO DE ROLLBACK SEGURO Y NO DESTRUCTIVO

> [!CAUTION]
> **ADVERTENCIA CRÍTICA CONTRA PÉRDIDA IRREVERSIBLE DE DATOS:**  
> **NUNCA** ejecute comandos destructivos como `dropdb`, `DROP DATABASE` ni `TRUNCATE` contra la base de datos activa. La eliminación de una base de datos destruye de forma irremediable inscripciones, registros de asistencia y bitácoras de auditoría institucional.

Si se produce un incidente crítico tras un despliegue o una actualización, aplique estrictamente el siguiente procedimiento en **8 pasos**:

### Paso 1: Notificación y Congelamiento de Tráfico
Detenga el tráfico de usuarios para evitar escrituras inconsistentes:
```bash
sudo systemctl stop sigae.service
```

### Paso 2: Volcado Preventivo de Emergencia (Conservación de Datos Recientes)
Antes de modificar cualquier esquema, genere un volcado de seguridad de la base activa actual. Esto preserva cualquier dato creado entre el último respaldo programado y el incidente:
```bash
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
pg_dump -U postgres -h 127.0.0.1 -p 5432 -Fc \
    -f "/var/backups/sigae/gfs/daily/sigae_safety_pre_rollback_${TIMESTAMP}.dump" sigae_production_db
```

### Paso 3: Verificación de Existencia e Integridad del Respaldo Destino
Compruebe que el respaldo que desea restaurar existe, es legible y tiene una tabla de contenidos (TOC) válida:
```bash
BACKUP_TO_RESTORE="/var/backups/sigae/gfs/daily/sigae_daily_production_db_<FECHA_VALIDA>.dump"
pg_restore --list "$BACKUP_TO_RESTORE" | head -n 30
```

### Paso 4: Creación y Restauración en Base Temporal Aislada
**NUNCA** restaure directamente sobre la base activa. Restaure siempre en una base temporal nueva:
```bash
RECOVERY_DB="sigae_recovery_test_${TIMESTAMP}"
sudo -u postgres createdb -E UTF8 -O sigae_app_user "$RECOVERY_DB"

# Restaurar en la base aislada
pg_restore -U sigae_app_user -h 127.0.0.1 -d "$RECOVERY_DB" -v "$BACKUP_TO_RESTORE"
```

### Paso 5: Verificación Técnica de la Base Restaurada
Ejecute la verificación de consistencia sobre la base temporal:
- Contar filas de todas las tablas principales (`usuarios_usuario`, `eventos_evento`, `participantes_inscripcion`, `asistencia_asistencia`, `auditoria_auditoria`).
- Comprobar que no existan claves foráneas huérfanas.
- Comprobar que las secuencias de IDs correspondan al valor máximo de cada tabla:
  ```bash
  sudo -u sigae DATABASE_URL="postgresql://sigae_app_user:<PASS>@127.0.0.1:5432/${RECOVERY_DB}" \
      .venv/bin/python manage.py check
  ```

### Paso 6: Autorización Formal de Sustitución
Presente los resultados de la verificación al Coordinador Técnico / DBA Institucional. Obtenga autorización explícita antes de proceder a la sustitución.

### Paso 7: Sustitución Atómica No Destructiva (Renombrado Seguro)
Sustituya la base mediante renombrado seguro (conservando la base anterior con un sufijo de diagnóstico):
```bash
sudo -u postgres psql -c "
  -- Terminar conexiones residuales
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'sigae_production_db';
  
  -- Renombrar la base activa (se conserva intacta para auditoría/peritaje)
  ALTER DATABASE sigae_production_db RENAME TO sigae_production_db_pre_rollback_${TIMESTAMP};
  
  -- Renombrar la base restaurada y verificada al nombre de producción
  ALTER DATABASE ${RECOVERY_DB} RENAME TO sigae_production_db;
"
```

### Paso 8: Reversión de Código, Arranque y Monitoreo
```bash
# 1. Regresar código al commit o versión anterior
cd /var/www/sigae-uniminuto
sudo -u sigae git checkout <COMMIT_O_TAG_ESTABLE>

# 2. Reiniciar el servicio de aplicación
sudo systemctl start sigae.service

# 3. Comprobar disponibilidad inmediatamente mediante endpoint de salud
curl -f -s -I http://127.0.0.1:8000/health/
# Debe retornar HTTP/1.1 200 OK
```

---

## 8. COMPROBACIONES QUE REQUIEREN ESTRICTAMENTE LINUX

Las siguientes comprobaciones **NO** pueden ejecutarse nativamente en Windows y deben realizarse en la máquina virtual o servidor Linux institucional:
1. **Llamadas POSIX de Gunicorn:** Señales UNIX (`SIGHUP`, `SIGTERM`), sockets de dominio UNIX en `/run/gunicorn/`.
2. **Aislamiento Systemd:** Directivas `PrivateTmp`, `ProtectSystem=full`, `NoNewPrivileges`.
3. **Módulo Nginx:** Carga del proxy y comprobación del bloqueo en vivo de `.php|.py|.sh` en `/media/`.
4. **Permisos y grupos POSIX:** Verificación de acceso para `sigae:www-data` con `chmod 750`.
5. **Rotación automática con logrotate:** Configuración en `/etc/logrotate.d/sigae`.
