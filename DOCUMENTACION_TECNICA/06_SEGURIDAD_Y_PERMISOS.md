# 06. SEGURIDAD, PERMISOS Y CONTROL DE ACCESO

**Sistema:** EventosSIGAE-UNIMINUTO  
**Propósito:** Describir exhaustivamente los mecanismos de autenticación, autorización basada en roles (RBAC), criptografía en códigos QR, protección contra vulnerabilidades web (OWASP Top 10), bitácora de auditoría y hardening configurado.

---

## 1. Autenticación de Usuarios

### A. Almacenamiento Seguro de Contraseñas
- **Mecanismo:** El sistema hereda la arquitectura criptográfica de contraseñas de Django a través del modelo personalizado [`Usuario`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/models.py#L24) (`AbstractUser`).
- **Algoritmo:** **PBKDF2 con SHA-256** (Password-Based Key Derivation Function 2) con miles de iteraciones de estiramiento de clave (*key stretching*).
- **Sal (*Salt*):** Cada contraseña se combina con una sal criptográfica pseudoaleatoria generada individualmente, impidiendo el uso de tablas arcoíris (*Rainbow Tables*). En ningún caso se almacenan contraseñas en texto claro.

### B. Validadores de Contraseñas (`AUTH_PASSWORD_VALIDATORS`)
Configurados en [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L248-L261):
1. `UserAttributeSimilarityValidator`: Impide que la contraseña sea similar al nombre de usuario o correo.
2. `MinimumLengthValidator`: Exige una longitud mínima.
3. `CommonPasswordValidator`: Bloquea contraseñas débiles o de listas comunes (ej. `123456`, `password`).
4. `NumericPasswordValidator`: Impide que la clave esté compuesta enteramente por dígitos.

### C. Gestión de Sesiones HTTP
- Al autenticarse satisfactoriamente mediante [`login_view`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/views.py#L17), Django emite una cookie de sesión criptográfica (`sessionid`).
- La cookie se almacena con la bandera `HttpOnly = True` por omisión, lo que impide que scripts maliciosos de JavaScript en el cliente puedan leer la sesión (mitigación de robo de sesión vía XSS).

---

## 2. Implementación de Roles y Autorización (RBAC)

El sistema utiliza un esquema de **Control de Acceso Basado en Roles** (*Role-Based Access Control*):

```text
[ Solicitud HTTP ]
       │
       ▼
[ @login_required ] ──> ¿Sesión activa? ──(No)──> Redirección a /usuarios/login/?next=...
       │ (Sí)
       ▼
[ Función de Verificación ]
       ├── es_usuario_gestion(user)  --> Administrador, Coordinador, Docente, Staff
       ├── es_administrador(user)    --> Administrador exclusivo
       └── Comprobación de Propiedad --> organizador_id == user.id
       │
       ├──── ¿Cumple permisos? ──(Sí)──> Ejecuta Vista
       │
       └──── (No) ──> raise PermissionDenied("...") ──> HTTP 403 Forbidden
```

### Funciones de Control Verificadas en Código:
1. **`es_usuario_gestion(user)`** ([`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py#L22)):
   - Verifica si el usuario es `is_superuser`, `is_staff` o si su rol institucional en `user.rol.nombre` está en `['Administrador', 'Coordinador', 'Docente']`.
   - Controla el acceso a la creación de eventos y al panel "Mis Eventos".
2. **`es_administrador(user)`** ([`auditoria/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py#L22)):
   - Verifica si el usuario cuenta con el rol exclusivo `Administrador` o superusuario.
   - Restringe la consulta de la bitácora de auditoría de seguridad.
3. **Control de Propiedad (*Object-Level Permissions*):**
   - En la consola de asistencia ([`asistencia/views.py: control_asistencia`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py#L137)), el sistema valida que el usuario sea el organizador del evento (`evento.organizador_id == request.user.id`) o un administrador general. Un docente ajeno no puede tomar asistencia de un evento que no le pertenece.
   - En cancelación de eventos ([`eventos/views.py: cancelar_evento`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py#L262)), solo el organizador o el administrador pueden cancelar.

---

## 3. Matriz de Rutas: Públicas vs. Autenticadas

| Ruta / Patrón URL | Nombre | ¿Requiere Autenticación? | Roles / Restricción de Acceso |
| :--- | :--- | :---: | :--- |
| `/` | `inicio` | No (Pública) | Acceso general a la página de bienvenida |
| `/health/` | `health_check` | No (Pública) | Monitoreo del estado del servicio |
| `/usuarios/login/` | `usuarios:login` | No (Pública) | Si ya tiene sesión, redirige a `inicio` |
| `/usuarios/logout/` | `usuarios:logout` | Sí | Cualquier usuario con sesión activa |
| `/usuarios/password_reset/` | `usuarios:password_reset` | No (Pública) | Solicitud de enlace de recuperación |
| `/eventos/` | `eventos:catalogo` | No (Pública) | Consulta abierta del catálogo institucional |
| `/eventos/<id>/` | `eventos:detalle` | No (Pública) | Información pública del evento |
| `/eventos/crear/` | `eventos:crear` | **Sí** | `Administrador`, `Coordinador`, `Docente` |
| `/eventos/<id>/editar/` | `eventos:editar` | **Sí** | Organizador del evento o Administrador |
| `/eventos/<id>/cancelar/` | `eventos:cancelar` | **Sí** | Organizador del evento o Administrador |
| `/participantes/evento/<id>/inscribirse/` | `participantes:inscribirse` | No / Híbrida | Si está autenticado inscribe perfil; si no, formulario externo |
| `/participantes/mis-inscripciones/` | `participantes:mis_inscripciones` | **Sí** | Propietario de la cuenta (Estudiantes, etc.) |
| `/participantes/inscripcion/<id>/cancelar/` | `participantes:cancelar_inscripcion` | **Sí** | Propietario de la inscripción |
| `/asistencia/inscripcion/<id>/pase/` | `asistencia:pase_digital` | No / Token | Requiere sesión del dueño O presentar `?token=` firmado |
| `/asistencia/inscripcion/<id>/qr-imagen/` | `asistencia:qr_imagen` | No / Token | Requiere sesión del dueño O presentar `?token=` firmado |
| `/asistencia/evento/<id>/control/` | `asistencia:control_asistencia` | **Sí** | Organizador del evento o Administrador |
| `/asistencia/evento/<id>/salida/` | `asistencia:salida_evento_publica` | No / Token | Requiere escanear el QR con token firmado del evento |
| `/asistencia/evento/<id>/toggle-salidas/` | `asistencia:toggle_salidas_evento` | **Sí** | Organizador del evento o Administrador |
| `/reportes/evento/<id>/planilla-pdf/` | `reportes:planilla_asistencia_pdf` | **Sí** | Organizador o Personal de Gestión |
| `/reportes/evento/<id>/reporte-pdf/` | `reportes:reporte_consolidado_pdf` | **Sí** | Organizador o Personal de Gestión |
| `/analitica/` | `analitica:dashboard` | **Sí** | Personal de Gestión (`es_usuario_gestion`) |
| `/auditoria/` | `auditoria:consulta_auditoria` | **Sí** | **Exclusivo Administrador** |
| `/admin/` | `admin:index` | **Sí** | `is_staff = True` o `is_superuser = True` |

---

## 4. Seguridad Criptográfica en Códigos QR

El sistema descarta deliberadamente el error común de almacenar datos sensibles (cédulas, nombres, correos) en texto plano dentro de los códigos QR.

### A. Pases Digitales Individuales (Entrada)
- **Generación:** [`asistencia/services.py: generar_token_qr`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L18).
- **Mecanismo:** `django.core.signing.dumps(payload, salt=SALT_QR)`.
- **Estructura del Payload:**
  ```python
  payload = {
      'ins': inscripcion.pk,
      'evt': inscripcion.evento_id,
      'f_ins': inscripcion.fecha_inscripcion.isoformat()
  }
  ```
- **Firma:** Se genera un HMAC-SHA256 utilizando la clave secreta del proyecto (`SECRET_KEY`) y una sal específica (`sigae-asistencia-qr-salt-v1`).
- **Propiedades de Seguridad:**
  1. **Privacidad:** No expone datos personales en el código de barras bidimensional.
  2. **Integridad:** Cualquier intento de alterar el número de inscripción o el ID del evento invalida la firma criptográfica (`BadSignature`).
  3. **No Intercambiabilidad:** Un pase de un evento jamás podrá ser validado en un evento distinto, pues el payload verifica `payload['evt'] == evento.pk`.

### B. Código QR Común de Salida (Salida Móvil)
- **Generación:** [`asistencia/services.py: generar_token_salida_evento`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L47).
- **Sal Aislada:** Utiliza `SALT_SALIDA_EVENTO = 'sigae-salida-evento-v1'`.
- **Doble Factor de Seguridad en la Página de Salida:**
  Al escanear el QR común, la página web no confía ciegamente solo en un número de documento. Exige:
  - **Número de Documento** + **Correo Electrónico registrado en la inscripción**.
  - Si un atacante conoce la cédula de un compañero pero desconoce su correo registrado, el sistema rechaza la salida con alerta: *"El correo electrónico ingresado no coincide con el registrado en la inscripción"*.

---

## 5. Protección contra Ataques Comunes (OWASP Top 10)

| Vulnerabilidad | Mecanismo de Defensa Implementado | Ubicación en Código |
| :--- | :--- | :--- |
| **CSRF (Cross-Site Request Forgery)** | Middleware `CsrfViewMiddleware`. Inyección de token `{% csrf_token %}` en todos los formularios POST. Cabecera `X-CSRFToken` en peticiones AJAX/Fetch. Lista blanca restrictiva en `CSRF_TRUSTED_ORIGINS`. | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L91-L114) |
| **XSS (Cross-Site Scripting)** | Auto-escapado contextual activado en el motor de plantillas de Django. Cabecera de respuesta `SECURE_BROWSER_XSS_FILTER = True`. JSON empaquetado de forma segura sin interpolación directa. | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L348) |
| **Inyección SQL** | Uso exclusivo del ORM de Django con consultas parametrizadas. Ninguna vista concatena cadenas SQL crudas. | Todo el backend |
| **Clickjacking** | Cabecera HTTP `X_FRAME_OPTIONS = 'DENY'`. Impide que el portal sea incrustado dentro de `<iframe>` en sitios ajenos. | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L350) |
| **MIME-Sniffing** | Cabecera `SECURE_CONTENT_TYPE_NOSNIFF = True`. Fuerza a los navegadores a respetar el `Content-Type` declarado. | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L349) |
| **Host Header Injection** | `ALLOWED_HOSTS` estricto. En desarrollo solo admite loopback y la IP local `192.168.1.10`. En producción prohíbe el comodín `'*'`. | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L60-L90) |
| **Condiciones de Carrera** | Uso de transacciones atómicas (`transaction.atomic()`) y bloqueos de fila a nivel de base de datos (`select_for_update()`) en check-in e inscripciones. | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L106), [`participantes/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/views.py#L73) |

---

## 6. Bitácora de Auditoría y Trazabilidad de Seguridad

El modelo [`auditoria.models.Auditoria`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/models.py#L5) implementa el principio de **No Repudio**:
- Registra automáticamente:
  - **`usuario`**: Objeto del usuario autenticado (o `None` si es acción anónima).
  - **`accion`**: Código unificado de la operación (`INICIAR_SESION`, `CERRAR_SESION`, `CREAR_EVENTO`, `CANCELAR_EVENTO`, `REGISTRAR_ASISTENCIA`, `DESCARGAR_PLANILLA_PDF`, `CONSULTA_AUDITORIA`, etc.).
  - **`modulo`**: Nombre del módulo afectado.
  - **`registro_afectado`**: Identificador sintético del registro impactado.
  - **`ip`**: Dirección IP del cliente, resuelta mediante `get_client_ip(request)` considerando cabeceras de proxy inverso (`HTTP_X_FORWARDED_FOR`).
  - **`fecha`**: Marca temporal generada por el servidor con zona horaria de Colombia.
- **Inmutabilidad:** La vista de auditoría no expone ningún método para modificar o borrar registros.

---

## 7. Clasificación del Estado de Seguridad del Proyecto

Para la sustentación oral, es fundamental distinguir tres niveles de seguridad:

### 1. Seguridad Comprobada y Activa en el Código:
- [x] Autenticación PBKDF2-SHA256 con sal individual.
- [x] Control de roles en vistas (`es_usuario_gestion`, `es_administrador`).
- [x] Tokens HMAC-SHA256 en pases QR individuales y QR común de salida.
- [x] Doble factor seguro (Documento + Correo) para salida móvil sin cuenta.
- [x] Transacciones atómicas y `select_for_update()` para evitar dobles registros.
- [x] Protección CSRF, XSS, Clickjacking y Content-Type sniffing.
- [x] Bitácora inmutable de auditoría con captura de IP.

### 2. Seguridad Configurada Parcialmente (Preparada para Producción):
- [x] Bloqueo automático si se intenta `DJANGO_ENV=production` con `DEBUG=True` (eleva `ImproperlyConfigured`).
- [x] Rechazo de `SECRET_KEY` inseguras o por defecto al iniciar en producción.
- [x] Parámetros SSL/HTTPS (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`) preparados para activarse mediante variables de entorno cuando se instalen certificados TLS válidos.

### 3. Aspectos Pendientes o Recomendaciones Futuras:
- [ ] **Certificado TLS / HTTPS:** En el entorno de pruebas local se utiliza HTTP (`http://192.168.1.10:8000/`); para producción en Internet se requiere un certificado SSL/TLS (ej. Let's Encrypt o institucional).
- [ ] **Autenticación en Dos Pasos (2FA / OTP):** Actualmente el login de usuarios se basa en contraseña; podría integrarse un segundo factor con código por correo o app autenticadora.
- [ ] **Rate Limiting:** Se recomienda añadir `django-ratelimit` a nivel de servidor o Nginx para limitar intentos de fuerza bruta en `/usuarios/login/`.
