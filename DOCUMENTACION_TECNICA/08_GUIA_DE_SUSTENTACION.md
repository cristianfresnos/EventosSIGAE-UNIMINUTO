# 08. GUÍA INTEGRAL DE SUSTENTACIÓN Y DEFENSA ACADÉMICA

**Sistema:** EventosSIGAE-UNIMINUTO  
**Destinatario:** Estudiante ponente ante jurados y docentes evaluadores  
**Propósito:** Proveer un guion de estudio estructurado con discursos de apertura, respuestas fundamentadas a preguntas difíciles de evaluación técnica, tabla de localización rápida de cambios y un guion de demostración en vivo.

---

## 1. Discursos de Apertura para la Sustentación

### A. Explicación Breve de Apertura (2 Minutos)

> *"Buenos días, profesor y miembros del jurado.*
>
> *Hoy presento **EventosSIGAE-UNIMINUTO**, el Sistema Integrado de Gestión de Asistencia y Eventos diseñado para resolver una problemática recurrente en la universidad: el control manual de asistencia en papel, las filas lentas en auditorios, la falta de control de aforos y el desconocimiento del tiempo real de permanencia de los asistentes.*
>
> *Para resolver esto, desarrollé una plataforma web modular en **Django 6.1** y **Python 3.13** que cubre de principio a fin el ciclo de vida de los eventos institucionales:*
>
> *1. **Gestión e Inscripción:** Los docentes publican eventos con cupos limitados. La comunidad UNIMINUTO se inscribe con su cuenta institucional y el público externo mediante un formulario público. Al inscribirse, el sistema les emite un **Pase Digital con un código QR firmado con HMAC-SHA256**, garantizando que nadie pueda falsificar entradas ni exponer cédulas en el código.*
>
> *2. **Acreditación sin Contacto en Vivo:** El día del evento, el organizador utiliza la cámara web de su computador para escanear pases a través de la librería `jsQR`, registrando ingresos en milisegundos. Al terminar la jornada, se proyecta un **QR común de salida** que los asistentes escanean desde sus teléfonos celulares para confirmar su salida con un doble factor seguro (cédula y correo), lo que permite al sistema calcular con exactitud la **permanencia efectiva** de cada participante.*
>
> *3. **Reportes y Auditoría:** La plataforma genera actas oficiales en PDF mediante `ReportLab` en memoria sin sobrecargar el servidor, exporta estadísticas a Excel y mantiene una **bitácora inmutable de auditoría** con registro de IP y usuario.*
>
> *El sistema cuenta con 135 pruebas automatizadas aprobadas y arquitectura de base de datos desacoplada para SQLite y PostgreSQL."*

---

### B. Explicación Técnica Profunda (5 Minutos)

> *"Profundizando en la arquitectura técnica del proyecto:*
>
> *Decidí estructurar el sistema siguiendo el patrón **MVT (Model-View-Template)** de Django, pero introduciendo una **capa de servicios desacoplada (`services.py`)**. Esto evita el antipatrón de 'vistas gordas' y concentra la lógica de negocio compleja fuera de los controladores HTTP.*
>
> *El backend está dividido en siete aplicaciones cohesivas:*
> - *`usuarios`: Extiende `AbstractUser` para centralizar la autenticación PBKDF2 y el catálogo de roles institucionales.*
> - *`eventos`: Administra el catálogo, la categorización y las reglas de aforo, controlando mediante validaciones a nivel de modelo que la hora de fin sea estrictamente posterior a la de inicio.*
> - *`participantes`: Modela la relación Many-to-Many entre eventos y personas físicas mediante la tabla intermedia `Inscripcion`, la cual cuenta con una restricción única `(evento, participante)` a nivel de motor de base de datos para impedir duplicidades.*
> - *`asistencia`: Es el núcleo operativo. Se vincula 1:1 con la inscripción y almacena `hora_entrada` y `hora_salida`. La propiedad calculada `.permanencia` resuelve la diferencia en minutos y horas, incluyendo la lógica de cruce de medianoche para eventos nocturnos. Implementa transacciones atómicas y bloqueos pesimistas de fila con `select_for_update()` para blindar el check-in contra condiciones de carrera concurrentes.*
> - *`reportes`: Diseñado bajo una arquitectura **stateless**. No almacenamos PDFs estáticos en disco; en su lugar, la librería `ReportLab` dibuja las tablas vectoriales en un búfer de memoria RAM (`io.BytesIO`) y las transmite directamente al navegador mediante un flujo HTTP binario.*
> - *`analitica`: Utiliza agregaciones optimizadas del ORM de Django (`Count`, `Q`, `Avg`) para calcular aforos y porcentajes de asistencia, exportando a Excel con `openpyxl` y a CSV con codificación UTF-8 BOM.*
> - *`auditoria`: Bitácora inmutable que captura cada acción crítica con la IP real del cliente resolviendo proxies inversos.*
>
> *En seguridad web, el sistema cumple con las directrices OWASP: protección CSRF activa, prevención de Clickjacking con `X_FRAME_OPTIONS = 'DENY'`, cookies `HttpOnly`, y los códigos QR están firmados mediante HMAC con sales diferenciadas (`SALT_QR` y `SALT_SALIDA_EVENTO`).*
>
> *Para garantizar la calidad del software, implementé **135 pruebas automatizadas** que cubren desde validaciones temporales hasta intentos de manipulación de tokens y concurrencia. El sistema está preparado para producción en Linux mediante Gunicorn y Nginx con soporte nativo para PostgreSQL 16."*

---

## 2. Banco de Preguntas de Evaluación y Respuestas Sugeridas

### Pregunta 1: ¿Por qué eligió Django en lugar de Flask, FastAPI o Express?
**Respuesta:**  
*"Elegí Django 6.1 porque sigue la filosofía 'baterías incluidas' (*batteries included*), ofreciendo de forma nativa un sistema de autenticación robusto, un ORM con migraciones controladas, protección integrada contra vulnerabilidades comunes (CSRF, XSS, inyección SQL, Clickjacking) y un panel administrativo maduro. Para un sistema institucional como SIGAE, donde la integridad de datos, la seguridad en roles y la trazabilidad son prioritarias, Django reduce drásticamente el riesgo de vulnerabilidades frente a microframeworks donde la seguridad debe ensamblarse manualmente."*

---

### Pregunta 2: ¿Qué arquitectura utiliza el proyecto y cómo está organizada?
**Respuesta:**  
*"Utiliza el patrón **MVT (Model-View-Template)** característico de Django, complementado con una **capa de servicios desacoplada (`services.py`)**. Los modelos representan las tablas y validan restricciones de datos; las plantillas manejan la presentación visual en el navegador; las vistas reciben las solicitudes HTTP y coordinan la ejecución; y los archivos de servicios (`asistencia/services.py`, `reportes/services.py`, `analitica/services.py`) albergan la lógica de negocio pesada, como la firma criptográfica de QR, el ensamblado de PDFs y los cálculos estadísticos."*

---

### Pregunta 3: ¿Qué diferencia existe entre un Modelo, una Vista, una URL y una Plantilla en su código?
**Respuesta:**  
- **URL ([`eventos/urls.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/urls.py)):** Es el enrutador que mapea una dirección web con una función o clase controladora.
- **Vista ([`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py)):** Es la función en Python que recibe la petición HTTP (`request`), comprueba permisos, invoca servicios o consulta modelos, y decide qué respuesta devolver.
- **Modelo ([`eventos/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py)):** Es la clase en Python que define la estructura de una tabla en la base de datos mediante el ORM de Django.
- **Plantilla ([`templates/eventos/catalogo.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/eventos/catalogo.html)):** Es el archivo HTML con etiquetas de Django (`DTL`) que renderiza los datos en pantalla para el usuario.

---

### Pregunta 4: ¿Dónde se almacena la información y cómo se gestiona la conexión a la base de datos?
**Respuesta:**  
*"En desarrollo local, la información se almacena en SQLite mediante archivos locales (`db.sqlite3` y `db.sqlite3.demo`). Sin embargo, el archivo `config/settings.py` implementa una arquitectura híbrida: mediante la función `_parse_database_url` y variables de entorno (`DATABASE_URL` o `DB_ENGINE`), el sistema puede conectarse de inmediato a PostgreSQL 16 sin modificar una sola línea de código fuente. Además, utilizamos la variable `SIGAE_DB_PATH` para aislar las pruebas de demostración sin tocar nunca la base de datos original."*

---

### Pregunta 5: ¿Cómo se relacionan las tablas principales del sistema?
**Respuesta:**  
*"Las relaciones fundamentales son:  
1. **`Usuario` a `Evento` (1 a Muchos):** Un usuario con rol docente u organizador puede crear múltiples eventos (`ForeignKey` en `Evento`).  
2. **`Evento` a `Participante` (Muchos a Muchos):** Se modela explícitamente mediante la tabla intermedia `Inscripcion` con restricción única `(evento, participante)`.  
3. **`Inscripcion` a `Asistencia` (1 a 1):** Un participante inscrito solo puede tener un registro de asistencia en ese evento (`OneToOneField`).  
4. **`Usuario` a `Rol` (Muchos a 1):** Cada usuario pertenece a un rol institucional mediante clave foránea protegida con `on_delete=PROTECT`."*

---

### Pregunta 6: ¿Cómo funciona el inicio de sesión y el almacenamiento de contraseñas?
**Respuesta:**  
*"El inicio de sesión se gestiona a través de `login_view` en `usuarios/views.py`. Cuando el usuario envía sus credenciales por POST, `LoginForm` valida los datos y ejecuta el backend de autenticación de Django. Las contraseñas se almacenan mediante el algoritmo **PBKDF2 con hash SHA-256** y una sal criptográfica individual. Si las credenciales coinciden, Django crea una sesión HTTP, emite una cookie firmada y segura (`sessionid`), y el sistema registra de inmediato la acción `INICIAR_SESION` en la bitácora de auditoría con la IP del cliente."*

---

### Pregunta 7: ¿Cómo se controlan los roles y permisos de los usuarios?
**Respuesta:**  
*"Mediante un esquema de Control de Acceso Basado en Roles (RBAC). El modelo `Usuario` se vincula a la tabla `Rol`. En las vistas aplicamos el decorador `@login_required` para exigir sesión y evaluamos funciones de control como `es_usuario_gestion` (para administradores, coordinadores y docentes) o `es_administrador` (para acceso exclusivo a la bitácora de auditoría). Si un usuario sin privilegios intenta acceder a una ruta protegida, el sistema eleva `PermissionDenied`, retornando un error **HTTP 403 Forbidden**."*

---

### Pregunta 8: ¿Cómo funciona la inscripción de participantes externos sin cuenta?
**Respuesta:**  
*"Cuando una persona no autenticada ingresa al catálogo y selecciona inscribirse, la vista `inscribirse_evento` en `participantes/views.py` detecta que `request.user.is_authenticated` es falso y le presenta el formulario `InscripcionExternaForm`. El usuario digita su cédula, correo, nombres y teléfono. El sistema verifica si esa persona ya existe en la tabla `Participante` para reutilizar su registro, valida que haya cupo disponible, crea la fila en `Inscripcion` y le genera automáticamente su **Pase Digital con QR**, redirigiéndolo directamente a la pantalla de descarga sin obligarlo a crear una cuenta ni recordar contraseñas."*

---

### Pregunta 9: ¿Cómo se genera y valida un código QR? ¿Por qué es seguro?
**Respuesta:**  
*"El código QR no almacena datos personales en texto plano. En `asistencia/services.py`, la función `generar_token_qr` toma el ID de la inscripción y del evento, y los firma utilizando `django.core.signing.dumps` con **HMAC-SHA256** y una sal secreta (`SALT_QR`). La librería `qrcode` compila este token en una imagen PNG en memoria RAM. Cuando el escáner lee el código, la función `decodificar_token_qr` verifica la firma criptográfica con la clave secreta del servidor. Si alguien intenta alterar el código para cambiar el número de entrada, la firma digital se rompe y el sistema rechaza el acceso con HTTP 403."*

---

### Pregunta 10: ¿Cómo se registra una entrada (Check-in) en el evento?
**Respuesta:**  
*"El organizador abre en su computador la consola `/asistencia/evento/<id>/control/`. La pantalla utiliza la cámara web del equipo y la librería JavaScript `jsQR` para escanear fotogramas de video en tiempo real. Al detectar el QR del pase, emite un sonido acústico y envía el token por POST asíncrono con cabecera CSRF. La vista `control_asistencia` invoca `registrar_asistencia_llegada` dentro de una **transacción atómica** con bloqueo `select_for_update()`. Valida que el token corresponda a este evento, que la inscripción esté activa y que no se haya marcado ya. Si todo es correcto, guarda la hora actual en `hora_entrada` y actualiza la interfaz visual al instante."*

---

### Pregunta 11: ¿Cómo se registra la salida de un participante?
**Respuesta:**  
*"Existen dos vías: manual desde la consola del operador, o mediante el **QR Común de Salida**. Cuando el organizador habilita las salidas, se proyecta un QR general del evento. Los asistentes lo escanean con sus teléfonos celulares abriendo la URL móvil de salida. Para evitar suplantaciones, la página exige un doble factor: Número de Documento y Correo Electrónico registrado. El servicio `registrar_asistencia_salida` verifica que el participante tenga una llegada previa registrada, que no haya marcado salida antes, registra `hora_salida = timezone.localtime().time()`, calcula la permanencia y actualiza el panel administrativo."*

---

### Pregunta 12: ¿Cómo se calcula la duración de asistencia o permanencia?
**Respuesta:**  
*"Se calcula mediante la propiedad `@property def permanencia` en el modelo `Asistencia` (`asistencia/models.py`). Combina la fecha del evento con `hora_entrada` y `hora_salida` para obtener objetos `datetime` completos y restar ambos valores. El sistema cuenta con soporte para **eventos nocturnos que cruzan la medianoche**: si la hora de salida es numéricamente menor a la hora de entrada pero corresponde a la madrugada siguiente (entrada $\ge 18:00$ y salida $\le 08:00$), suma automáticamente un día a la fecha de salida. Retorna un diccionario estructurado con total de minutos, horas y una cadena legible como `'1h 45m'`."*

---

### Pregunta 13: ¿Cómo evita el sistema los registros duplicados?
**Respuesta:**  
*"Se implementa defensa en profundidad en tres capas:*
*1. **A nivel de base de datos:** Restricción `UniqueConstraint(fields=['evento', 'participante'])` en `Inscripcion` y relación `OneToOneField` en `Asistencia`.*
*2. **A nivel de concurrencia:** Transacciones atómicas (`transaction.atomic()`) y bloqueos pesimistas de fila (`select_for_update()`) para que dos peticiones simultáneas en el mismo microsegundo no colisionen.*
*3. **A nivel de lógica de negocio:** Las funciones `registrar_asistencia_llegada` y `registrar_asistencia_salida` verifican explícitamente el estado previo y rechazan con avisos explicativos si ya existe una marcación registrada."*

---

### Pregunta 14: ¿Cómo se generan los reportes oficiales?
**Respuesta:**  
*"Se generan bajo demanda y en memoria (arquitectura **stateless**) en el módulo `reportes`. La vista invoca a `reportes/services.py`, donde utilizamos la librería **ReportLab**. El servicio construye un documento `SimpleDocTemplate`, añade el logotipo institucional de UNIMINUTO, los metadatos del evento y dibuja una tabla vectorial con los participantes, sus horas de entrada/salida, permanencia y casillas de firma. El archivo se compila en un búfer `io.BytesIO()` y se transmite como un flujo binario en la respuesta HTTP con `Content-Type: application/pdf`, sin almacenar archivos estáticos en el disco del servidor."*

---

### Pregunta 15: ¿Cómo se realizaron las pruebas automatizadas del proyecto?
**Respuesta:**  
*"Implementamos **135 pruebas automatizadas** utilizando el framework nativo `django.test.TestCase` y el cliente simulado `Client`. Las pruebas se dividen en las siete aplicaciones y verifican modelos, vistas, formularios, algoritmos criptográficos, validaciones de cupo, cancelaciones y manejo de concurrencia. Cada ejecución se realiza en una base de datos temporal aislada en memoria que se destruye al finalizar, garantizando que los datos originales nunca sean modificados."*

---

### Pregunta 16: ¿Cómo se protege el sistema contra ataques informáticos?
**Respuesta:**  
*"El sistema cubre las principales amenazas de OWASP Top 10:*
*- **CSRF:** Protección obligatoria con `CsrfViewMiddleware` y verificación de orígenes en `CSRF_TRUSTED_ORIGINS`.*
*- **XSS:** Auto-escapado de variables en plantillas DTL y cabecera `SECURE_BROWSER_XSS_FILTER = True`.*
*- **Inyección SQL:** Consultas 100% parametrizadas a través del ORM de Django sin SQL crudo.*
*- **Clickjacking:** Cabecera `X_FRAME_OPTIONS = 'DENY'` que impide incrustar la web en iframes externos.*
*- **MIME Sniffing:** Cabecera `SECURE_CONTENT_TYPE_NOSNIFF = True`.*
*- **Falsificación de Identidad:** Criptografía HMAC-SHA256 en tokens QR sin PII visible.*
*- **Auditoría:** Bitácora inmutable en la tabla `Auditoria` con registro de IP real y usuario."*

---

### Pregunta 17: Si quisiera agregar un nuevo campo a un evento (ej. "enlace de transmisión virtual"), ¿qué pasos seguiría?
**Respuesta:**  
*"Seguiría cuatro pasos estructurados:*
*1. **Modelo:** En [`eventos/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py), agregaría `enlace_virtual = models.URLField(blank=True, null=True, verbose_name='Enlace Virtual')` a la clase `Evento`.*
*2. **Migración:** Ejecutaría `python manage.py makemigrations eventos` y `python manage.py migrate` para actualizar el esquema de la base de datos.*
*3. **Formulario:** En [`eventos/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/forms.py), incluiría `'enlace_virtual'` en la lista `fields` de `EventoForm`.*
*4. **Plantilla:** En [`templates/eventos/detalle.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/eventos/detalle.html) y `form_evento.html`, renderizaría el nuevo campo condicionándolo a que la modalidad sea Virtual o Híbrida."*

---

### Pregunta 18: ¿Qué limitaciones tiene el sistema actualmente?
**Respuesta:**  
*"Las limitaciones identificadas y delimitadas son:*
*1. **Sin pasarela de pagos:** Los eventos son de carácter académico gratuito, por lo que no integra procesamiento de pagos.*
*2. **Web App Responsiva (no app nativa):** Opera directamente en navegadores móviles estándar mediante diseño adaptativo, sin requerir instalación de APK en tiendas.*
*3. **Servicio de correo en desarrollo:** Utiliza `console.EmailBackend` para imprimir correos en la terminal local; en producción requiere conectarse a un servidor SMTP institucional (ej. Microsoft 365).*
*4. **Dependencia de cámara e iluminación:** La lectura óptica de QR requiere condiciones mínimas de enfoque y luz en la cámara web del dispositivo."*

---

### Pregunta 19: ¿Qué se necesitaría para desplegar el sistema públicamente en Internet?
**Respuesta:**  
*"El proyecto ya cuenta con los artefactos de preparación en la carpeta `deploy/`. Para desplegarlo en producción se requiere:*
*1. Un servidor Linux (Ubuntu/Debian) con Python 3.13.*
*2. Configurar **Gunicorn** como servidor de aplicaciones WSGI utilizando [`deploy/gunicorn_conf.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/deploy/gunicorn_conf.py) gestionado por **Systemd** ([`deploy/sigae.service`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/deploy/sigae.service)).*
*3. Configurar **Nginx** como proxy inverso ([`deploy/nginx_sigae.conf`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/deploy/nginx_sigae.conf)) para servir archivos estáticos (`collectstatic`) y gestionar certificados SSL/TLS con HTTPS.*
*4. Una base de datos **PostgreSQL 16** aprovisionada.*
*5. Configurar las variables de entorno en `.env`: `DJANGO_ENV=production`, `DEBUG=False`, una `SECRET_KEY` aleatoria de 50 caracteres y el dominio institucional en `ALLOWED_HOSTS`."*

---

## 3. Tabla de Consulta Rápida ("¿Dónde cambio X cosa?")

| Pregunta o Necesidad del Evaluador | Archivo que debo revisar | Función, Clase o Componente | Motivo / Justificación |
| :--- | :--- | :--- | :--- |
| **Quiero cambiar un campo de un evento** | [`eventos/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py) | `class Evento` | Define las columnas de la tabla en base de datos. |
| **Quiero cambiar el diseño o inputs de un formulario** | [`eventos/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/forms.py) o [`participantes/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/forms.py) | `EventoForm`, `InscripcionExternaForm` | Controla los widgets HTML, clases CSS y validaciones de formulario. |
| **Quiero cambiar los colores o tipografía institucional** | [`static/css/styles.css`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/css/styles.css) | Variables CSS `:root` (`--primary`, `--accent`) | Centraliza la paleta de colores y estilos globales de UNIMINUTO. |
| **Quiero cambiar la estructura o encabezado común de las páginas** | [`templates/base.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/base.html) | Bloques `{% block navbar %}`, `{% block content %}` | Maqueta HTML maestra de la que heredan todas las vistas. |
| **Quiero modificar los roles o sus permisos** | [`usuarios/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/models.py) y [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py) | `class Rol`, función `es_usuario_gestion` | `Rol` define el catálogo y `es_usuario_gestion` autoriza en vistas. |
| **Quiero cambiar la seguridad o firma del QR de entrada** | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) | `generar_token_qr`, `decodificar_token_qr` | Controla la carga útil y la sal criptográfica HMAC-SHA256 (`SALT_QR`). |
| **Quiero modificar el lector de cámara web en vivo** | [`templates/asistencia/control_asistencia.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/asistencia/control_asistencia.html) | Funciones JS `startCamera()`, `tick()`, `jsQR` | Controla el canvas de video y el procesamiento de cuadros ópticos. |
| **Quiero cambiar la lógica del QR común de salida** | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) y [`asistencia/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py) | `construir_url_salida_evento`, `salida_evento_publica` | Resuelve la IP local para celulares y valida el doble factor (cédula + correo). |
| **Quiero modificar la fórmula de cálculo de permanencia** | [`asistencia/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/models.py) | `@property def permanencia` | Calcula la resta de horas y resuelve el cruce de medianoche. |
| **Quiero cambiar el diseño de la Planilla PDF** | [`reportes/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py) | `generar_pdf_planilla_asistencia` | Ensambla el documento vectorial con ReportLab, tablas y casillas de firma. |
| **Quiero agregar métricas o gráficas al Dashboard** | [`analitica/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/services.py) y [`templates/analitica/dashboard.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/analitica/dashboard.html) | `calcular_metricas_dashboard`, script Chart | Calcula agregaciones en backend y alimenta gráficos en frontend. |
| **Quiero cambiar la conexión o el motor de base de datos** | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py) | Diccionario `DATABASES`, `_parse_database_url` | Configura SQLite, `SIGAE_DB_PATH` o PostgreSQL. |
| **Quiero agregar una nueva ruta o módulo** | [`config/urls.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/urls.py) y el `urls.py` de la aplicación | Lista `urlpatterns` | Registra el path y lo conecta con su vista correspondiente. |
| **Quiero consultar los registros de auditoría de seguridad** | [`auditoria/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py) | `consulta_auditoria` | Vista administrativa que filtra por módulo, acción, usuario e IP. |

---

## 4. Guion de Demostración Paso a Paso en el Navegador

Sigue este orden secuencial durante la sustentación en vivo para lograr el máximo impacto visual y técnico:

1. **Paso 1: Pantalla Principal y Catálogo (`http://127.0.0.1:8000/`)**
   - Muestra la interfaz con diseño institucional UNIMINUTO.
   - Navega al Catálogo de Eventos (`/eventos/`).
   - Demuestra el filtro por categoría y modalidad (Presencial/Híbrida).
   - Señala el cálculo en vivo de los cupos disponibles: *"El sistema resta automáticamente las inscripciones activas del aforo máximo"*.

2. **Paso 2: Registro de Participante Externo sin Cuenta**
   - Entra al detalle de un evento (`/eventos/1/`).
   - Haz clic en **"Inscribirme a este Evento"** (sin haber iniciado sesión).
   - Completa el formulario con datos de prueba (ej. Cédula: `10998877`, Correo: `visitante@externo.com`, Nombre: `Visitante Externo`).
   - Al enviar el formulario, muestra cómo el sistema lo redirige de inmediato a su **Pase Digital de Asistencia**.
   - Enfatiza: *"El participante externo no requirió contraseña y ya tiene su código QR firmado con HMAC-SHA256 listo para ser escaneado"*.

3. **Paso 3: Inicio de Sesión y Consola de Control de Asistencia**
   - Inicia sesión como docente u organizador (`/usuarios/login/`).
   - Dirígete al panel del evento: `/asistencia/evento/1/control/`.
   - Muestra cómo la cámara web del PC se enciende automáticamente con el visor óptico de `jsQR`.
   - Acerca el código QR del pase digital generado en el paso anterior (desde la pantalla de otro celular o pestaña).
   - El sistema emite un beep de confirmación y actualiza instantáneamente la fila del participante a **"Asistió"** con su hora exacta de llegada, sin recargar la página.

4. **Paso 4: Demostración de Seguridad del Lector**
   - Abre el modal del **QR Común de Salida**.
   - Acerca ese QR de salida al lector de entrada.
   - Muestra cómo el sistema lo rechaza inteligentemente con una alerta visual:  
     *"El código escaneado corresponde al QR común de SALIDA del evento. Este lector es exclusivo para escanear pases personales de entrada."*
   - Explica: *"Esto demuestra que el sistema diferencia criptográficamente los tipos de código y evita confusiones operativas"*.

5. **Paso 5: Flujo de Salida Móvil y Cálculo de Permanencia**
   - Abre la URL de salida: `/asistencia/evento/1/salida/?token_evento=...`.
   - Ingresa la cédula y correo del asistente acreditado.
   - Presiona **"Confirmar Mi Salida"**.
   - La pantalla confirma el éxito y muestra el tiempo de permanencia calculado (ej. *"Permanencia: 1h 30m"*).
   - Regresa a la consola del organizador y activa el filtro **"Salieron"**: el participante aparece registrado con su hora de salida y permanencia.

6. **Paso 6: Descarga de la Planilla Oficial en PDF**
   - En el menú del evento, presiona **"Descargar Planilla PDF"**.
   - Abre el archivo descargado y muestra el membrete institucional, la tabla formateada de asistentes, estados y casillas de firma generadas en memoria con `ReportLab`.

7. **Paso 7: Dashboard Analítico y Bitácora de Auditoría**
   - Accede a `/analitica/` para mostrar las métricas de cobertura y la opción de exportar a Excel (`openpyxl`).
   - Accede a `/auditoria/` (como Administrador) y muestra cómo cada una de las acciones que acabas de ejecutar (login, inscripción externa, check-in, check-out, descarga de PDF) quedó registrada cronológicamente con usuario, IP y hora.
