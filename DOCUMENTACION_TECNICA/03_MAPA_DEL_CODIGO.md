# 03. MAPA DE NAVEGACIÓN Y ARQUITECTURA DEL CÓDIGO

**Sistema:** EventosSIGAE-UNIMINUTO  
**Propósito:** Guía de orientación rápida para ubicar con exactitud cualquier funcionalidad, clase, vista, modelo o plantilla dentro del proyecto.

---

## 1. Árbol General del Repositorio

```text
EventosSIGAE-UNIMINUTO/
│
├── manage.py                          # Entrada CLI para comandos administrativos de Django
├── requirements.txt                   # Dependencias base (Django, reportlab, qrcode, etc.)
├── requirements-prod.txt              # Dependencias de producción Linux (Gunicorn)
├── .env.example                       # Plantilla de variables de entorno seguras
│
├── config/                            # Paquete central de configuración del proyecto
│   ├── settings.py                    # Ajustes globales, apps, bases de datos y seguridad
│   ├── urls.py                        # Enrutador principal de URLs institucionales
│   ├── views.py                       # Vista de monitoreo de salud (/health/)
│   ├── wsgi.py                        # Punto de entrada WSGI para servidores web
│   └── asgi.py                        # Punto de entrada ASGI
│
├── usuarios/                          # Módulo 1: Autenticación, usuarios y roles
│   ├── models.py                      # Modelos Rol y Usuario (AbstractUser)
│   ├── views.py                       # Login, Logout y recuperación de contraseñas
│   ├── forms.py                       # LoginForm y PerfilUsuarioForm
│   ├── urls.py                        # Rutas /usuarios/...
│   ├── admin.py                       # Registro en panel administrativo
│   ├── tests.py                       # Pruebas automatizadas del módulo
│   └── management/commands/
│       └── inicializar_roles.py       # Comando para roles canónicos
│
├── eventos/                           # Módulo 2: Catálogo y ciclo de vida de eventos
│   ├── models.py                      # Modelos CategoriaEvento y Evento
│   ├── views.py                       # Catálogo público, detalle, CRUD y cancelación
│   ├── forms.py                       # EventoForm con validaciones de fechas y cupos
│   ├── urls.py                        # Rutas /eventos/...
│   ├── admin.py                       # Configuración administrativa
│   └── tests.py                       # Pruebas unitarias y de integración
│
├── participantes/                     # Módulo 3: Perfiles de participantes e inscripciones
│   ├── models.py                      # Modelos Participante e Inscripcion
│   ├── views.py                       # Inscripción interna/externa y "Mis Inscripciones"
│   ├── forms.py                       # InscripcionExternaForm (Cédula, Correo, Datos)
│   ├── urls.py                        # Rutas /participantes/...
│   ├── admin.py                       # Registro de participantes en Django Admin
│   └── tests.py                       # Pruebas de cupos, cancelaciones y reactivaciones
│
├── asistencia/                        # Módulo 4: Pases QR, lectura óptica y check-out
│   ├── models.py                      # Modelos Asistencia y ControlSalidaEvento
│   ├── services.py                    # Criptografía QR, permanencia y lógica temporal
│   ├── views.py                       # Consola cámara, pase digital y salida móvil
│   ├── urls.py                        # Rutas /asistencia/...
│   ├── admin.py                       # Control administrativo de asistencias
│   └── tests.py                       # 49 pruebas de validaciones QR y de negocio
│
├── reportes/                          # Módulo 5: Generación stateless de PDFs oficiales
│   ├── models.py                      # Declarativo (arquitectura stateless sin persistencia)
│   ├── services.py                    # Dibujo vectorial ReportLab (Planillas y Consolidados)
│   ├── views.py                       # Endpoints de descarga con auditoría
│   ├── urls.py                        # Rutas /reportes/...
│   └── tests.py                       # Pruebas de generación y descarga binaria
│
├── analitica/                         # Módulo 6: Dashboard estadístico y exportaciones
│   ├── models.py                      # Declarativo (computado on-the-fly)
│   ├── services.py                    # Agregaciones, promedios y generador Excel/CSV
│   ├── views.py                       # Tablero visual con filtros y series JSON
│   ├── forms.py                       # FiltroDashboardForm
│   ├── urls.py                        # Rutas /analitica/...
│   └── tests.py                       # Pruebas de cálculo de métricas y exportación
│
├── auditoria/                         # Módulo 7: Bitácora inmutable de seguridad
│   ├── models.py                      # Modelo Auditoria (Acción, Módulo, IP, Usuario)
│   ├── views.py                       # Vista de consulta y filtros para administradores
│   ├── urls.py                        # Rutas /auditoria/...
│   ├── admin.py                       # Visualización de solo lectura en Admin
│   └── tests.py                       # Pruebas de trazabilidad
│
├── templates/                         # Plantillas HTML5 globales y modulares
│   ├── base.html                      # Maqueta principal institucional con navegación
│   ├── usuarios/                      # login.html, password_reset_*.html
│   ├── eventos/                       # catalogo.html, detalle.html, mis_eventos.html, etc.
│   ├── participantes/                 # inscribirse_externo.html, mis_inscripciones.html
│   ├── asistencia/                    # control_asistencia.html, pase_digital.html, salida_evento.html
│   ├── analitica/                     # dashboard.html
│   └── auditoria/                     # consulta.html
│
├── static/                            # Archivos estáticos del frontend
│   ├── css/styles.css                 # Sistema de diseño institucional UNIMINUTO
│   ├── js/main.js                     # Inicialización general de la app
│   └── js/jsQR.min.js                 # Biblioteca de escaneo óptico por cámara web
│
└── deploy/                            # Endurecimiento y producción Linux
    ├── gunicorn_conf.py               # Configuración de workers y sockets
    ├── nginx_sigae.conf               # Configuración de proxy inverso y TLS
    └── sigae.service                  # Servicio Systemd para Linux
```

---

## 2. Descripción Detallada por Aplicación Django

### 1. `config` (Núcleo del Sistema)
- **Responsabilidad:** Configurar el entorno de ejecución, cargar variables de entorno, conectar la base de datos adecuada, registrar el enrutador principal y proveer el chequeo de salud de la plataforma.
- **Archivos Clave:**
  - [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py): Contiene `ALLOWED_HOSTS`, `INSTALLED_APPS`, `DATABASES` (soporte SQLite con `SIGAE_DB_PATH` y PostgreSQL con `DATABASE_URL`), `AUTH_USER_MODEL = 'usuarios.Usuario'`, configuración de idioma (`es-co`) y zona horaria (`America/Bogota`).
  - [`config/urls.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/urls.py): Define la raíz `'/'`, `'admin/'`, `'health/'` y conecta los espacios de nombres (`namespaces`) de las 7 aplicaciones.
  - [`config/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/views.py): Contiene `health_check(request)`, que ejecuta `SELECT 1;` en la base de datos activa.
- **¿Cuándo consultarlo?** Cuando se necesite cambiar variables de entorno, agregar una nueva aplicación a Django, modificar orígenes CSRF o ajustar el motor de base de datos.

---

### 2. `usuarios` (Autenticación y Roles)
- **Responsabilidad:** Gestionar las cuentas de usuario de UNIMINUTO, los roles institucionales canónicos y el flujo de autenticación y recuperación de contraseñas.
- **Archivos Clave:**
  - [`usuarios/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/models.py):
    - `Rol`: Catálogo de roles (`Administrador`, `Coordinador`, `Docente`, `Estudiante`).
    - `Usuario`: Extiende `AbstractUser`. Campos adicionales: `documento` (único), `nombres`, `apellidos`, `email` (único), `telefono`, `tipo_vinculacion`, `rol` (FK a `Rol`).
  - [`usuarios/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/views.py):
    - `login_view`: Autentica credenciales, crea sesión y registra auditoría.
    - `logout_view`: Destruye sesión y audita la salida.
    - `CustomPasswordResetView` / `CustomPasswordResetConfirmView`: Flujo de recuperación de clave por correo.
  - [`usuarios/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/forms.py): `LoginForm` con estilos institucionales y `PerfilUsuarioForm`.
  - [`usuarios/management/commands/inicializar_roles.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/management/commands/inicializar_roles.py): Comando CLI idempotente para sembrar los 4 roles canónicos sin alterar usuarios.
- **¿Cuándo consultarlo?** Al modificar la estructura de los usuarios, ajustar los roles institucionales o personalizar la pantalla de inicio de sesión.

---

### 3. `eventos` (Catálogo y Ciclo de Vida de Eventos)
- **Responsabilidad:** Gestionar la información de los eventos institucionales, programación, lugares, aforos, estados y catálogo público.
- **Archivos Clave:**
  - [`eventos/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/models.py):
    - `CategoriaEvento`: Nombre, descripción y estado activo.
    - `Evento`: Nombre, descripción, fecha, hora inicio/fin, lugar, modalidad (`PRESENCIAL`, `VIRTUAL`, `HIBRIDA`), cupo, estado (`BORRADOR`, `PUBLICADO`, `CERRADO`, `CANCELADO`, `FINALIZADO`), organizador (FK a `Usuario`). Validación `clean()`: `hora_fin > hora_inicio`.
  - [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py):
    - `catalogo_eventos`: Vista pública con filtros y cálculo de cupos disponibles (`cupo - total_activos`).
    - `detalle_evento`: Vista detallada con control de acceso y botón condicional de inscripción.
    - `crear_evento`: Formulario de creación para organizadores/docentes autorizados con auditoría.
    - `editar_evento`: Modificación por parte del organizador o administrador.
    - `cancelar_evento`: Cancelación formal con motivo obligatorio, cambiando estado a `CANCELADO` y preservando inscripciones.
  - [`eventos/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/forms.py): `EventoForm` con widgets HTML5 de fecha y hora.
- **¿Cuándo consultarlo?** Al alterar los campos de un evento, modificar las reglas de cupo o ajustar los filtros de búsqueda en el catálogo.

---

### 4. `participantes` (Inscripciones Internas y Externas)
- **Responsabilidad:** Gestionar las personas que asisten a los eventos y sus registros formales de inscripción.
- **Archivos Clave:**
  - [`participantes/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/models.py):
    - `Participante`: Representa a la persona física. Puede estar vinculado a un `Usuario` (1:1 opcional) o ser externo sin cuenta (`usuario=None`).
    - `Inscripcion`: Tabla intermedia N:M entre `Evento` y `Participante`. Restricción única `(evento, participante)`. Propiedad `.asistio` que consulta si tiene asistencia registrada.
  - [`participantes/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/views.py):
    - `inscribirse_evento`: Detecta si el usuario está autenticado (inscripción directa) o anónimo (formulario externo con cédula y correo). Si ya estaba inscrito y canceló, reactiva la inscripción.
    - `mis_inscripciones`: Panel personal del estudiante para ver sus eventos y acceder a sus pases QR.
    - `cancelar_inscripcion`: Permite al asistente cancelar su inscripción si el evento no ha cerrado ni registra asistencia.
  - [`participantes/forms.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/forms.py): `InscripcionExternaForm`.
- **¿Cuándo consultarlo?** Si se necesita cambiar el formulario de registro externo, agregar datos al perfil de los asistentes o modificar la política de cancelaciones.

---

### 5. `asistencia` (Pases QR, Cámara Web y Check-out)
- **Responsabilidad:** Corazón operativo de la acreditación. Emisión de pases digitales, decodificación por cámara web, check-in, check-out móvil y permanencia.
- **Archivos Clave:**
  - [`asistencia/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/models.py):
    - `Asistencia`: Relación 1:1 con `Inscripcion`. Campos: `fecha`, `hora_entrada`, `hora_salida`, `metodo` (`QR`, `MANUAL`, `LISTA`), `estado` (`REGISTRADA`, `ANULADA`), `observaciones`. Propiedades: `permanencia` (calcula horas y minutos) y `es_valida`.
    - `ControlSalidaEvento`: Interruptor de habilitación de salidas para cada evento.
  - [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py): **Capa de Lógica de Negocio Pura**:
    - `generar_token_qr` / `decodificar_token_qr`: Criptografía HMAC-SHA256 para pases individuales (`SALT_QR`).
    - `generar_imagen_qr_bytes`: Construye el PNG del QR con la librería `qrcode` en memoria.
    - `registrar_asistencia_llegada`: Transacción atómica que valida inscripción activa, evento no cancelado y evita llegadas duplicadas.
    - `registrar_asistencia_salida`: Transacción atómica que valida llegada previa, hora de salida posterior a entrada, calcula permanencia y bloquea salidas duplicadas.
    - `construir_url_salida_evento`: Resuelve la IP local (`192.168.1.10:8000`) para que el celular abra la página sin apuntar a su propio loopback.
  - [`asistencia/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/views.py):
    - `pase_digital`: Renderiza el pase digital del asistente.
    - `descargar_qr_imagen`: Endpoint binario de descarga del PNG.
    - `control_asistencia`: Consola del organizador (video de cámara web + lista de inscritos + modal de QR de salida). Detecta si se pasa el QR de salida por el lector de entrada y lo rechaza con aviso explícito.
    - `salida_evento_publica`: Vista móvil accesible desde el celular del participante con doble factor (cédula + correo).
    - `toggle_salidas_evento`: Activa o pausa la toma de salidas para el evento.
    - `anular_asistencia`: Permite anular una marcación errónea con justificación auditada.
- **¿Cuándo consultarlo?** Es el archivo principal para entender cómo funciona la lectura óptica por cámara, la seguridad de los tokens y el cálculo de permanencia.

---

### 6. `reportes` (Documentos Oficiales en PDF)
- **Responsabilidad:** Construir programáticamente actas oficiales de asistencia y reportes consolidados en formato PDF vectorial.
- **Archivos Clave:**
  - [`reportes/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/models.py): Sin modelos (arquitectura stateless).
  - [`reportes/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py):
    - `obtener_datos_planilla_imprimible`: Consulta optimizada de inscritos y asistencias.
    - `generar_pdf_planilla_asistencia`: Dibuja el PDF con ReportLab (encabezado institucional UNIMINUTO, metadatos, tabla de asistentes con casillas de firma y fecha de generación).
    - `generar_pdf_reporte_consolidado`: Genera informe ejecutivo con métricas de aforo, porcentaje de asistencia y tabla detallada con hora de entrada, salida y permanencia.
  - [`reportes/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/views.py):
    - `descargar_planilla_asistencia_pdf`: Endpoint con control de permisos y auditoría.
    - `descargar_reporte_consolidado_pdf`: Endpoint con control de permisos y auditoría.
- **¿Cuándo consultarlo?** Si se necesita cambiar el diseño, logotipos, márgenes o columnas de los documentos PDF imprimibles.

---

### 7. `analitica` (Indicadores y Exportación de Datos)
- **Responsabilidad:** Calcular métricas de cobertura, asistencia promedio y permitir la exportación tabular de datos.
- **Archivos Clave:**
  - [`analitica/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/services.py):
    - `calcular_metricas_dashboard`: Agregaciones SQL (`total_eventos`, `total_inscritos`, `total_asistieron`, `porcentaje_asistencia_global`, `permanencia_promedio_general`).
    - `exportar_csv_analitica`: Construye cadena CSV codificada en UTF-8 con BOM para apertura correcta en Excel.
    - `exportar_excel_analitica`: Construye libro `.xlsx` con `openpyxl`, estilizando cabeceras y auto-ajustando anchos de columna.
  - [`analitica/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/views.py):
    - `dashboard`: Renderiza el tablero con series empaquetadas en JSON para gráficas.
    - `exportar_csv` / `exportar_excel`: Endpoints de descarga de datos.
- **¿Cuándo consultarlo?** Para modificar fórmulas estadísticas, agregar nuevos gráficos o añadir columnas a las exportaciones de datos.

---

### 8. `auditoria` (Seguridad y Trazabilidad)
- **Responsabilidad:** Registrar cronológicamente cada acción relevante del sistema para garantizar no repudio y trazabilidad.
- **Archivos Clave:**
  - [`auditoria/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/models.py):
    - `Auditoria`: `usuario`, `accion`, `modulo`, `registro_afectado`, `ip` y `fecha`.
  - [`auditoria/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py):
    - `consulta_auditoria`: Vista de consulta exclusiva para administradores con filtros por módulo, acción, usuario, fechas y paginación a 25 registros. Garantiza inmutabilidad (no ofrece botones de editar o borrar).
- **¿Cuándo consultarlo?** Para revisar el historial de operaciones o auditar quién realizó una modificación o cancelación en el sistema.

---

## 3. Dónde se Ubica la Lógica de Negocio

A diferencia de proyectos principiantes donde las vistas acumulan cientos de líneas de lógica mezclada, en **EventosSIGAE-UNIMINUTO** la lógica de negocio se encuentra **estrictamente desacoplada**:

```text
[ Vistas (views.py) ]
       │  (Solo orquestan HTTP, validan formularios y retornan respuestas)
       ▼
[ Servicios (services.py) ]
       ├── asistencia/services.py  --> Criptografía HMAC, validación de llegada/salida, permanencia
       ├── reportes/services.py    --> Ensamblado vectorial de documentos PDF (ReportLab)
       └── analitica/services.py   --> Cómputos estadísticos y generación de Excel (openpyxl)
       │
       ▼
[ Modelos (models.py) ]
       └── Validaciones de integridad mediante clean() y propiedades calculadas (@property)
```

---

## 4. Tabla de Localización Rápida por Funcionalidad

| Funcionalidad que busco | Archivo donde está implementada | Clase / Función específica |
| :--- | :--- | :--- |
| Inicio de sesión y verificación de clave | [`usuarios/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/views.py) | `login_view` |
| Modelo de datos del Usuario y Roles | [`usuarios/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/usuarios/models.py) | `class Usuario`, `class Rol` |
| Catálogo y búsqueda de eventos | [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py) | `catalogo_eventos` |
| Creación de nuevo evento | [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py) | `crear_evento` |
| Cancelación de evento con motivo | [`eventos/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/eventos/views.py) | `cancelar_evento` |
| Formulario de inscripción para externos | [`participantes/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/participantes/views.py) | `inscribirse_evento` |
| Generación del token seguro del QR | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) | `generar_token_qr` |
| Generación de la imagen física del QR | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) | `generar_imagen_qr_bytes` |
| Escáner óptico de cámara web en vivo | [`templates/asistencia/control_asistencia.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/asistencia/control_asistencia.html) | Script JS `tick()`, `jsQR` |
| Registro de llegada (Check-in) | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) | `registrar_asistencia_llegada` |
| Registro de salida y permanencia | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py) | `registrar_asistencia_salida` |
| Cálculo de permanencia en el modelo | [`asistencia/models.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/models.py) | Propiedad `@property def permanencia` |
| Generación de Planilla de Asistencia PDF | [`reportes/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py) | `generar_pdf_planilla_asistencia` |
| Generación de Reporte Consolidado PDF | [`reportes/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py) | `generar_pdf_reporte_consolidado` |
| Cálculo de estadísticas del Dashboard | [`analitica/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/services.py) | `calcular_metricas_dashboard` |
| Exportación a Excel (.xlsx) | [`analitica/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/services.py) | `exportar_excel_analitica` |
| Bitácora de Auditoría | [`auditoria/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/auditoria/views.py) | `consulta_auditoria` |
| Chequeo de Salud del Sistema | [`config/views.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/views.py) | `health_check` |
