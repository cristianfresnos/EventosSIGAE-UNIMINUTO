# GUÍA DE DESPLIEGUE PILOTO EN RENDER CON BASE DE DATOS NEON POSTGRESQL
## Proyecto: EventosSIGAE-UNIMINUTO (Django 6.1.1 / Python 3.13.0)

Esta guía detalla paso a paso el procedimiento técnico para desplegar la aplicación **EventosSIGAE-UNIMINUTO** en la plataforma **Render** (servicio web Linux) conectada a una base de datos serverless **PostgreSQL 16 en Neon**.

---

## 1. Arquitectura de Despliegue

```
  [ Usuario / Navegador / Celular ]
                 │
                 │ HTTPS (TLS 1.3 automático)
                 ▼
     [ Proxy Inverso Render ]  ─── Envía cabecera: X-Forwarded-Proto = https
                 │
                 ▼
  [ Contenedor Web Render (Linux) ]
    ├─ Servidor WSGI: Gunicorn (23.0.0)
    ├─ Framework: Django 6.1.1 (Python 3.13.0)
    ├─ Archivos Estáticos: WhiteNoise (6.8.2) con compresión y hash manifiesto
    └─ Generación QR / PDF / Excel: En memoria RAM (io.BytesIO) sin disco efímero
                 │
                 │ Conexión Segura SSL (psycopg 3.3.6, sslmode=require)
                 ▼
  [ Neon PostgreSQL 16 (Serverless) ]
    ├─ Pooling de conexiones: PgBouncer (-pooler endpoint)
    └─ Almacenamiento independiente, copias y escalado elástico
```

---

## 2. Requisitos Previos

1. Cuenta activa en [Neon](https://neon.tech).
2. Cuenta activa en [Render](https://render.com).
3. Repositorio de código del proyecto alojado en GitHub o GitLab.
4. Entorno local intacto (la base de datos local SQLite `db.sqlite3` no sufre ninguna modificación).

---

## 3. PASO 1: Aprovisionamiento de la Base de Datos en Neon

1. Inicia sesión en la consola de **Neon** ([console.neon.tech](https://console.neon.tech)).
2. Haz clic en **"New Project"**.
3. Diligencia los datos básicos:
   - **Project name:** `eventossigae-uniminuto-db`
   - **Postgres version:** `16` (versión recomendada y soportada por `psycopg 3.3.6`).
   - **Region:** Selecciona una región cercana a tu ubicación o a la región que usarás en Render (por ejemplo, `AWS US East (Ohio)` o `AWS US East (N. Virginia)`).
4. Haz clic en **"Create Project"**.
5. Al crearse el proyecto, Neon mostrará el panel **"Connection Details"**:
   - Selecciona el rol y la base de datos por defecto (`neondb`).
   - En la opción de conexión, activa **"Connection pooling"** si planeas manejar picos de concurrencia, o selecciona la cadena directa.
     > **Nota Técnica:** El analizador de base de datos del proyecto (`config/settings.py`) detecta automáticamente si el host contiene `-pooler` y ajusta `CONN_MAX_AGE = 0` para evitar conexiones huérfanas con PgBouncer, cumpliendo las mejores prácticas oficiales de Neon.
   - Copia la cadena de conexión completa que tiene el formato:
     ```text
     postgresql://<usuario>:<contraseña>@<host-neon>/<nombre_bd>?sslmode=require
     ```
   - **Guarda temporalmente esta URL de forma segura.** Esta será tu variable `DATABASE_URL`.

---

## 4. PASO 2: Creación del Servicio Web en Render

### Opción A: Despliegue mediante Render Blueprint (Recomendada)
Si el repositorio cuenta con el archivo `render.yaml` incluido en la raíz:
1. En el dashboard de Render, haz clic en **"New +"** y selecciona **"Blueprint"**.
2. Conecta el repositorio de `EventosSIGAE-UNIMINUTO`.
3. Render detectará automáticamente el archivo `render.yaml` y preconfigurará el servicio web con todos los parámetros técnicos (Python 3.13.0, Gunicorn, WhiteNoise y las variables de entorno base).
4. En el campo `DATABASE_URL`, introduce la cadena de conexión copiada de Neon.
5. Haz clic en **"Apply"**.

---

### Opción B: Creación Manual del Web Service
1. En el dashboard de Render, haz clic en **"New +"** y selecciona **"Web Service"**.
2. Selecciona la opción **"Build and deploy from a Git repository"** y vincula tu repositorio.
3. Configura los campos del servicio:
   - **Name:** `eventossigae-uniminuto` (o el subdominio que prefieras).
   - **Region:** Selecciona la misma región de Neon (ej. `Ohio (US East)`).
   - **Branch:** `main` (o tu rama de despliegue).
   - **Root Directory:** *(Dejar vacío para usar la raíz)*.
   - **Runtime:** `Python 3`.
   - **Build Command:**
     ```bash
     bash build.sh
     ```
   - **Start Command:**
     ```bash
     gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
     ```
   - **Instance Type:** `Free` (o `Starter` según requerimiento).

---

## 5. PASO 3: Configuración de Variables de Entorno en Render

En la pestaña **"Environment"** de tu servicio web en Render, configura las siguientes variables:

| Variable | Valor Recomendado / Descripción | Requerida |
|---|---|:---:|
| `PYTHON_VERSION` | `3.13.0` | **SÍ** |
| `DJANGO_ENV` | `production` | **SÍ** |
| `DEBUG` | `False` | **SÍ** |
| `SECRET_KEY` | *(Generar una clave segura aleatoria de 50+ caracteres o usar el generador de Render)* | **SÍ** |
| `DATABASE_URL` | `postgresql://<usuario>:<password>@<host-neon>/neondb?sslmode=require` | **SÍ** |
| `RENDER` | `true` | **SÍ** |
| `USE_X_FORWARDED_PROTO` | `true` | **SÍ** |
| `EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` *(por defecto para piloto)* | **SÍ** |
| `DEFAULT_FROM_EMAIL` | `SIGAE UNIMINUTO <no-reply@uniminuto.edu.co>` | **SÍ** |
| `ALLOWED_HOSTS` | *(Opcional en Render)* El sistema agrega automáticamente el host de Render (`RENDER_EXTERNAL_HOSTNAME`). Si tienes un dominio personalizado, añade: `eventos.tudominio.edu.co` | Condicional |
| `CSRF_TRUSTED_ORIGINS` | *(Opcional en Render)* Se autocalcula desde el host. Si usas dominio personalizado: `https://eventos.tudominio.edu.co` | Condicional |

> **IMPORTANTE: Integración SMTP Institucional (Opcional)**
> Cuando se autorice el envío de correos electrónicos reales a participantes externos e invitados, cambia `EMAIL_BACKEND` y agrega:
> - `EMAIL_BACKEND = django.core.mail.backends.smtp.EmailBackend`
> - `EMAIL_HOST = smtp.office365.com` (o el servidor asignado por UNIMINUTO)
> - `EMAIL_PORT = 587`
> - `EMAIL_USE_TLS = True`
> - `EMAIL_HOST_USER = tu_cuenta@uniminuto.edu.co`
> - `EMAIL_HOST_PASSWORD = tu_contraseña_o_app_password`

---

## 6. PASO 4: Primer Despliegue y Ejecución Controlada de Migraciones

Por diseño estricto de seguridad, **`build.sh` NO ejecuta migraciones automáticas**. Esto previene bloqueos del despliegue en caso de intermitencia de red y asegura que un administrador verifique la conectividad antes de tocar la base de datos.

### Procedimiento Post-Despliegue:

1. **Esperar a que finalice el primer Build:**
   Render clonará el repositorio, ejecutará `bash build.sh` (instalando `requirements.txt` y ejecutando `collectstatic --no-input`) e iniciará Gunicorn.
2. **Acceder a la Render Shell:**
   En el menú lateral del servicio web en Render, haz clic en la pestaña **"Shell"** para abrir una terminal interactiva en el contenedor.
3. **Paso 4.1: Verificar Conectividad con Neon:**
   En la Shell de Render, ejecuta:
   ```bash
   python -c "import django; django.setup(); from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT version();'); print('Conectado exitosamente a:', cursor.fetchone()[0])"
   ```
   *Debe responder con la versión de PostgreSQL de Neon sin errores.*

4. **Paso 4.2: Aplicar Migraciones en Neon PostgreSQL:**
   Ejecuta:
   ```bash
   python manage.py migrate
   ```
   *Esto creará todas las tablas requeridas por Django y las 7 aplicaciones del sistema (incluyendo las migraciones canónicas de las fases 7.1 a 7.3).*

5. **Paso 4.3: Inicializar los Roles Canónicos:**
   Ejecuta el comando idempotente del sistema:
   ```bash
   python manage.py inicializar_roles
   ```
   *Esto garantizará la existencia de los roles institucionales: Administrador, Coordinador, Docente y Estudiante.*

6. **Paso 4.4: Crear el Superusuario Inicial Institucional:**
   Ejecuta:
   ```bash
   python manage.py crear_superusuario_inicial --username admin.institucional --email admin@uniminuto.edu.co --documento 1000000001 --nombres "Administrador" --apellidos "Institucional"
   ```
   *(El comando te solicitará ingresar una contraseña segura que cumpla con las políticas de validación).*

---

## 7. PASO 5: Lista de Verificación y Pruebas Operativas (Checklist)

Una vez completado el paso 4, abre la URL pública asignada por Render (`https://eventossigae-uniminuto.onrender.com`):

- [ ] **Candado HTTPS Activo:** Verificar que el navegador muestra conexión segura (TLS) sin alertas de certificado.
- [ ] **Archivos Estáticos (WhiteNoise):** Confirmar que los estilos CSS, scripts JavaScript, tipografías e imágenes del sistema cargan correctamente con código de respuesta HTTP 200.
- [ ] **Inicio de Sesión:** Ingresar a `/usuarios/login/` con las credenciales creadas y verificar la redirección al panel principal.
- [ ] **Panel de Administración:** Acceder a `/admin/` y verificar que todos los modelos están registrados y accesibles.
- [ ] **Módulo de Eventos:** Crear un evento de prueba y verificar el guardado en Neon.
- [ ] **Generación de Códigos QR Dinámicos:** Abrir la pantalla de control de asistencia del evento y comprobar que el QR dinámico de 30 segundos se genera en memoria sin errores de disco.
- [ ] **Escaneo QR con Cámara Móvil:** Abrir la URL pública desde un teléfono celular (Android o iOS) y verificar que el navegador solicita permiso y activa la cámara trasera para el escaneo en vivo (habilitado gracias al HTTPS nativo de Render).

---

## 8. Consideraciones Operativas de la Infraestructura

1. **Modo de Suspensión en el Plan Gratuito de Render:**
   - Si no recibe peticiones durante 15 minutos, el contenedor entra en modo de reposo. La siguiente petición puede demorar entre 30 y 50 segundos mientras se reactiva ("cold start").
   - Para demostraciones continuas o eventos en vivo, se recomienda mantener la pestaña abierta o pasar a un plan *Starter* ($7 USD/mes).
2. **Archivos Multimedia y Almacenamiento Efímero:**
   - La arquitectura de EventosSIGAE-UNIMINUTO genera todos los reportes (PDF y Excel) y códigos QR en memoria RAM (`io.BytesIO`) y los transmite por streaming HTTP.
   - Ningún modelo del sistema depende de almacenamiento persistente en disco para archivos subidos por usuarios. El disco efímero de Render es 100% suficiente.
3. **Integridad del Entorno Local:**
   - Tu base de datos local `db.sqlite3` permanece intacta. Al trabajar en local sin definir `DATABASE_URL`, el sistema continuará ejecutándose sobre SQLite con total normalidad.

