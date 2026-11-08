# 09. GLOSARIO TÉCNICO Y CONCEPTUAL

**Sistema:** EventosSIGAE-UNIMINUTO  
**Propósito:** Definir en lenguaje riguroso pero accesible cada término técnico utilizado en el proyecto, distinguiendo expresamente los conceptos que forman parte de la implementación real de aquellos que corresponden a principios teóricos generales de la ingeniería de software.

---

## 1. Conceptos Implementados y Comprobados en el Proyecto

### 1. Python
- **Definición:** Lenguaje de programación interpretado, multiparadigma y de alto nivel.
- **En el Proyecto:** Es el lenguaje sobre el cual está construido el 100% del backend de SIGAE, utilizando específicamente **Python 3.13.0**.

### 2. Django
- **Definición:** Framework web de código abierto para Python que promueve el desarrollo rápido y el diseño limpio y pragmático siguiendo la arquitectura MVT.
- **En el Proyecto:** Se utiliza **Django 6.1.1** como núcleo de toda la aplicación, proveyendo el ORM, la gestión de sesiones, el sistema de plantillas y la seguridad.

### 3. MVT (Model - View - Template)
- **Definición:** Patrón de arquitectura de software derivado de MVC (Model-View-Controller).
- **En el Proyecto:**
  - **Model (Modelo):** [`models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py) representa los datos relacionales en la base de datos.
  - **View (Vista):** [`views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py) actúa como controlador recibiendo peticiones HTTP y ejecutando la lógica.
  - **Template (Plantilla):** [`templates/`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/) renderiza la presentación en HTML5 para el navegador.

### 4. ORM (Object-Relational Mapping / Mapeo Objeto-Relacional)
- **Definición:** Técnica de programación que permite interactuar con una base de datos relacional utilizando objetos de código orientado a objetos, en lugar de escribir consultas SQL manuales.
- **En el Proyecto:** Django ORM traduce clases como `Evento.objects.filter(estado='PUBLICADO')` a sentencias SQL parametrizadas seguras contra inyección de código.

### 5. Modelo (`models.Model`)
- **Definición:** Clase de Python que describe la estructura, columnas, tipos de datos y restricciones de una tabla en la base de datos.
- **En el Proyecto:** Se implementan 8 modelos principales (`Rol`, `Usuario`, `CategoriaEvento`, `Evento`, `Participante`, `Inscripcion`, `Asistencia`, `ControlSalidaEvento` y `Auditoria`).

### 6. Vista (`views.py`)
- **Definición:** Función o clase en Python que recibe un objeto `HttpRequest` del cliente web y devuelve un objeto `HttpResponse` (HTML, JSON o descarga binaria de archivo).
- **En el Proyecto:** Gestionan el flujo de las páginas, por ejemplo `catalogo_eventos`, `control_asistencia` y `descargar_planilla_asistencia_pdf`.

### 7. URL / Enrutador (`urls.py`)
- **Definición:** Archivo de configuración que mapea patrones de direcciones web (rutas) hacia vistas específicas de Django mediante expresiones o rutas parametrizadas.
- **En el Proyecto:** Centralizado en [`config/urls.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/urls.py) y distribuido modularmente en los `urls.py` de cada una de las 7 aplicaciones.

### 8. Plantilla (*Template* / DTL)
- **Definición:** Archivo de texto plano (usualmente HTML) enriquecido con el lenguaje de plantillas de Django (*Django Template Language*), que permite incrustar variables, bucles condicionales y herencia de bloques.
- **En el Proyecto:** Permite que todas las pantallas hereden del archivo maestro [`templates/base.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/base.html) manteniendo la identidad visual de UNIMINUTO.

### 9. Migración (`makemigrations` / `migrate`)
- **Definición:** Archivo en Python generado por Django que registra de forma incremental los cambios realizados en los modelos para replicarlos en el esquema de la base de datos.
- **En el Proyecto:** Carpetas `migrations/` en cada módulo que garantizan el control de versiones del esquema en SQLite o PostgreSQL.

### 10. SQLite
- **Definición:** Motor de base de datos relacional ligero, sin servidor (*serverless*), que almacena toda la información en un único archivo de disco local.
- **En el Proyecto:** Base de datos utilizada en el entorno de desarrollo y pruebas locales ([`db.sqlite3`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3) y [`db.sqlite3.demo`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3.demo)).

### 11. PostgreSQL
- **Definición:** Sistema de gestión de bases de datos relacional y orientado a objetos de nivel empresarial, con soporte de concurrencia avanzada y transacciones ACID.
- **En el Proyecto:** Configurado como el motor oficial para producción a través del driver `psycopg` (3.3.6) y variables de entorno (`DATABASE_URL`).

### 12. Autenticación vs. Autorización
- **Autenticación:** Proceso de verificar la identidad del usuario (¿Quién es usted? Ej. login con usuario y contraseña PBKDF2).
- **Autorización:** Proceso de verificar qué acciones tiene permitido realizar ese usuario una vez autenticado (¿Qué puede hacer? Ej. control de acceso basado en el rol `Docente` o `Administrador`).

### 13. Sesión HTTP (`SessionMiddleware`)
- **Definición:** Mecanismo que permite al servidor web recordar el estado y la identidad del usuario entre diferentes peticiones HTTP que por naturaleza son sin estado (*stateless*).
- **En el Proyecto:** Django almacena la sesión en la base de datos y envía una cookie firmada `sessionid` al navegador.

### 14. Middleware
- **Definición:** Componente intermedio en la arquitectura de Django que procesa peticiones y respuestas de forma global antes de que lleguen a las vistas o antes de ser devueltas al navegador.
- **En el Proyecto:** Operan middlewares esenciales como `SecurityMiddleware`, `SessionMiddleware`, `CsrfViewMiddleware` y `AuthenticationMiddleware`.

### 15. Token Criptográfico
- **Definición:** Cadena de caracteres codificada que encapsula información protegida matemáticamente para ser transmitida entre sistemas sin permitir su alteración.
- **En el Proyecto:** Se generan con `django.core.signing.dumps` para los pases de asistencia y para la recuperación de contraseñas.

### 16. HMAC (Hash-based Message Authentication Code)
- **Definición:** Mecanismo criptográfico que utiliza una función de dispersión (hash, en este caso SHA-256) combinada con una clave secreta para autenticar la integridad de un mensaje.
- **En el Proyecto:** Garantiza que el código QR generado por el servidor no pueda ser falsificado ni modificado por terceros sin poseer la `SECRET_KEY` del sistema.

### 17. Código QR (Quick Response Code)
- **Definición:** Matriz bidimensional de puntos utilizada para almacenar información óptica que puede ser leída rápidamente por cámaras digitales o escáneres.
- **En el Proyecto:**
  - Generación backend: Mediante la librería `qrcode` y `Pillow`.
  - Decodificación frontend: Mediante la librería JavaScript `jsQR.min.js` desde el flujo de video de la cámara web.

### 18. CSRF (Cross-Site Request Forgery / Falsificación de Petición en Sitios Cruzados)
- **Definición:** Ataque cibernético que obliga al navegador de una víctima autenticada a ejecutar comandos no autorizados en una aplicación web de confianza.
- **En el Proyecto:** Se bloquea obligatoriamente exigiendo un token secreto en cada formulario POST (`{% csrf_token %}`) y validando los orígenes permitidos en `CSRF_TRUSTED_ORIGINS`.

### 19. Endpoint
- **Definición:** Dirección URL específica de un servidor web que expone un servicio o recurso determinado para recibir o enviar información.
- **En el Proyecto:** Ejemplos: `/health/` (endpoint de salud), `/asistencia/evento/1/control/` (endpoint de consola).

### 20. Pruebas Unitarias vs. Pruebas de Integración
- **Pruebas Unitarias:** Verifican el funcionamiento aislado de un componente individual (ej. comprobar que el método `clean()` de `Evento` rechace horas invertidas).
- **Pruebas de Integración:** Verifican la interacción conjunta de múltiples componentes (ej. enviar un formulario web, procesar la vista, guardar en base de datos, validar el token QR y generar auditoría).
- **En el Proyecto:** Implementadas en los archivos `tests.py` sumando 135 casos de prueba automatizados.

### 21. Variables de Entorno
- **Definición:** Valores dinámicos que se configuran en el sistema operativo del servidor o mediante archivos `.env` fuera del código fuente, para desacoplar configuraciones sensibles (claves, contraseñas, URLs de BD).
- **En el Proyecto:** Gestionadas mediante `os.environ.get()` en [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py) y documentadas en [`.env.example`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/.env.example).

### 22. Archivos Estáticos (*Static Files*)
- **Definición:** Archivos que el servidor web envía directamente al navegador sin ser procesados por Python (CSS, JavaScript, imágenes de logotipos).
- **En el Proyecto:** Almacenados en [`static/css/styles.css`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/css/styles.css) y [`static/js/jsQR.min.js`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/js/jsQR.min.js).

---

## 2. Conceptos Teóricos Generales (No Implementados Directamente)

Para responder con honestidad técnica durante la sustentación, los siguientes conceptos son teóricos o propios del estado del arte, pero **no** forman parte de la arquitectura activa de SIGAE:

- **API REST / GraphQL:**  
  *Concepto General:* Interfaz de servicios desacoplada para comunicación con clientes externos o móviles nativos mediante JSON.  
  *En SIGAE:* No está implementada; SIGAE es una aplicación web renderizada en servidor (SSR) mediante el motor de plantillas de Django, utilizando llamadas AJAX específicas para la consola de asistencia.
- **Single Page Application (SPA):**  
  *Concepto General:* Aplicaciones donde la navegación ocurre dinámicamente en una sola página gestionada por frameworks como React, Angular o Vue.js.  
  *En SIGAE:* No se usa SPA; la arquitectura se basa en páginas web tradicionales multi-página renderizadas en servidor con HTML semántico.
- **JWT (JSON Web Tokens):**  
  *Concepto General:* Tokens estándar para autenticación en APIs sin estado.  
  *En SIGAE:* No se utiliza JWT; la autenticación se maneja por sesiones de Django (`sessionid`), y la firma de los códigos QR utiliza `django.core.signing` con HMAC.
- **Docker / Kubernetes:**  
  *Concepto General:* Plataformas de contenedorización y orquestación de microservicios.  
  *En SIGAE:* No se utilizan contenedores en el entorno actual; el despliegue está planificado sobre servidores Linux nativos con Gunicorn, Systemd y Nginx.
- **Microservicios:**  
  *Concepto General:* Arquitectura distribuida que divide el sistema en múltiples servicios independientes desplegados por separado.  
  *En SIGAE:* No aplica; el sistema es un **Monolito Modular** estructurado en 7 aplicaciones Django altamente cohesivas.
