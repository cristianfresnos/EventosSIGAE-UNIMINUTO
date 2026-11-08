# INFORME TÉCNICO DE PREPARACIÓN PARA DESPLIEGUE PILOTO
## Proyecto: EventosSIGAE-UNIMINUTO
**Fecha de Elaboración:** Noviembre 2026  
**Entorno de Ejecución:** Python 3.13.0 | Django 6.1.1  
**Plataforma de Despliegue Objetivo:** Render (Web Service Linux) + Neon PostgreSQL 16 (Serverless)  
**Base de Datos Local:** SQLite (`db.sqlite3`)  

---

## 1. Estado Inicial de la Configuración

Al iniciar la actividad de preparación técnica para el despliegue piloto, el proyecto se encontraba en las siguientes condiciones:

- **Estructura del Proyecto:** Proyecto Django bajo el paquete raíz de configuración `config/` (`config/settings.py`, `config/wsgi.py`, `config/urls.py`, `config/asgi.py`).
- **Aplicaciones Activas:** 7 aplicaciones modulares (`usuarios`, `eventos`, `participantes`, `asistencia`, `reportes`, `analitica`, `auditoria`).
- **Estado de Base de Datos Local:** SQLite con archivo físico `db.sqlite3` íntegro. Se identificaron 7 migraciones ya diseñadas y probadas correspondientes a las Fases 7.1 a 7.3, pendientes de aplicación física para respetar la restricción de no modificar el archivo operativo local.
- **Soporte de Driver de Base de Datos:** `psycopg[binary]==3.3.6` instalado en el entorno virtual `.venv`.
- **Archivos Estáticos:** `whitenoise==6.8.2` instalado en el entorno virtual, con middleware posicionado en `config/settings.py`.
- **Servidor WSGI de Producción:** Configurado a nivel de código (`config.wsgi.application`), pendiente de estandarización en dependencias y scripts de ejecución en Render.

---

## 2. Archivos Inspeccionados

Se llevó a cabo una auditoría exhaustiva y directa sobre los archivos clave del repositorio:

1. `config/settings.py`: Inspección de la arquitectura de configuración para `DJANGO_ENV`, `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, motor `_parse_database_url`, WhiteNoise, almacenamiento `STORAGES`, políticas de cookies y headers HTTP.
2. `config/wsgi.py`: Verificación del callable WSGI (`config.wsgi.application`) para el servidor de aplicaciones en Linux.
3. `config/asgi.py`: Verificación del soporte ASGI para futuros canales asíncronos.
4. `requirements.txt`: Revisión de dependencias congeladas para producción.
5. `requirements-prod.txt`: Revisión del archivo de dependencias de servidor Linux.
6. `.gitignore`: Verificación de reglas para excluir `db.sqlite3`, entornos virtuales, variables de entorno (`.env`), secretos y carpetas temporales.
7. `usuarios/management/commands/inicializar_roles.py`: Inspección del comando idempotente de roles institucionales canónicos.
8. `usuarios/management/commands/crear_superusuario_inicial.py`: Inspección del comando para inicializar el superusuario con clave foránea al modelo `Rol`.
9. `build.sh`: Revisión y saneamiento del script de construcción de Render.

---

## 3. Cambios Realizados y Justificación

| Archivo Modificado / Creado | Tipo de Cambio | Justificación Técnica |
|---|---|---|
| `requirements.txt` | Modificación | Se agregaron formalmente `whitenoise==6.8.2` y `gunicorn==23.0.0` para garantizar que el comando de construcción en Render (`pip install -r requirements.txt`) instale el servidor WSGI estándar de producción y el despachador de archivos estáticos sin recurrir a paquetes adicionales no versionados. |
| `build.sh` | Actualización | Se depuró el script de construcción de Render para cumplir estrictamente con la directiva de despliegue: instala dependencias y ejecuta `collectstatic --no-input`. **Se eliminaron de forma absoluta las instrucciones `migrate` e `inicializar_roles` del build**, asegurando que ninguna migración se ejecute automáticamente antes de verificar la conectividad de Neon. |
| `render.yaml` | Creación | Se creó la especificación declarativa (Blueprint) para Render, definiendo el servicio web Linux, comandos de build y start, runtime Python 3.13.0, variables de entorno base y políticas de seguridad. |
| `GUIA_DESPLIEGUE_RENDER_NEON.md` | Creación | Documentación operativa completa, paso a paso, para aprovisionar Neon PostgreSQL 16, configurar Render, ejecutar migraciones manualmente en la Shell y realizar la verificación funcional. |

---

## 4. Dependencias Añadidas

Se consolidaron en `requirements.txt` exclusivamente las dependencias indispensables para operar en Render bajo Linux:

- **`whitenoise==6.8.2`**: Despacho ultra-eficiente de archivos estáticos desde el propio proceso de Python con compresión gzip/brotli y generación de hash manifiesto (`CompressedManifestStaticFilesStorage`).
- **`gunicorn==23.0.0`**: Servidor WSGI estándar para entornos de producción UNIX/Linux, compatible con Python 3.13.
- **`psycopg[binary]==3.3.6`** *(Ya instalado y congelado)*: Driver oficial de PostgreSQL (versión 3) con soporte completo para transacciones y SSL de Neon.

---

## 5. Variables de Entorno Necesarias

Las siguientes variables deben configurarse en el panel de control de Render (Web Service > Environment):

| Variable de Entorno | Tipo | Ejemplo / Valor en Producción | Justificación |
|---|:---:|---|---|
| `PYTHON_VERSION` | Fijo | `3.13.0` | Garantiza que Render compile el contenedor con la versión exacta de Python del proyecto. |
| `DJANGO_ENV` | Fijo | `production` | Activa el modo de producción en `settings.py`, forzando `DEBUG=False` y cookies seguras. |
| `DEBUG` | Fijo | `False` | Deshabilita trazas de depuración para evitar fugas de información sensible. |
| `SECRET_KEY` | Secreto | *(50+ caracteres aleatorios)* | Clave criptográfica para firmas de sesión y tokens CSRF. |
| `DATABASE_URL` | Secreto | `postgresql://user:pass@ep-xyz-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require` | Cadena de conexión al cluster de Neon PostgreSQL 16 con SSL obligatorio. |
| `RENDER` | Fijo | `true` | Informa a Django que se encuentra detrás del proxy inverso de Render. |
| `USE_X_FORWARDED_PROTO` | Fijo | `true` | Activa `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`. |
| `DEFAULT_FROM_EMAIL` | Fijo | `SIGAE UNIMINUTO <no-reply@uniminuto.edu.co>` | Remitente canónico para comunicaciones institucionales. |
| `EMAIL_BACKEND` | Fijo | `django.core.mail.backends.console.EmailBackend` | Backend de correo seguro para la fase piloto (evita envíos accidentales a buzones reales). |

---

## 6. Comandos de Construcción e Inicio para Render

- **Comando de Construcción (Build Command):**
  ```bash
  bash build.sh
  ```
  *Contenido del proceso:*
  1. `python -m pip install --upgrade pip`
  2. `python -m pip install -r requirements.txt`
  3. `python manage.py collectstatic --no-input`
  *(Migraciones excluidas intencionalmente del build).*

- **Comando de Inicio (Start Command):**
  ```bash
  gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
  ```
  *(Render enlaza automáticamente la variable de entorno `$PORT` al servidor Gunicorn).*

---

## 7. Estado de la Configuración PostgreSQL

- **Analizador Dinámico de `DATABASE_URL` (`_parse_database_url`):**
  - Implementado de forma nativa en `config/settings.py` sin paquetes externos.
  - Soporta esquemas `postgresql://`, `postgres://` y `psql://`.
  - Extrae y propaga automáticamente el parámetro `sslmode=require` exigido por Neon.
  - Extrae opciones de endpoint (`options=endpoint=ep-xxx`) necesarias en conexiones pooler.
  - **Detección de PgBouncer:** Si el hostname contiene `-pooler`, ajusta automáticamente `CONN_MAX_AGE = 0` para prevenir retención de conexiones inactivas.
- **Fallback Automático Local:** Si la variable `DATABASE_URL` no está definida, `settings.py` conmuta automáticamente a SQLite (`BASE_DIR / 'db.sqlite3'`), garantizando que las pruebas y desarrollo locales no sufran afectación.

---

## 8. Configuración de Seguridad

- **`DEBUG = False` Forzado:** En producción (`DJANGO_ENV=production`), si `DEBUG` fuese evaluado como `True`, el sistema arroja una excepción `ImproperlyConfigured` bloqueando el inicio inseguro.
- **`ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` Dinámicos:** Lee automáticamente la variable de entorno de Render `RENDER_EXTERNAL_HOSTNAME` e inyecta el FQDN asignado (ej. `eventossigae-uniminuto.onrender.com`) y su origen HTTPS correspondiente. Prohíbe comodines globales (`*`).
- **Detección de SSL tras Proxy Inverso:** Se configuró `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` cuando `RENDER=true` o `IS_PRODUCTION=True`. Esto previene bucles de redirección infinita HTTP->HTTPS.
- **Protección de Cookies:** `SESSION_COOKIE_SECURE = True` y `CSRF_COOKIE_SECURE = True` en producción.
- **Cabeceras de Defensa en Profundidad:** `SECURE_BROWSER_XSS_FILTER = True`, `SECURE_CONTENT_TYPE_NOSNIFF = True`, `X_FRAME_OPTIONS = 'DENY'`.

---

## 9. Estado de Archivos Estáticos y Multimedia

- **Archivos Estáticos:**
  - `STATIC_ROOT` configurado en `BASE_DIR / 'staticfiles'`.
  - Middleware de WhiteNoise (`whitenoise.middleware.WhiteNoiseMiddleware`) posicionado de forma óptima en `MIDDLEWARE[1]` inmediatamente después de `SecurityMiddleware`.
  - `collectstatic` compiló de forma limpia 133 archivos estáticos (CSS, JS, iconos, librerías frontend como `jsQR`).
  - En producción se utiliza `whitenoise.storage.CompressedManifestStaticFilesStorage` para compresión brotli/gzip y cache busting permanente.
- **Archivos Multimedia:**
  - El sistema **no utiliza campos `FileField` ni `ImageField`** en sus modelos de datos.
  - Los reportes institucionales (PDF con ReportLab y planillas Excel con openpyxl) y los códigos QR dinámicos se generan en memoria RAM (`io.BytesIO`) y se transmiten directamente al cliente por streaming HTTP (`HttpResponse`).
  - **Conclusión de Arquitectura:** El proyecto **no requiere almacenamiento en disco persistente ni servicios externos de almacenamiento de objetos (como AWS S3)** en Render. El disco efímero de Render es 100% compatible.

---

## 10. Resultados de Validaciones

| Validación Ejecutada | Comando | Resultado Obtenido | Estado |
|---|---|---|:---:|
| Verificación del Sistema Django | `manage.py check` | `System check identified no issues (0 silenced).` | **APROBADO** |
| Verificación de Dependencias Pip | `pip check` | `No broken requirements found.` | **APROBADO** |
| Consistencia de Modelos y Migraciones | `makemigrations --check --dry-run` | `No changes detected.` | **APROBADO** |
| Recolección de Archivos Estáticos | `collectstatic --dry-run --no-input` | 133 archivos procesados exitosamente sin fallos de manifiesto. | **APROBADO** |
| Conmutación Dual de Base de Datos | Prueba de resolución en Python | • Sin `DATABASE_URL` -> `django.db.backends.sqlite3`<br>• Con `DATABASE_URL` (Neon) -> `django.db.backends.postgresql` con `sslmode=require` | **APROBADO** |
| Suite Completa de Pruebas Automatizadas | `manage.py test` | 268 pruebas ejecutadas en base aislada, 268 aprobadas (100% éxito). 0 fallos, 0 errores. | **APROBADO** |

---

## 11. SHA-256 de SQLite Antes y Después

Para garantizar el cumplimiento de las restricciones de integridad y la prohibición de ejecutar migraciones sobre el entorno local:

- **SHA-256 Inicial de `db.sqlite3`:**
  `C30E8081B9E631C804E6B94081F2F252C82D53D8508E3FFD049608C722F290D0`
- **SHA-256 Final de `db.sqlite3`:**
  `C30E8081B9E631C804E6B94081F2F252C82D53D8508E3FFD049608C722F290D0`
- **Diagnóstico:** El archivo `db.sqlite3` se mantuvo **100% inalterado bit a bit**. Cero migraciones ejecutadas localmente.

---

## 12. Pasos Manuales a Completar en Neon y Render

Una vez que se decida publicar el servicio:

1. **En Neon ([neon.tech](https://neon.tech)):**
   - Crear el proyecto `eventossigae-uniminuto-db` en PostgreSQL 16.
   - Copiar la cadena de conexión `DATABASE_URL` con pooling de conexiones y parámetro `sslmode=require`.
2. **En Render ([render.com](https://render.com)):**
   - Crear el Web Service vinculado al repositorio (usando `render.yaml` o creación manual con `bash build.sh` y `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`).
   - Configurar las variables de entorno (`DJANGO_ENV=production`, `DEBUG=False`, `SECRET_KEY`, `DATABASE_URL`, `RENDER=true`, `USE_X_FORWARDED_PROTO=true`).
   - Permitir que Render ejecute el primer build (`bash build.sh`).
3. **En la Render Shell (Post-Despliegue Controlado):**
   - Abrir la pestaña **Shell** en el panel de Render.
   - Ejecutar la verificación de conexión:
     ```bash
     python -c "import django; django.setup(); from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT version();'); print('Conectado a:', cursor.fetchone()[0])"
     ```
   - Aplicar las migraciones canónicas sobre Neon:
     ```bash
     python manage.py migrate
     ```
   - Inicializar los roles institucionales:
     ```bash
     python manage.py inicializar_roles
     ```
   - Crear el superusuario inicial institucional:
     ```bash
     python manage.py crear_superusuario_inicial --username admin.institucional --email admin@uniminuto.edu.co --documento 1000000001 --nombres "Administrador" --apellidos "Institucional"
     ```

---

## 13. Riesgos o Bloqueantes Pendientes

1. **Modo de Suspensión (Cold Start) en Render Free Tier:**
   - En el plan gratuito de Render, el contenedor web se suspende tras 15 minutos de inactividad HTTP. La reactivación puede tardar de 30 a 50 segundos. Si se requiere disponibilidad inmediata sin latencia en eventos institucionales reales, se recomienda considerar el plan *Starter* ($7/mes).
2. **Envío de Correos a Buzones Reales:**
   - La configuración actual utiliza `console.EmailBackend`. Para que los participantes externos e invitados reciban correos en sus bandejas de entrada reales, se deberán parametrizar las credenciales SMTP institucionales de UNIMINUTO en las variables de entorno de Render (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, etc.).
3. **Acceso a Cámara Móvil para Escaneo de Códigos QR:**
   - Al desplegar en Render bajo HTTPS nativo (`https://...onrender.com`), el bloqueo de seguridad del navegador para la API `navigator.mediaDevices.getUserMedia` queda **100% resuelto**, permitiendo que operadores y participantes usen la cámara de sus teléfonos inteligentes sin impedimentos.

---
**Conclusión General:**  
La base de código de **EventosSIGAE-UNIMINUTO** se encuentra **técnicamente lista y preparada para el despliegue piloto en Render con Neon PostgreSQL**. No se realizaron migraciones, no se alteró la base local SQLite y se preservó la totalidad de la lógica funcional del sistema.

