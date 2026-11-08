# 04. DOCUMENTACIÓN DETALLADA DE FLUJOS FUNCIONALES

**Sistema:** EventosSIGAE-UNIMINUTO  
**Propósito:** Describir paso a paso cada uno de los 14 procesos implementados en el sistema, detallando la interacción del usuario, las rutas, vistas, modelos, validaciones de seguridad, respuestas y manejo de errores.

---

## Flujo 1: Inicio de Sesión y Autenticación

```text
[ Usuario ] ──(Credenciales)──> /usuarios/login/ ──> [ login_view ]
                                                            │
                            ┌───────────────────────────────┴───────────────────────────────┐
                            ▼                                                               ▼
                     (Válidas)                                                      (Inválidas)
        - Crea Sesión HTTP                                              - Muestra mensaje de error
        - Registra Auditoría (INICIAR_SESION)                           - Permanece en login.html
        - Redirige a next_url o 'inicio'
```

- **Acción del Usuario:** Ingresa su nombre de usuario (`username`) y contraseña institucional en el formulario de login.
- **URL Interviniente:** `/usuarios/login/` (Nombre: `usuarios:login`).
- **Vista / Función:** [`usuarios.views.login_view`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/views.py#L17).
- **Validaciones Realizadas:**
  1. Si el usuario ya está autenticado, lo redirige de inmediato a la página de inicio.
  2. `LoginForm` valida que los campos no estén vacíos y utiliza el backend de autenticación de Django (`authenticate()`) para verificar el hash de la contraseña (`PBKDF2SHA256`).
  3. `url_has_allowed_host_and_scheme`: Valida que el parámetro `?next=` no apunte a dominios maliciosos externos (previene ataques de *Open Redirect*).
- **Modelos que Intervienen:** [`usuarios.models.Usuario`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/models.py#L24), [`auditoria.models.Auditoria`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/models.py#L5).
- **Datos Consultados / Guardados:** Consulta la tabla `usuarios_usuario` por `username`; si es exitoso, crea un registro en `auditoria_auditoria` con acción `INICIAR_SESION`, ID del usuario y la IP del cliente.
- **Plantilla / Respuesta:**
  - GET: Renderiza [`templates/usuarios/login.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/usuarios/login.html).
  - POST exitoso: Redirección HTTP 302 a `next_url` o `'inicio'`.
- **Controles de Seguridad:** Protección CSRF obligatoria (`{% csrf_token %}`), cookies de sesión `HttpOnly`, bloqueo de sesiones concurrentes inválidas.
- **Manejo de Errores:** Si las credenciales fallan, agrega un mensaje flash de nivel error: *"Nombre de usuario o contraseña incorrectos. Por favor verifique sus credenciales."* y vuelve a renderizar el formulario sin revelar si el usuario existe o no.

---

## Flujo 2: Roles, Permisos y Control de Acceso

- **Acción del Usuario:** Intenta navegar hacia módulos restringidos (ej. creación de eventos, consola de asistencia, bitácora de auditoría, panel analítico).
- **Controladores de Acceso:**
  - `login_required`: Decorador estándar de Django para exigir sesión iniciada.
  - `es_usuario_gestion(user)`: Función utilitaria en [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py#L22) que comprueba si el usuario es Superusuario, Staff o posee rol de `Administrador`, `Coordinador` o `Docente`.
  - `es_administrador(user)`: Función en [`auditoria/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py#L22) que restringe el acceso exclusivamente a usuarios con rol `Administrador`.
- **Reglas de Acceso Comprobadas:**
  - Si un usuario no autenticado intenta ingresar a `/eventos/crear/` o `/asistencia/evento/1/control/`, es redirigido con HTTP 302 hacia `/usuarios/login/?next=...`.
  - Si un estudiante autenticado intenta acceder a la consola de asistencia o al panel de auditoría, el sistema eleva `PermissionDenied` que Django traduce en una respuesta **HTTP 403 Forbidden**.
- **Modelos que Intervienen:** `usuarios.Usuario`, `usuarios.Rol`.

---

## Flujo 3: Creación y Administración de Eventos

- **Acción del Usuario (Docente / Organizador):** Ingresa al panel de gestión, pulsa "Crear Evento", completa el formulario institucional y guarda.
- **URLs Intervinientes:**
  - `/eventos/crear/` (Nombre: `eventos:crear`).
  - `/eventos/<id_evento>/editar/` (Nombre: `eventos:editar`).
  - `/eventos/<id_evento>/cancelar/` (Nombre: `eventos:cancelar`).
- **Vistas / Funciones:** [`eventos.views.crear_evento`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py#L179), `editar_evento`, `cancelar_evento`.
- **Validaciones Realizadas:**
  1. Permiso de usuario de gestión (`es_usuario_gestion`).
  2. Validación de fechas: `clean()` comprueba que `hora_fin > hora_inicio`.
  3. Validación de aforo: El campo `cupo` debe ser un entero positivo o nulo (aforo ilimitado).
  4. En cancelación: El motivo es obligatorio (`motivo_cancelacion.strip()`), el evento no debe estar ya finalizado ni cancelado.
- **Modelos que Intervienen:** [`eventos.models.Evento`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py#L53), `CategoriaEvento`, `Auditoria`.
- **Datos Guardados:** Crea/actualiza fila en `eventos_evento` asignando `organizador = request.user`. Registra en `auditoria_auditoria` con acción `CREAR_EVENTO`, `EDITAR_EVENTO` o `CANCELAR_EVENTO`.
- **Plantilla / Respuesta:** [`templates/eventos/form_evento.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/eventos/form_evento.html) y redirección al detalle del evento.

---

## Flujo 4: Registro de Participantes Internos (Comunidad UNIMINUTO)

- **Acción del Usuario:** Un estudiante o docente autenticado consulta el catálogo o el detalle de un evento y hace clic en **"Inscribirme a este Evento"**.
- **URL Interviniente:** `/participantes/evento/<id_evento>/inscribirse/` (Nombre: `participantes:inscribirse`).
- **Vista / Función:** [`participantes.views.inscribirse_evento`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/views.py#L47).
- **Validaciones Realizadas:**
  1. El evento debe estar en estado `PUBLICADO`.
  2. Aforo disponible: `total_activos < evento.cupo`. Si se llena, rechaza con mensaje de cupo agotado.
  3. Evitar duplicidad: Consulta si ya existe una inscripción para `(evento, participante)`. Si ya está en estado `ACTIVA`, notifica que ya está inscrito. Si estaba `CANCELADA`, la reactiva atómicamente.
- **Modelos que Intervienen:** [`participantes.models.Participante`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/models.py#L14), [`Inscripcion`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/models.py#L91), `Evento`, `Auditoria`.
- **Datos Guardados:** Garantiza el perfil en `participantes_participante` mediante `obtener_o_crear_perfil_participante(user)` y crea la fila en `participantes_inscripcion` con estado `ACTIVA`.
- **Plantilla / Respuesta:** Redirección HTTP 302 a [`/participantes/mis-inscripciones/`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/views.py#L183) con mensaje flash de bienvenida.

---

## Flujo 5: Registro de Participantes Externos (Sin Cuenta Institucional)

- **Acción del Usuario:** Una persona externa (sin sesión iniciada) visita el enlace público del evento y completa el formulario de inscripción con sus datos.
- **URL Interviniente:** `/participantes/evento/<id_evento>/inscribirse/` (misma URL inteligente que atiende peticiones anónimas).
- **Vista / Función:** `participantes.views.inscribirse_evento` (rama `CASO B`).
- **Validaciones Realizadas:**
  1. Estado del evento y cupo disponible.
  2. `InscripcionExternaForm`: Valida formato de cédula, correo electrónico válido, nombres, apellidos y teléfono.
  3. Comprueba si el documento ya existe como participante externo (`usuario__isnull=True`) para reutilizar el perfil sin duplicar personas en la base de datos.
- **Modelos que Intervienen:** `Participante` (con `tipo='EXTERNO'`, `usuario=None`), `Inscripcion`, `Auditoria`.
- **Datos Guardados:** Crea/actualiza `Participante`, crea `Inscripcion` y registra `INSCRIBIR_EXTERNO` en auditoría.
- **Plantilla / Respuesta:** Al finalizar, genera de inmediato el token firmado del QR y redirige automáticamente al participante a su **Pase Digital**:  
  `/asistencia/inscripcion/<id>/pase/?token=<token_firmado>`.

---

## Flujo 6: Generación de Códigos QR

El sistema implementa dos tipos de códigos QR con funciones totalmente distintas y separadas criptográficamente:

### A. Pase Digital Individual (Entrada del Participante)
- **Generador:** [`asistencia.services.generar_token_qr(inscripcion)`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L18).
- **Algoritmo:** HMAC-SHA256 (`django.core.signing.dumps`) utilizando la sal criptográfica privada:  
  `SALT_QR = 'sigae-asistencia-qr-salt-v1'`.
- **Payload:** `{'ins': inscripcion.pk, 'evt': inscripcion.evento_id, 'f_ins': fecha_iso}`.
- **Seguridad:** No incluye cédula, nombres ni correo. Un atacante no puede modificar el ID de la inscripción ni usar el token en otro evento sin romper la firma criptográfica.
- **Emisión Gráfica:** `generar_imagen_qr_bytes(token)` utiliza la librería `qrcode` y `Pillow` para devolver bytes PNG en memoria.
- **Visualización:**
  - Página HTML con diseño de credencial en [`asistencia/views.py: pase_digital`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py#L42).
  - Descarga directa de archivo binario PNG en [`asistencia/views.py: descargar_qr_imagen`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py#L106).

### B. QR Común de Salida del Evento
- **Generador:** [`asistencia.services.generar_token_salida_evento(evento)`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L47).
- **Algoritmo:** HMAC-SHA256 con sal específica:  
  `SALT_SALIDA_EVENTO = 'sigae-salida-evento-v1'`.
- **Payload:** `{'evt': evento.pk, 'f': str(evento.fecha)}`.
- **URL Incrustada:** Construida mediante `construir_url_salida_evento(request, evento)`, que reemplaza direcciones de loopback por la IP de red local del equipo (`http://192.168.1.10:8000/asistencia/evento/<id>/salida/?token_evento=<token>`) para que sea accesible desde celulares.

---

## Flujo 7: Lectura y Escaneo de Códigos QR (Consola de Asistencia)

```text
[ Cámara Web del PC ] ──> Video Stream ──> Canvas HTML5 ──> [ jsQR.min.js ]
                                                                   │
                                                                   ▼ (Detecta QR)
[ Consola Operador ] <── JSON Response ── AJAX POST /asistencia/evento/<id>/control/
```

- **Acción del Usuario (Organizador / Operador):** Abre la consola de control en el computador, autoriza el permiso de la cámara web en el navegador y coloca el pase digital del asistente frente al lente.
- **URL Interviniente:** `/asistencia/evento/<id_evento>/control/` (Nombre: `asistencia:control_asistencia`).
- **Tecnología en el Navegador:**
  - `navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })` captura el flujo de video en vivo.
  - La función en bucle `tick()` dibuja cada fotograma en un `<canvas>` oculto.
  - [`jsQR(imageData.data, width, height)`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/js/jsQR.min.js) analiza la imagen en milisegundos buscando patrones de alineación QR.
  - Al detectar un código, extrae la cadena de texto, emite un sonido acústico de retroalimentación vía `AudioContext` y despacha una solicitud asíncrona `fetch()` tipo POST con la cabecera `X-CSRFToken`.

---

## Flujo 8: Registro de Ingreso (Check-in)

- **Receptor:** [`asistencia.views.control_asistencia`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py#L137) llamando a [`asistencia.services.registrar_asistencia_llegada`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L82).
- **Validaciones de Seguridad y Negocio:**
  1. **Separación de Códigos QR:** Si el operador escanea por error el QR común de salida en el lector de llegada, el sistema detecta la sal de salida y responde:  
     `codigo='QR_SALIDA_COMUN_NO_ES_PASE'`, alertando: *"El código escaneado corresponde al QR común de SALIDA del evento. Este lector es exclusivo para escanear pases personales de entrada."*
  2. **Verificación Criptográfica:** Decodifica el token con `decodificar_token_qr`. Si la firma fue manipulada o expiró, rechaza con HTTP 400.
  3. **Aislamiento por Evento:** Comprueba que `payload['evt'] == evento.pk`. Un token de otro evento es rechazado de inmediato.
  4. **Estado de la Inscripción:** La inscripción debe estar en estado `ACTIVA`.
  5. **Bloqueo de Duplicados (Transacción Atómica):** Ejecuta `select_for_update()` sobre la inscripción. Si ya existe un registro en `asistencia_asistencia` con `estado='REGISTRADA'`, rechaza la solicitud indicando la hora y fecha en que el participante ya ingresó.
- **Modelos que Intervienen:** [`asistencia.models.Asistencia`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/models.py#L17), `Inscripcion`, `Auditoria`.
- **Datos Guardados:** Inserta registro en `asistencia_asistencia` con `hora_entrada = timezone.localtime().time()`, `metodo='QR'`, `estado='REGISTRADA'`. Inserta en `auditoria_auditoria` (`REGISTRAR_ASISTENCIA`).
- **Respuesta:** JSON con `exito=True`, nombre del participante, tipo institucional y hora de ingreso. La interfaz actualiza la fila del asistente sin recargar la página.

---

## Flujo 9: Registro de Salida (Check-out)

El sistema provee dos mecanismos para el check-out:

### A. Check-out Manual por el Operador
En la consola de control, el operador puede buscar a un participante y presionar el botón "Salida".

### B. Check-out Móvil Autónomo por QR Común (Flujo Principal)
1. **Habilitación:** El organizador presiona "Habilitar Registro de Salidas" en su consola (`/asistencia/evento/<id>/toggle-salidas/`).
2. **Proyección:** Se despliega en pantalla o proyector el QR común de salida.
3. **Escaneo Móvil:** El participante escanea el código con la cámara de su celular y abre en el navegador móvil la URL:  
   `/asistencia/evento/<id>/salida/?token_evento=<token>`.
4. **Validación del Enlace:**
   - Si no hay token o está adulterado $\rightarrow$ **HTTP 403 Forbidden**.
   - Si las salidas no han sido habilitadas $\rightarrow$ La página avisa: *"El registro de salidas para este evento se encuentra cerrado o no ha sido habilitado por el organizador"*.
5. **Identificación Segura:**
   - **Usuario con Sesión:** El sistema detecta su usuario y ofrece el botón explícito *"Confirmar Mi Salida"*.
   - **Participante Externo (Doble Factor):** Solicita Número de Documento y Correo Electrónico. Si el documento existe pero el correo no coincide con el registrado en la inscripción, rechaza la operación impidiendo que un tercero marque la salida de otra persona.
6. **Ejecución Atómica:** Llama a [`registrar_asistencia_salida`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L193).
   - Valida que exista una `Asistencia` previa con `hora_entrada`. Si no ingresó, rechaza: *"El participante no cuenta con un registro de entrada previo válido"*.
   - Valida que no tenga ya `hora_salida`. Si ya salió, rechaza: *"La salida de ... ya fue registrada a las HH:MM"*.
   - Guarda `hora_salida = timezone.localtime().time()`.
   - Ejecuta `asistencia.clean()` para validar la coherencia temporal.
   - Calcula la permanencia y registra auditoría.
7. **Confirmación Visual:** La pantalla del celular se torna verde mostrando el mensaje de éxito y el tiempo total de permanencia (ej. *"Permanencia: 1h 45m"*).

---

## Flujo 10: Cálculo de Duración de Asistencia (Permanencia)

- **Ubicación:** Propiedad `@property def permanencia(self)` en [`asistencia/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/models.py#L81).
- **Fórmula Matemática:**
  $$\Delta t = \text{datetime}(\text{fecha}, \text{hora\_salida}) - \text{datetime}(\text{fecha}, \text{hora\_entrada})$$
- **Manejo de Cruce de Medianoche (Eventos Nocturnos / Trasnoche):**
  Si $\text{hora\_salida} < \text{hora\_entrada}$, el sistema evalúa si corresponde a una transición verosímil ($\text{hora\_entrada} \ge 18:00$ y $\text{hora\_salida} \le 08:00$). De cumplirse, suma automáticamente 1 día a la fecha de salida:
  `salida_dt += datetime.timedelta(days=1)`
- **Estructura Retornada:**
  ```python
  {
      'horas': 1,
      'minutos': 45,
      'total_minutos': 105,
      'texto': '1h 45m',
      'cruce_medianoche': False
  }
  ```
- **Cálculo de Promedio Global:** La función `calcular_permanencia_promedio(evento)` en `asistencia/services.py` calcula la media aritmética de todos los asistentes con salida registrada en el evento.

---

## Flujo 11: Consulta de Participantes y Asistencias

- **Ubicación:** Consola de asistencia ([`asistencia/views.py: control_asistencia`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py#L137)).
- **Métricas en Vivo:**
  - `total_inscritos`: Total de inscripciones activas.
  - `total_asistieron`: Participantes con entrada registrada.
  - `total_sin_salida`: Participantes presentes que no han marcado salida.
  - `total_salidas`: Participantes con check-out completado.
  - `permanencia_promedio`: Tiempo medio de estadía del público.
- **Filtros Rápidos en la Interfaz:**
  - `todos`: Lista completa de inscritos.
  - `asistieron`: Solo quienes ingresaron.
  - `ausentes`: Inscritos que no llegaron al evento.
  - `sin_salida`: Participantes que están adentro del recinto.
  - `salieron`: Participantes que ya completaron su ciclo.

---

## Flujo 12: Generación de Reportes Oficiales

- **Acción del Usuario:** El organizador hace clic en "Descargar Planilla PDF" o "Reporte Consolidado PDF" desde el menú del evento.
- **URLs Intervinientes:**
  - `/reportes/evento/<id>/planilla-pdf/`
  - `/reportes/evento/<id>/reporte-pdf/`
- **Vistas / Servicios:** [`reportes.views.descargar_planilla_asistencia_pdf`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/views.py#L45) llamando a [`reportes.services.generar_pdf_planilla_asistencia`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py#L100).
- **Proceso Interno (Stateless):**
  1. Consulta los datos de la base de datos optimizando con `select_related`.
  2. Crea un búfer en memoria `io.BytesIO()`.
  3. Dibuja el PDF con ReportLab (encabezado UNIMINUTO, metadatos, tabla de participantes con estados y casillas de firma).
  4. Registra auditoría de la descarga (`DESCARGAR_PLANILLA_PDF`).
  5. Retorna un `HttpResponse` con cabecera `Content-Type: application/pdf` y `Content-Disposition: attachment; filename="Planilla_...pdf"`.
- **Seguridad:** Requiere que el usuario sea el organizador del evento o tenga rol de gestión (`Administrador`, `Coordinador`, `Docente`).

---

## Flujo 13: Auditoría y Trazabilidad

- **Acción del Administrador:** Accede a `/auditoria/` para supervisar la actividad del sistema.
- **Vista:** [`auditoria.views.consulta_auditoria`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py#L34).
- **Controles:**
  - Acceso restringido exclusivamente a usuarios con rol `Administrador` (HTTP 403 para cualquier otro usuario).
  - Interfaz de **solo lectura**: no permite editar, modificar ni eliminar registros de la bitácora.
  - Filtros por Módulo (`USUARIOS`, `EVENTOS`, `PARTICIPANTES`, `ASISTENCIA`, `REPORTES`, `ANALITICA`), Acción, Usuario y Rango de Fechas.
  - Paginación segura a 25 registros por página.
  - La propia consulta de auditoría queda registrada en la bitácora (`CONSULTA_AUDITORIA`).

---

## Flujo 14: Endpoint de Salud del Sistema (Health Check)

- **Acción:** Petición HTTP realizada por balanceadores de carga, scripts de monitoreo o administradores.
- **URL Interviniente:** `/health/` (Pública).
- **Vista:** [`config.views.health_check`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/views.py#L9).
- **Funcionamiento Técnico:**
  1. Ejecuta una consulta ligera de conectividad sobre la conexión activa de Django: `cursor.execute("SELECT 1;")`.
  2. Si la base de datos responde `1`, retorna **HTTP 200 OK**:
     ```json
     {
       "status": "healthy",
       "database": "connected",
       "timestamp": "2026-10-16T20:30:00.000000+00:00"
     }
     ```
  3. Si la base de datos no responde o genera una excepción, captura el error y retorna **HTTP 503 Service Unavailable** con `"status": "unhealthy"`.
- **Seguridad:** En ningún caso expone nombres de tablas, contraseñas, IPs internas ni trazas de error (Tracebacks).
