# 10. GUÍA DE COMANDOS SEGUROS Y SOLUCIÓN DE PROBLEMAS

**Sistema:** EventosSIGAE-UNIMINUTO  
**Entorno:** Windows 11 (PowerShell) / Linux  
**Propósito:** Manual de operaciones técnicas que distingue comandos de solo lectura de aquellos con efectos de modificación, detalla el uso de la variable `SIGAE_DB_PATH` y ofrece una matriz estructurada para diagnosticar y solucionar incidentes frecuentes durante la ejecución del sistema.

---

## 1. Clasificación de Comandos de Operación

> [!CAUTION]
> **REGLA DE ORO DE INTEGRIDAD DE DATOS:**  
> La base de datos original del proyecto es [`db.sqlite3`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3).  
> **NUNCA** ejecute comandos de migración (`migrate`), inicialización (`inicializar_roles`) o borrado directo contra esta base sin respaldo previo. Para pruebas y demostraciones, utilice exclusivamente la base de demostración [`db.sqlite3.demo`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3.demo) mediante la variable `SIGAE_DB_PATH`.

---

### A. Comandos de Solo Lectura (100% Seguros)

Estos comandos **no alteran** ningún archivo ni modifican registros en la base de datos:

#### 1. Verificación de Integridad de Django
Realiza un chequeo estático de configuración, modelos y relaciones:
```powershell
.\.venv\Scripts\python.exe manage.py check
```

#### 2. Chequeo de Seguridad de Configuración
Examina parámetros de cookies, SSL, cabeceras y hosts:
```powershell
.\.venv\Scripts\python.exe manage.py check --deploy
```

#### 3. Consultar Estado de Migraciones (Solo Lectura)
Muestra qué migraciones están aplicadas (`[X]`) y cuáles pendientes (`[ ]`):
```powershell
.\.venv\Scripts\python.exe manage.py showmigrations
```

#### 4. Consultar Paquetes Instalados
```powershell
.\.venv\Scripts\python.exe -m pip list
```

#### 5. Verificar Hash SHA-256 de la Base de Datos Original
Permite confirmar que `db.sqlite3` no ha sido modificada:
```powershell
Get-FileHash .\db.sqlite3 -Algorithm SHA256
```
*(El hash original certificado de referencia es `C30E8081B9E631C804E6B94081F2F252C82D53D8508E3FFD049608C722F290D0`)*.

#### 6. Ejecutar Suite de Pruebas Automatizadas en Entorno Aislado
Django crea una base de datos temporal en memoria y la destruye al terminar, sin tocar `db.sqlite3` ni `db.sqlite3.demo`:
```powershell
# Pruebas del módulo de asistencia (49 tests)
.\.venv\Scripts\python.exe manage.py test asistencia

# Suite completa del proyecto (135 tests)
.\.venv\Scripts\python.exe manage.py test
```

---

### B. Comandos de Ejecución del Servidor Local

#### 1. Iniciar Servidor en Modo Seguro sobre la Base de Demostración (`db.sqlite3.demo`)
Este comando activa la variable `SIGAE_DB_PATH` apuntando a la base de pruebas y arranca el servidor vinculándolo a todas las interfaces locales (`0.0.0.0:8000`) para permitir el acceso desde la computadora y el celular:

```powershell
$env:SIGAE_DB_PATH = (Resolve-Path .\db.sqlite3.demo).Path; .\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

- **Acceso desde el computador:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Acceso desde el teléfono móvil (en la misma red Wi-Fi):** `http://192.168.1.10:8000/`

#### 2. Iniciar Servidor Exclusivo para Loopback
Si solo se va a probar desde el propio computador:
```powershell
$env:SIGAE_DB_PATH = (Resolve-Path .\db.sqlite3.demo).Path; .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

---

### C. Comandos con Efectos de Modificación (Usar con Precaución)

> [!WARNING]
> Los siguientes comandos escriben información en disco o en la base de datos. Deben ejecutarse conscientemente sobre la base de datos deseada:

#### 1. Inicializar Roles Institucionales Canónicos
Inserta de forma idempotente los roles `Administrador`, `Coordinador`, `Docente` y `Estudiante` si no existen:
```powershell
# Asegúrese de definir SIGAE_DB_PATH antes para aplicarlo sobre la base de demo:
$env:SIGAE_DB_PATH = (Resolve-Path .\db.sqlite3.demo).Path; .\.venv\Scripts\python.exe manage.py inicializar_roles
```

#### 2. Recopilar Archivos Estáticos (Preparación para Producción)
Copia todos los archivos de `static/` a `staticfiles/`:
```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

---

## 2. Matriz de Solución de Problemas Frecuentes

### Problema 1: El celular no abre la página al escanear el QR común de salida
- **Síntoma:** El navegador móvil muestra `ERR_CONNECTION_REFUSED` o *"No se puede acceder al sitio web"*.
- **Causas Posibles:**
  1. El servidor Django se arrancó escuchando solo en `127.0.0.1:8000` en lugar de `0.0.0.0:8000`.
  2. El celular no está conectado a la misma red Wi-Fi que el computador (`FAMILIA_GAMBOA 2`).
  3. El Firewall de Windows bloquea conexiones entrantes porque la red Wi-Fi está clasificada como red pública (`Public`).
- **Solución:**
  1. Verificar que el servidor corra con `runserver 0.0.0.0:8000`.
  2. Conectar el celular a la misma red Wi-Fi local.
  3. En PowerShell como Administrador, cambiar el perfil de la red Wi-Fi a Privada:
     ```powershell
     Set-NetConnectionProfile -InterfaceAlias "Wi-Fi 4" -NetworkCategory Private
     ```

---

### Problema 2: Error HTTP 400 "Bad Request" al ingresar desde otro dispositivo
- **Síntoma:** Al abrir `http://192.168.1.10:8000/` desde el celular, Django muestra error 400.
- **Causa:** La cabecera `Host` enviada por el celular (`192.168.1.10:8000`) no está autorizada en la lista `ALLOWED_HOSTS`.
- **Solución:**  
  Verificar en [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L67) que la lista `ALLOWED_HOSTS` incluya la IP `192.168.1.10`. El proyecto ya cuenta con resolución dinámica de la IP local para evitar este inconveniente en desarrollo.

---

### Problema 3: Error 403 "Verificación CSRF fallida. Solicitud abortada"
- **Síntoma:** Al enviar un formulario por POST (ej. confirmar salida o login), Django responde con error 403 CSRF.
- **Causas Posibles:**
  1. El formulario no incluye la etiqueta `{% csrf_token %}`.
  2. La petición proviene de un origen no incluido en `CSRF_TRUSTED_ORIGINS`.
  3. El navegador móvil tiene deshabilitadas las cookies de sesión.
- **Solución:**  
  1. Asegurar que el formulario HTML contenga `{% csrf_token %}` dentro de las etiquetas `<form>`.
  2. En [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L97-L102), confirmar que `CSRF_TRUSTED_ORIGINS` contenga `http://192.168.1.10:8000`.
  3. Asegurarse de que el navegador móvil acepte cookies para el sitio.

---

### Problema 4: La cámara web no se activa en la consola de asistencia
- **Síntoma:** El cuadro de video permanece negro o muestra el mensaje *"No se pudo acceder a la cámara"*.
- **Causas Posibles:**
  1. El navegador bloqueó el permiso de acceso a la cámara.
  2. Otra aplicación (Teams, Zoom, Meet) tiene bloqueada la cámara en exclusiva.
  3. Políticas de contexto seguro: algunos navegadores restringen `getUserMedia` en conexiones HTTP ajenas a `localhost` o `127.0.0.1`.
- **Solución:**
  1. En el navegador del operador (PC), abrir el icono del candado o configuración junto a la barra de direcciones y seleccionar **"Permitir Cámara"**.
  2. Cerrar aplicaciones de videoconferencia que puedan estar utilizando la cámara web.
  3. Para la consola del operador, navegar siempre desde el propio computador anfitrión en [`http://127.0.0.1:8000/asistencia/evento/1/control/`](http://127.0.0.1:8000/asistencia/evento/1/control/), donde los navegadores siempre consideran `localhost` como contexto seguro.

---

### Problema 5: Error "El código QR de salida presentado es inválido o ha caducado" (HTTP 403)
- **Síntoma:** Al escanear el QR o abrir el enlace, la página rechaza el acceso con error de permiso denegado.
- **Causa:** El token criptográfico en la URL (`?token_evento=...`) fue cortado al escanear, modificado manualmente o corresponde a un evento distinto.
- **Solución:**  
  Escanear nuevamente el código QR asegurando buena iluminación y enfoque completo, o copiar la URL completa generada en la consola del evento.

---

### Problema 6: La hora de salida es rechazada con "La hora de salida debe ser posterior a la hora de entrada"
- **Síntoma:** El sistema rechaza el check-out de un participante indicando inconsistencia temporal.
- **Causa:** La hora del servidor está desfasada o en UTC en lugar de la hora legal de Colombia (`America/Bogota`).
- **Solución:**  
  El código de `asistencia/services.py` ya fue corregido para utilizar `timezone.localtime(timezone.now())`, sincronizándose con la zona horaria `America/Bogota` configurada en `config/settings.py`.

---

## 3. Consulta de Registros y Logs del Sistema

Para diagnosticar el comportamiento de Django en tiempo real:

1. **Salida estándar de la consola:**  
   Al ejecutar `runserver`, cada petición HTTP imprime su método, ruta, código de estado y tiempo de respuesta:
   ```text
   [2026-10-16 15:30:12] INFO [django.server:283] "GET /eventos/ HTTP/1.1" 200 10748
   [2026-10-16 15:30:15] INFO [django.server:283] "POST /asistencia/evento/1/control/ HTTP/1.1" 200 309
   ```
2. **Nivel de detalle de Logs (`LOG_LEVEL`):**  
   Controlado en `config/settings.py` mediante la variable `LOG_LEVEL` (`DEBUG` en desarrollo, `INFO` en producción).
3. **Auditoría en Base de Datos:**  
   Para auditar eventos de negocio específicos (inicios de sesión, cancelaciones, descargas de reportes), consultar la tabla de auditoría ingresando como Administrador a:  
   [`http://127.0.0.1:8000/auditoria/`](http://127.0.0.1:8000/auditoria/).
