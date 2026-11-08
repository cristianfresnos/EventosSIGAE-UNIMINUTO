# 02. INVENTARIO REAL DE TECNOLOGÍAS, LIBRERÍAS Y DEPENDENCIAS

**Sistema:** EventosSIGAE-UNIMINUTO  
**Entorno de Verificación:** Python 3.13.0 en Windows 11  
**Propósito:** Detallar cada componente tecnológico comprobado en el proyecto, clasificando su nivel de presencia (Declarada, Instalada, Utilizada) y citando los archivos exactos donde se implementa.

---

## 1. Clasificación Metodológica de Dependencias

Para responder con total precisión académica ante el evaluador, se clasifica cada componente bajo tres criterios estrictos:
- **A. Declarada:** Listada formalmente en los archivos [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt) o [`requirements-prod.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements-prod.txt).
- **B. Instalada:** Verificada físicamente en el entorno virtual activo (`.venv`) mediante el comando de solo lectura `pip list`.
- **C. Utilizada Efectivamente:** Importada y ejecutada en los módulos de código fuente (`.py` o `.js`).

---

## 2. Inventario Tecnológico Clasificado por Categorías

### A. Lenguaje de Programación

| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **Python** |
| **Versión Comprobada** | `3.13.0` (64-bit) |
| **Nivel** | Declarada, Instalada y Utilizada Efectivamente |
| **Para qué se utiliza** | Lenguaje base para todo el backend del sistema, gestión de lógica de negocio, servicios criptográficos y ORM. |
| **Ubicación de Verificación** | Ejecución de `python --version` en el entorno `.venv`. |
| **Importancia** | Núcleo de cómputo donde corren Django, ReportLab, QrCode y los servicios del proyecto. |
| **Ejemplo Concreto** | Funciones de tiempo, tipado dinámico, manejo de excepciones y decoradores en todo el proyecto. |

---

### B. Framework Web y Servidor ASGI/WSGI

#### 1. Django
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **Django** |
| **Versión Comprobada** | `6.1.1` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`6.1.1`) y Utilizada Efectivamente |
| **Para qué se utiliza** | Framework web integral: enrutamiento de URLs, vistas, middleware de seguridad, motor de plantillas, ORM y panel administrativo. |
| **Ubicación de Verificación** | [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt#L2), [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py) |
| **Importancia** | Estructura medular del patrón MVT sobre el que se articulan las 7 aplicaciones del sistema. |
| **Ejemplo Concreto** | En [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L118-L133) define `INSTALLED_APPS` y en [`config/urls.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/urls.py#L14-L25) gestiona la inclusión modular de rutas. |

#### 2. asgiref
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **asgiref** |
| **Versión Comprobada** | `3.12.1` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`3.12.1`) y Utilizada Efectivamente (como sub-dependencia crítica de Django) |
| **Para qué se utiliza** | Especificación estándar para servidores web asíncronos en Python. |
| **Ubicación de Verificación** | [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt#L1), [`config/asgi.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/asgi.py) |
| **Importancia** | Requisito fundamental de Django para manejar el ciclo de vida de peticiones y compatibilidad ASGI/WSGI. |

#### 3. Gunicorn
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **Gunicorn (Green Unicorn)** |
| **Versión Comprobada** | `23.0.0` (Declarada para servidores Linux en `requirements-prod.txt`) |
| **Nivel** | Declarada para Producción. No instalada en el entorno local de desarrollo Windows. |
| **Para qué se utiliza** | Servidor de aplicaciones WSGI para entornos Unix/Linux de producción. |
| **Ubicación de Verificación** | [`requirements-prod.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements-prod.txt#L7), [`deploy/gunicorn_conf.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/deploy/gunicorn_conf.py), [`deploy/sigae.service`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/deploy/sigae.service) |
| **Importancia** | Permite ejecutar workers concurrentes detrás de Nginx en servidores de despliegue institucional. |

---

### C. Base de Datos y Adaptadores (ORM)

#### 1. SQLite 3
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **SQLite** |
| **Versión Comprobada** | Nativa de Python 3.13 (`sqlite3` standard library) |
| **Nivel** | Instalada y Utilizada Efectivamente |
| **Para qué se utiliza** | Motor relacional por defecto para desarrollo local, pruebas unitarias y validaciones funcionales. |
| **Ubicación de Verificación** | [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L233-L239), archivos [`db.sqlite3`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3) y [`db.sqlite3.demo`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3.demo) |
| **Importancia** | Almacenamiento local autocontenido sin necesidad de levantar servicios de bases de datos independientes. |
| **Ejemplo Concreto** | La variable `SIGAE_DB_PATH` permite alternar dinámicamente entre la base original y la de pruebas. |

#### 2. PostgreSQL y Psycopg
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **Psycopg 3 (psycopg / psycopg-binary)** |
| **Versión Comprobada** | `3.3.6` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`3.3.6`) y Utilizada Efectivamente en pruebas de compatibilidad |
| **Para qué se utiliza** | Conector / adaptador oficial para bases de datos PostgreSQL de alto rendimiento. |
| **Ubicación de Verificación** | [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt#L9), [`config/settings.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/config/settings.py#L185-L231) |
| **Importancia** | Habilita el soporte dual del proyecto para migrar a PostgreSQL 16 en producción sin tocar código. |
| **Ejemplo Concreto** | La función `_parse_database_url` en `config/settings.py` parsea cadenas de conexión de PostgreSQL. |

#### 3. sqlparse
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **sqlparse** |
| **Versión Comprobada** | `0.6.0` |
| **Nivel** | Declarada, Instalada y Utilizada Efectivamente (por Django ORM) |
| **Para qué se utiliza** | Análisis sintáctico y formateo de sentencias SQL generadas por el ORM. |
| **Ubicación de Verificación** | [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt#L4) |
| **Importancia** | Componente requerido por Django para depuración y ejecución interna de migraciones SQL. |

---

### D. Generación y Lectura de Códigos QR

#### 1. qrcode (Python)
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **qrcode** |
| **Versión Comprobada** | `8.2` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`8.2`) y Utilizada Efectivamente |
| **Para qué se utiliza** | Generación de matrices bidimensionales QR en memoria RAM a partir de cadenas o URLs. |
| **Ubicación de Verificación** | [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L8), función `generar_imagen_qr_bytes` |
| **Importancia** | Emite la imagen PNG del pase digital de asistencia y el QR común de salida del evento. |
| **Ejemplo Concreto** | `qr = qrcode.QRCode(box_size=10, border=2); qr.add_data(token); img = qr.make_image(...)` en `asistencia/services.py`. |

#### 2. Pillow (PIL Fork)
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **Pillow** |
| **Versión Comprobada** | `12.3.0` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`12.3.0`) y Utilizada Efectivamente |
| **Para qué se utiliza** | Procesamiento y renderizado de imágenes digitales en Python; backend gráfico de `qrcode`. |
| **Ubicación de Verificación** | [`requirements.txt`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/requirements.txt#L3) |
| **Importancia** | Sin Pillow, `qrcode` no puede compilar matrices en formatos de imagen descargables (PNG/JPEG). |

#### 3. jsQR (JavaScript)
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **jsQR (minified)** |
| **Versión Comprobada** | Biblioteca JS embebida (`jsQR.min.js`, 130 KB) |
| **Nivel** | Instalada localmente en [`static/js/jsQR.min.js`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/js/jsQR.min.js) y Utilizada Efectivamente en el navegador |
| **Para qué se utiliza** | Decodificación óptica de códigos QR en tiempo real a partir de cuadros de video (`<video>` / `<canvas>`). |
| **Ubicación de Verificación** | [`static/js/jsQR.min.js`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/js/jsQR.min.js), [`templates/asistencia/control_asistencia.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/asistencia/control_asistencia.html#L470) |
| **Importancia** | Permite que el organizador utilice la cámara web del computador como escáner de asistencia sin comprar lectores externos. |
| **Ejemplo Concreto** | `const code = jsQR(imageData.data, imageData.width, imageData.height);` en el bucle `requestAnimationFrame`. |

---

### E. Generación y Exportación de Reportes

#### 1. ReportLab
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **ReportLab** |
| **Versión Comprobada** | `5.0.1` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`5.0.1`) y Utilizada Efectivamente |
| **Para qué se utiliza** | Generación programática de documentos PDF vectoriales (Planillas Imprimibles y Reportes Ejecutivos). |
| **Ubicación de Verificación** | [`reportes/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/reportes/services.py#L9-L16) |
| **Importancia** | Permite generar documentos oficiales descargables con membrete, tablas formateadas, totales y firmas sin guardar archivos en el servidor (stateless). |
| **Ejemplo Concreto** | Construcción de `SimpleDocTemplate(buffer, pagesize=letter)` y componentes `Table`, `Paragraph` y `Spacer`. |

#### 2. OpenPyXL
| Atributo | Detalle Comprobado |
| :--- | :--- |
| **Nombre** | **openpyxl** |
| **Versión Comprobada** | `3.1.5` |
| **Nivel** | Declarada (`requirements.txt`), Instalada (`3.1.5`) y Utilizada Efectivamente |
| **Para qué se utiliza** | Creación y formato de libros de cálculo en formato Excel nativo (`.xlsx`). |
| **Ubicación de Verificación** | [`analitica/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/analitica/services.py#L9), función `exportar_excel_analitica` |
| **Importancia** | Exporta consolidados tabulares de analítica e inscripciones con cabeceras estilizadas para análisis de gestión. |
| **Ejemplo Concreto** | `wb = Workbook(); ws = wb.active; ws.append([...]);` en `analitica/services.py`. |

---

### F. Frontend y Estilos Visuales

#### 1. HTML5 Semántico y Django Template Engine
- **Nivel:** Nativo de Django y HTML5 estándar.
- **Uso:** Estructuración de vistas mediante herencia de plantillas (`{% extends 'base.html' %}`, `{% block content %}`).
- **Ubicación:** Carpeta [`templates/`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/) y subdirectorios de cada aplicación.

#### 2. CSS Puro (Vanilla CSS) Institucional
- **Nivel:** Archivo propio del proyecto [`static/css/styles.css`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/static/css/styles.css) (21 KB).
- **Decisión de Arquitectura:** Se evitó intencionalmente el uso de frameworks pesados (Bootstrap/Tailwind) para garantizar control absoluto de estilos, cero dependencias de Node.js o CDN externas y máxima ligereza en conexiones móviles.
- **Paleta Institucional UNIMINUTO:**
  - Azul Institucional: `#002d62`
  - Dorado Institucional: `#eaaa00`
  - Gris Fondo: `#f8fafc`
  - Acentos de Éxito / Alerta: `#059669`, `#dc2626`

#### 3. Vanilla JavaScript
- **Nivel:** Scripts propios sin frameworks pesados (React/Vue/Angular).
- **Uso:**
  - Control de cámara web y canvas óptico en [`templates/asistencia/control_asistencia.html`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/templates/asistencia/control_asistencia.html).
  - Peticiones asíncronas con la API nativa `fetch()` y cabecera `X-CSRFToken`.
  - Sintetizador de audio web (`AudioContext`) para beeps de éxito y error en el escáner.

---

### G. Seguridad y Utilidades del Sistema

#### 1. django.core.signing (HMAC-SHA256)
- **Nivel:** Módulo nativo de la biblioteca de Django.
- **Uso:** Firma criptográfica y validación de tokens de pases QR individuales y QR común de salida.
- **Ubicación:** [`asistencia/services.py`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/asistencia/services.py#L4).

#### 2. tzdata
- **Versión Comprobada:** `2026.4` (Declarada en `requirements.txt`).
- **Uso:** Base de datos IANA de zonas horarias para sincronización precisa con `America/Bogota`.

---

## 3. Matriz Resumen de Dependencias

| Paquete / Componente | Versión | Tipo | ¿Declarada? | ¿Instalada? | ¿Usada en Código? | Módulo Principal de Uso |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Python** | 3.13.0 | Lenguaje | N/A | Sí | Sí | Todo el proyecto |
| **Django** | 6.1.1 | Framework Web | Sí | Sí | Sí | Todo el backend |
| **asgiref** | 3.12.1 | Utilidad ASGI | Sí | Sí | Sí | Ciclo HTTP Django |
| **sqlparse** | 0.6.0 | Analizador SQL | Sí | Sí | Sí | Django ORM / Migraciones |
| **tzdata** | 2026.4 | Zonas Horarias | Sí | Sí | Sí | Localización `America/Bogota` |
| **reportlab** | 5.0.1 | Generador PDF | Sí | Sí | Sí | `reportes` |
| **openpyxl** | 3.1.5 | Generador Excel | Sí | Sí | Sí | `analitica` |
| **pillow** | 12.3.0 | Imagen digital | Sí | Sí | Sí | `asistencia` (backend qrcode) |
| **qrcode** | 8.2 | Códigos QR | Sí | Sí | Sí | `asistencia` |
| **psycopg[binary]** | 3.3.6 | Driver PostgreSQL | Sí | Sí | Sí | `config` (Soporte PostgreSQL) |
| **gunicorn** | 23.0.0 | Servidor WSGI | Sí (Prod) | No (Windows) | Sí (Configurada) | `deploy/gunicorn_conf.py` |
| **jsQR** | 1.4.0 | Lector QR JS | No (Estático) | Sí (Local) | Sí | `asistencia` (Frontend) |
