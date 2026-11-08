# 01. RESUMEN EJECUTIVO Y ACADÉMICO DEL PROYECTO

**Sistema:** EventosSIGAE-UNIMINUTO  
**Nombre Completo:** Sistema Integrado de Gestión de Asistencia y Eventos  
**Institución:** Corporación Universitaria Minuto de Dios - UNIMINUTO  
**Framework:** Django 6.1.1 (Python 3.13.0)  
**Propósito del Documento:** Síntesis global, justificación de arquitectura y guion para sustentación oral ante docentes y evaluadores.

---

## 1. Problema que Busca Resolver

En las instituciones de educación superior como UNIMINUTO, la realización frecuente de eventos académicos (seminarios, congresos, simposios, talleres) y culturales enfrenta problemas recurrentes:
1. **Listados en papel:** Registro manual de asistencia propenso a pérdidas, deterioro, suplantación y datos ilegibles.
2. **Filas y cuellos de botella:** Procesos lentos de acreditación en el ingreso de los auditorios.
3. **Falta de trazabilidad y tiempo de permanencia:** Los sistemas tradicionales registran únicamente la llegada, desconociendo si el asistente permaneció durante el desarrollo del evento.
4. **Desarticulación de públicos:** Dificultad para gestionar simultáneamente a la comunidad interna (estudiantes, docentes, administrativos con cuenta) y al público externo (visitantes, conferencistas, egresados sin usuario en el sistema).
5. **Cálculo tardío de indicadores:** Generar certificados o consolidados estadísticos de cobertura y aforo suele tardar días tras la finalización del evento.

---

## 2. Objetivo General del Sistema

Diseñar e implementar una plataforma web centralizada, segura y escalable que digitalice el ciclo de vida completo de los eventos institucionales en UNIMINUTO, automatizando desde la publicación e inscripción pública hasta el control de acceso en tiempo real mediante códigos QR criptográficos (llegada individual y salida común), el cálculo automático de permanencia, la emisión de planillas/reportes ejecutivos en PDF y la trazabilidad exhaustiva de operaciones mediante una bitácora de auditoría.

---

## 3. Funcionalidades Principales Verificadas en el Código

El sistema cuenta con las siguientes capacidades implementadas y comprobadas:

| Módulo / Capacidad | Descripción Funcional Verificada | Implementación Técnica |
| :--- | :--- | :--- |
| **Catálogo Público de Eventos** | Búsqueda, filtros por categoría, modalidad (Presencial, Virtual, Híbrida), estado y cálculo en tiempo real de cupos disponibles. | `eventos/views.py`: `catalogo_eventos`, `detalle_evento` |
| **Gestión Integral de Eventos** | Creación, edición, consulta y cancelación formal con motivo obligatorio y preservación de inscripciones históricas. | `eventos/views.py`: `crear_evento`, `editar_evento`, `cancelar_evento` |
| **Inscripción Dual (Interna / Externa)** | - Usuarios autenticados: inscripción en 1 clic vinculando su perfil institucional.<br>- Participantes externos: formulario público con cédula y correo sin requerir contraseña previa. | `participantes/views.py`: `inscribirse_evento`, `obtener_o_crear_perfil_participante` |
| **Pase Digital con QR Criptográfico** | Emisión de pase web responsivo con QR firmado mediante HMAC-SHA256 (`django.core.signing`). No expone cédulas ni datos personales en el código. | `asistencia/services.py`: `generar_token_qr`, `generar_imagen_qr_bytes` |
| **Lector de Entrada con Cámara Web** | Consola del organizador con video en vivo vía `jsQR.min.js`, detección óptica instantánea, retroalimentación auditiva y registro atómico de llegada. | `asistencia/views.py`: `control_asistencia`, `templates/asistencia/control_asistencia.html` |
| **Flujo de Salida Móvil (QR Común)** | Código QR proyectado por el organizador que los asistentes escanean desde sus celulares para abrir una página móvil, identificarse con doble factor seguro (Cédula + Correo) y registrar su salida. | `asistencia/services.py`: `construir_url_salida_evento`, `asistencia/views.py`: `salida_evento_publica` |
| **Cálculo de Permanencia** | Cómputo exacto de minutos y horas de asistencia entre `hora_entrada` y `hora_salida`, incluyendo soporte para eventos nocturnos que cruzan la medianoche. | `asistencia/models.py`: propiedad `permanencia`, `asistencia/services.py`: `calcular_permanencia_promedio` |
| **Reportes Ejecutivos en PDF** | Generación bajo demanda en memoria (stateless con `ReportLab`) de la Planilla Imprimible de Asistencia y el Reporte Consolidado con indicadores y firmas. | `reportes/services.py`: `generar_pdf_planilla_asistencia`, `generar_pdf_reporte_consolidado` |
| **Dashboard y Analítica** | Métricas de aforo, porcentaje de asistencia, permanencia promedio, distribución por categorías/modalidades y exportación a CSV y Excel (`openpyxl`). | `analitica/views.py`: `dashboard`, `exportar_csv`, `exportar_excel` |
| **Bitácora Inmutable de Auditoría** | Registro cronológico automático de acciones críticas (inicios de sesión, cancelaciones, asistencias, descargas de reportes) con usuario, IP real y timestamp. | `auditoria/models.py`: `Auditoria`, `auditoria/views.py`: `consulta_auditoria` |
| **Endpoint de Monitoreo / Salud** | Verificación técnica de disponibilidad y conectividad a base de datos (`SELECT 1`) en `/health/` retornando HTTP 200/503 en formato JSON. | `config/views.py`: `health_check` |

---

## 4. Roles y Tipos de Usuarios Reales en el Sistema

El sistema maneja dos capas de clasificación verificadas en el modelo de datos:

### A. Roles de Sistema (`usuarios.models.Rol` y `Usuario.rol`)
1. **Administrador:** Acceso completo a gestión de eventos, supervisión de todos los organizadores, consulta de bitácora de auditoría y reportes institucionales.
2. **Coordinador:** Gestión de eventos de su área o facultad, revisión de métricas y descarga de reportes.
3. **Docente:** Creación y gestión de sus propios eventos, control de asistencia por cámara y descarga de actas.
4. **Estudiante:** Consulta de catálogo público, auto-inscripción a eventos y visualización de sus pases digitales en "Mis Inscripciones".

*(Adicionalmente, los superusuarios o staff nativos de Django cuentan con acceso al panel técnico `/admin/`).*

### B. Tipos de Participantes (`participantes.models.TipoParticipante`)
Clasificación de las personas que asisten a los eventos:
`ESTUDIANTE`, `DOCENTE`, `ADMINISTRATIVO`, `EGRESADO`, `EXTERNO`, `OTRO`.

---

## 5. Flujo General de Operación

```text
[ Profesor / Organizador ]
           │
           ▼
    1. Crea Evento (Fecha, Cupo, Modalidad, Categoría)
           │
           ▼
    2. Publica el Evento en el Catálogo Institucional
           │
           ├──────────────────────────────┬──────────────────────────────┐
           ▼                                                             ▼
[ Estudiante Autenticado ]                                   [ Participante Externo ]
3. Inicia sesión institucional                               4. Ingresa al enlace público
5. Se inscribe en 1 clic                                     6. Diligencia Cédula + Correo
           │                                                             │
           └──────────────────────────────┬──────────────────────────────┘
                                          ▼
                         7. Obtiene Pase Digital con QR Criptográfico
                            (Descarga PNG o guarda en el móvil)
                                          │
                                          ▼ [ DÍA DEL EVENTO ]
                         8. El Operador escanea el QR en la entrada
                            (Cámara web / jsQR registra Check-in)
                                          │
                                          ▼
                         9. Al finalizar, el Organizador habilita Salidas
                            y proyecta el QR Común del Evento
                                          │
                                          ▼
                         10. El Asistente escanea el QR con su Celular
                             Confirma su salida (Doble factor seguro)
                                          │
                                          ▼
                         11. El Sistema calcula la Permanencia Efectiva
                             (Ej. "1h 45m" y actualiza métricas en vivo)
                                          │
                                          ▼
                         12. El Organizador descarga Planilla PDF y
                             consulta el Dashboard Estadístico
```

---

## 6. Arquitectura General del Sistema

El proyecto implementa el patrón **MVT (Model-View-Template)** característico de Django, complementado con una **capa de servicios desacoplada**:

1. **Modelos (`models.py`):** Estructura relacional con validaciones de negocio en el método `clean()` (integridad temporal, aforos, estados).
2. **Vistas (`views.py`):** Coordinación HTTP, control de acceso mediante decoradores (`@login_required`) y permisos por rol.
3. **Servicios (`services.py`):** Lógica de negocio pesada separada de las vistas (criptografía HMAC de códigos QR, cálculo matemático de permanencia, dibujo vectorial de PDFs con ReportLab, agregaciones analíticas).
4. **Plantillas (`templates/`):** Renderizado del lado del servidor con diseño visual adaptativo (Vanilla CSS institucional y HTML5 semántico).
5. **Base de Datos Dual:**
   - Desarrollo y pruebas: SQLite (`db.sqlite3` / `db.sqlite3.demo` vía variable `SIGAE_DB_PATH`).
   - Preparación para producción: PostgreSQL 16 vía variables de entorno (`DATABASE_URL` o `DB_ENGINE`).

---

## 7. Estado Actual del Proyecto

- **Estado Funcional:** 100% operativo en entorno local.
- **Suite de Pruebas Automatizadas:** 135 pruebas automatizadas implementadas y certificadas con resultado `OK` en todos los módulos (`usuarios`, `eventos`, `participantes`, `asistencia`, `reportes`, `analitica`, `auditoria`).
- **Aislamiento de Datos:** La base de datos original (`db.sqlite3`) se encuentra íntegra y protegida bajo el hash SHA-256 verificado `C30E8081B9E631C804E6B94081F2F252C82D53D8508E3FFD049608C722F290D0`. Todas las pruebas y ejecuciones se realizan sobre `db.sqlite3.demo`.
- **Despliegue:** Artefactos de endurecimiento para Linux (Gunicorn, Nginx, Systemd) preparados en la carpeta `deploy/`, sin haber iniciado despliegue en servidores públicos.

---

## 8. Funcionalidades Verificadas vs. Funcionalidades No Implementadas

Para garantizar máxima honestidad académica durante la sustentación:

### Verificadas y Comprobadas en Código:
- [x] Registro y autenticación por sesión.
- [x] Recuperación de contraseña vía correo de consola (tokens nativos).
- [x] Catálogo con filtros y control estricto de cupos.
- [x] Inscripción institucional y formulario para externos.
- [x] Generación y renderizado de QR con HMAC-SHA256.
- [x] Lectura de QR desde cámara web del PC con biblioteca JavaScript cliente.
- [x] Check-in y Check-out con validación de no duplicidad.
- [x] Cálculo de permanencia exacta y cálculo de promedio.
- [x] Generación de PDF sin persistencia en disco (ReportLab).
- [x] Exportación a Excel (`openpyxl`) y CSV.
- [x] Bitácora inmutable de auditoría con captura de IP.
- [x] Endpoint de salud `/health/`.

### No Implementadas o Fuera de Alcance:
- [ ] No existe integración con pasarelas de pago (los eventos son de carácter institucional gratuito).
- [ ] No existe una aplicación móvil nativa (Android/iOS en APK o Swift); el sistema es una **Web App Responsiva** que opera en navegadores móviles.
- [ ] No hay reconocimiento facial ni biometría por hardware; el acceso se basa en QR y cédula.
- [ ] El envío de correos en desarrollo utiliza el backend de consola (`console.EmailBackend`); no emite correos reales a bandejas de entrada a menos que se configure un servidor SMTP real.

---

## 9. Guion para Explicación Oral de 2 Minutos (Elevator Pitch)

> *"Buenos días, profesor. Mi proyecto se titula **EventosSIGAE-UNIMINUTO**, y es una plataforma integral desarrollada sobre **Django 6.1** y **Python 3.13** para resolver la gestión manual, lenta e inexacta de eventos y asistencias en la universidad.*
>
> *El sistema cubre tres momentos clave:*
>
> *Primero, la **gestión e inscripción**: los docentes y coordinadores publican eventos con cupos controlados. Los estudiantes se inscriben con su cuenta institucional y los asistentes externos mediante un formulario público. Al inscribirse, el sistema les genera de inmediato un **Pase Digital con código QR firmado criptográficamente con HMAC-SHA256**, lo que garantiza que nadie pueda alterar su identidad ni falsificar entradas.*
>
> *Segundo, el **control de acceso ágil**: el día del evento, el organizador abre la consola de asistencia en su computador y, usando la cámara web integrada mediante la librería JavaScript `jsQR`, escanea los pases de los asistentes en segundos, registrando la llegada sin contacto y en tiempo real. Al finalizar el evento, el sistema proyecta un **QR común de salida** que los participantes escanean desde sus teléfonos celulares para confirmar su salida mediante un doble factor seguro (cédula y correo). Con esto, el sistema calcula automáticamente el **tiempo real de permanencia** de cada persona y maneja eventos nocturnos con cruce de medianoche.*
>
> *Y tercero, la **toma de decisiones y auditoría**: la plataforma genera en tiempo real actas y planillas de asistencia en PDF vectorial mediante `ReportLab`, exporta consolidados a Excel y CSV, y alimenta un **Dashboard analítico** de aforo y permanencia. Todo esto respaldado por una **bitácora de auditoría inmutable** que registra cada acción con usuario, IP y fecha para máxima seguridad institucional.*
>
> *El proyecto cuenta con una arquitectura modular de siete aplicaciones, 135 pruebas automatizadas aprobadas y soporte dual para SQLite y PostgreSQL."*
