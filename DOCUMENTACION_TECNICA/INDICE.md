# ÍNDICE GENERAL DE LA DOCUMENTACIÓN TÉCNICA

**Sistema:** EventosSIGAE-UNIMINUTO (Sistema Integrado de Gestión de Asistencia y Eventos)  
**Institución:** Corporación Universitaria Minuto de Dios - UNIMINUTO  
**Tecnologías:** Python 3.13.0, Django 6.1.1, ReportLab 5.0.1, QrCode 8.2, OpenPyXL 3.1.5, jsQR  
**Fecha de Certificación:** Octubre de 2026  

---

## 1. Propósito de la Suite Documental

Esta colección de documentos técnicos y guías de estudio ha sido elaborada para servir como soporte integral durante la **sustentación académica y técnica** del proyecto ante docentes y jurados evaluadores. Todo el contenido está fundamentado **exclusivamente en el código fuente real**, las pruebas automatizadas verificadas y la arquitectura relacional activa en el repositorio.

---

## 2. Estructura de la Documentación

A continuación se listan los documentos especializados que componen la carpeta [`DOCUMENTACION_TECNICA/`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA):

| Documento | Título y Enlace | Propósito Principal |
| :---: | :--- | :--- |
| **01** | [`01_RESUMEN_DEL_PROYECTO.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/01_RESUMEN_DEL_PROYECTO.md) | Resumen ejecutivo, problemática institucional, objetivos, alcance verificado, roles y **discurso de 2 minutos para apertura oral**. |
| **02** | [`02_TECNOLOGIAS_Y_LIBRERIAS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/02_TECNOLOGIAS_Y_LIBRERIAS.md) | Inventario real y exhaustivo de dependencias, diferenciando dependencias declaradas, instaladas y utilizadas en código. |
| **03** | [`03_MAPA_DEL_CODIGO.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/03_MAPA_DEL_CODIGO.md) | Mapa de navegación por carpetas y archivos, responsabilidades por módulo, desacoplamiento de la capa de servicios y tabla de búsqueda rápida. |
| **04** | [`04_FLUJOS_FUNCIONALES.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/04_FLUJOS_FUNCIONALES.md) | Documentación paso a paso de los 14 procesos del sistema (autenticación, eventos, pases QR, lectura por cámara, salida móvil y permanencia). |
| **05** | [`05_BASE_DE_DATOS_Y_MODELOS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/05_BASE_DE_DATOS_Y_MODELOS.md) | Especificación de los 8 modelos, claves primarias, claves foráneas, restricciones únicas, migraciones y **Diagrama Entidad-Relación en Mermaid**. |
| **06** | [`06_SEGURIDAD_Y_PERMISOS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/06_SEGURIDAD_Y_PERMISOS.md) | Arquitectura de seguridad: RBAC, criptografía HMAC-SHA256 en tokens QR, defensas contra OWASP (CSRF, XSS, Clickjacking) y bitácora de auditoría. |
| **07** | [`07_PRUEBAS_Y_ESTADO_ACTUAL.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/07_PRUEBAS_Y_ESTADO_ACTUAL.md) | Estrategia de pruebas automatizadas: distribución de los **135 tests aprobados**, escenarios críticos comprobados y puntos para demostrar en vivo. |
| **08** | [`08_GUIA_DE_SUSTENTACION.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/08_GUIA_DE_SUSTENTACION.md) | **Documento central de estudio**: discursos de 2 y 5 minutos, banco de 19 preguntas difíciles con respuestas sugeridas, tabla rápida y guion de demostración. |
| **09** | [`09_GLOSARIO_TECNICO.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/09_GLOSARIO_TECNICO.md) | Glosario conceptual riguroso y accesible, distinguiendo conceptos implementados de conceptos teóricos generales. |
| **10** | [`10_COMANDOS_Y_SOLUCION_DE_PROBLEMAS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/10_COMANDOS_Y_SOLUCION_DE_PROBLEMAS.md) | Manual operativo de comandos seguros, uso de `SIGAE_DB_PATH`, preservación de la BD original y matriz de resolución de problemas. |

---

## 3. Rutas Recomendadas de Lectura

Dependiendo de tu objetivo inmediato, sigue una de estas tres rutas pedagógicas:

### Ruta A: Preparación Rápida para la Sustentación Oral (1 a 2 horas)
Para estudiar y memorizar los argumentos clave antes de presentar el proyecto:
1. Iniciar con [`01_RESUMEN_DEL_PROYECTO.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/01_RESUMEN_DEL_PROYECTO.md) para dominar el problema, objetivo y el *Pitch* de 2 minutos.
2. Estudiar [`08_GUIA_DE_SUSTENTACION.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/08_GUIA_DE_SUSTENTACION.md) para repasar el banco de preguntas y practicar el guion de demostración en vivo.
3. Consultar [`04_FLUJOS_FUNCIONALES.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/04_FLUJOS_FUNCIONALES.md) en los flujos de lectura QR y permanencia (Flujos 6, 7, 8, 9 y 10).

### Ruta B: Comprensión Técnica Profunda de la Arquitectura (3 a 4 horas)
Para responder preguntas complejas sobre diseño de software y código:
1. Leer [`03_MAPA_DEL_CODIGO.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/03_MAPA_DEL_CODIGO.md) para ubicar dónde reside cada responsabilidad.
2. Analizar el modelo relacional en [`05_BASE_DE_DATOS_Y_MODELOS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/05_BASE_DE_DATOS_Y_MODELOS.md) y su diagrama Mermaid ER.
3. Revisar los mecanismos de defensa y criptografía en [`06_SEGURIDAD_Y_PERMISOS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/06_SEGURIDAD_Y_PERMISOS.md).
4. Contrastar las librerías comprobadas en [`02_TECNOLOGIAS_Y_LIBRERIAS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/02_TECNOLOGIAS_Y_LIBRERIAS.md).

### Ruta C: Puesta en Marcha y Demostración Práctica
Para preparar el computador antes de la presentación:
1. Seguir [`10_COMANDOS_Y_SOLUCION_DE_PROBLEMAS.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/10_COMANDOS_Y_SOLUCION_DE_PROBLEMAS.md) para levantar el servidor sobre `db.sqlite3.demo` en `0.0.0.0:8000`.
2. Verificar que las 135 pruebas automatizadas pasen según [`07_PRUEBAS_Y_ESTADO_ACTUAL.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/07_PRUEBAS_Y_ESTADO_ACTUAL.md).
3. Seguir el guion paso a paso de la Sección 4 de [`08_GUIA_DE_SUSTENTACION.md`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA/08_GUIA_DE_SUSTENTACION.md).

---

## 4. Garantía de Integridad del Repositorio

- **Archivos de Código Modificados:** Cero (0). No se alteró ningún modelo, vista, formulario, ruta, plantilla ni servicio.
- **Bases de Datos Afectadas:** Cero (0). La base de datos original [`db.sqlite3`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3) conserva de manera verificable su hash SHA-256 intacto:  
  `C30E8081B9E631C804E6B94081F2F252C82D53D8508E3FFD049608C722F290D0`.
- **Archivos Creados:** Exclusivamente los 11 archivos Markdown dentro del directorio [`DOCUMENTACION_TECNICA/`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/DOCUMENTACION_TECNICA).
