# 07. ESTRATEGIA DE PRUEBAS, COBERTURA Y ESTADO ACTUAL

**Sistema:** EventosSIGAE-UNIMINUTO  
**Suite de Pruebas:** Django Test Runner (`django.test.TestCase`, `Client`)  
**Propósito:** Detallar la arquitectura de pruebas automatizadas, los 135 casos de prueba comprobados en el código, los escenarios de validación funcional y la guía de demostración para evaluación académica.

---

## 1. Organización de la Suite de Pruebas Automatizadas

El proyecto utiliza el marco nativo de pruebas de Django (`django.test`), basado en el estándar `unittest` de Python.
- **Aislamiento por Diseño:** Al ejecutar `python manage.py test`, Django crea automáticamente una base de datos temporal en memoria o en archivo temporal con prefijo `test_`, ejecuta las migraciones, corre cada prueba dentro de una transacción atómica que se revierte (`rollback`) al finalizar y destruye la base de prueba al terminar.
- **Protección de Datos Reales:** La base de datos original [`db.sqlite3`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3) y la base de demostración [`db.sqlite3.demo`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3.demo) **nunca son tocadas ni alteradas** por la suite de pruebas.

---

## 2. Cobertura y Distribución de Pruebas por Módulo

El inventario verificado en el código fuente registra **135 pruebas automatizadas**, distribuidas en las siete aplicaciones:

```text
┌────────────────────────────────────────────────────────────────────────┐
│               DISTRIBUCIÓN DE PRUEBAS AUTOMATIZADAS                    │
├────────────────────────────┬──────────────┬────────────────────────────┤
│ Aplicación / Módulo        │ N° Pruebas   │ Archivo Fuente             │
├────────────────────────────┼──────────────┼────────────────────────────┤
│ usuarios                   │  10 tests    │ usuarios/tests.py          │
│ eventos                    │  18 tests    │ eventos/tests.py           │
│ participantes              │  16 tests    │ participantes/tests.py     │
│ asistencia                 │  49 tests    │ asistencia/tests.py        │
│ reportes                   │  12 tests    │ reportes/tests.py          │
│ analitica                  │  18 tests    │ analitica/tests.py         │
│ auditoria                  │  12 tests    │ auditoria/tests.py         │
├────────────────────────────┼──────────────┼────────────────────────────┤
│ TOTAL DE CASOS VERIFICADOS │ 135 tests    │ Suite Completa             │
└────────────────────────────┴──────────────┴────────────────────────────┘
```

---

## 3. Escenarios Críticos Verificados por Módulo

### A. Módulo `usuarios` (10 pruebas)
- `test_crear_usuario`: Creación correcta de usuarios con `documento`, `nombres`, `apellidos`, `email` y rol asignado.
- `test_documento_unico`: Rechazo de creación con documento duplicado.
- `test_email_unico`: Rechazo de creación con correo electrónico duplicado.
- `test_login_credenciales_correctas`: Inicio de sesión exitoso, emisión de sesión y auditoría.
- `test_login_credenciales_incorrectas`: Rechazo de login con aviso de error seguro.
- `test_logout`: Cierre de sesión y destrucción de cookie.
- `test_password_reset_solicitud`: Solicitud de restablecimiento vía token de un solo uso sin revelar si el correo existe.

### B. Módulo `eventos` (18 pruebas)
- `test_crear_evento_valido`: Creación de evento con fecha, horas y lugar válidos.
- `test_validacion_hora_fin_anterior_inicio`: El validador `clean()` rechaza eventos donde `hora_fin <= hora_inicio`.
- `test_catalogo_eventos_filtros`: Filtrado por categoría, modalidad (`PRESENCIAL`, `VIRTUAL`, `HIBRIDA`) y estado.
- `test_calculo_cupos_disponibles`: Comprueba que `cupos_disponibles = cupo - total_activos`.
- `test_edicion_evento_organizador`: El organizador puede editar su evento.
- `test_edicion_evento_denegada_tercero`: Un usuario no organizador recibe HTTP 403.
- `test_cancelar_evento_con_motivo`: Cancelación formal con motivo obligatorio y preservación de inscripciones históricas.

### C. Módulo `participantes` (16 pruebas)
- `test_inscripcion_usuario_autenticado`: Inscripción en 1 clic para usuarios con cuenta.
- `test_inscripcion_participante_externo`: Inscripción pública sin cuenta con datos de contacto.
- `test_inscripcion_rechazada_evento_cancelado`: Bloqueo de inscripciones si el evento no está publicado.
- `test_inscripcion_rechazada_cupo_lleno`: Bloqueo seguro cuando el aforo llega al 100%.
- `test_inscripcion_duplicada_evitada`: La restricción única de BD y la vista evitan duplicidad.
- `test_reactivacion_inscripcion_cancelada`: Si un participante cancela y se inscribe de nuevo, reactiva la fila existente.
- `test_cancelar_inscripcion_propia`: El participante puede cancelar su inscripción si no tiene asistencia registrada.
- `test_cancelar_inscripcion_con_asistencia_denegada`: No se permite cancelar inscripciones con llegada registrada.

### D. Módulo `asistencia` (49 pruebas - Núcleo Operativo)
- **Criptografía de Pases QR:**
  - `test_token_qr_firma_valida`: Token HMAC-SHA256 generado correctamente.
  - `test_token_qr_manipulado_rechazado`: Cualquier alteración de caracteres en el token produce rechazo HTTP 403.
  - `test_token_qr_otro_evento_rechazado`: Un token firmado de otro evento es detectado y denegado.
  - `test_descarga_qr_imagen_png`: El endpoint binario retorna un archivo con cabeceras `image/png` y encabezado `\x89PNG`.
- **Lector de Entrada (Cámara Web / Consola):**
  - `test_control_asistencia_requiere_permiso`: Estudiantes o docentes ajenos reciben HTTP 403.
  - `test_registro_llegada_exitoso`: Marca asistencia, hora de entrada y auditoría.
  - `test_registro_llegada_duplicada_rechazada`: Impide marcar llegada dos veces al mismo participante.
  - `test_qr_salida_escaneado_en_lector_operador_rechazado_con_aviso_especifico`: Si el operador escanea el QR común de salida en lugar de un pase, responde con código `QR_SALIDA_COMUN_NO_ES_PASE`.
- **Flujo de Salida Móvil y Permanencia:**
  - `test_construir_url_salida_evento_red_local`: La URL del QR no usa `127.0.0.1` sino la IP de red local para acceso móvil.
  - `test_salida_sin_entrada_previa`: Rechaza el check-out si el participante no tiene llegada registrada.
  - `test_salida_duplicada`: Impide registrar check-out más de una vez.
  - `test_salida_con_registro_deshabilitado`: Si el organizador pausa salidas, el formulario rechaza intentos.
  - `test_salida_con_correo_incorrecto_rechazada`: Doble factor de seguridad: si la cédula existe pero el correo no coincide, rechaza la operación.
  - `test_salida_con_documento_y_correo_correctos_exitosa`: Registra la salida, calcula la permanencia y actualiza filtros.
  - `test_calculo_correcto_permanencia_promedio`: Comprueba el cálculo matemático de permanencia en minutos y horas.
  - `test_cruce_medianoche`: Valida la transición temporal en eventos nocturnos.

### E. Módulo `reportes` (12 pruebas)
- `test_planilla_pdf_generacion_correcta`: Genera PDF binario en memoria sin errores.
- `test_planilla_pdf_requiere_autenticacion`: Redirige anónimos al login.
- `test_planilla_pdf_permisos_restringidos`: Usuarios sin permisos de gestión reciben HTTP 403.
- `test_reporte_consolidado_pdf_metricas`: Valida la presencia de totales, aforo y permanencia en el reporte.
- `test_auditoria_descarga_pdf`: La descarga exitosa genera un registro en la bitácora de auditoría.

### F. Módulo `analitica` (18 pruebas)
- `test_dashboard_acceso_gestion`: Solo usuarios con rol de gestión o administradores pueden acceder.
- `test_metricas_calculo_porcentajes`: Comprueba fórmulas de porcentaje de asistencia y aforo.
- `test_exportacion_csv_formato`: El archivo CSV generado contiene codificación UTF-8 con cabeceras correctas.
- `test_exportacion_excel_valida`: El libro generado contiene cabeceras estilizadas y filas de datos coincidentes.

### G. Módulo `auditoria` (12 pruebas)
- `test_consulta_auditoria_solo_administrador`: Restringe la consulta exclusivamente al rol `Administrador`.
- `test_inmutabilidad_auditoria`: El modelo no expone vistas ni formularios de edición o borrado.
- `test_filtros_auditoria`: Filtrado por módulo, acción, usuario y rango de fechas.

---

## 4. Comandos para Ejecutar las Pruebas de Forma Segura

Para ejecutar las pruebas sin tocar las bases de datos de producción ni desarrollo:

### Ejecutar las 49 pruebas del módulo de asistencia:
```powershell
.\.venv\Scripts\python.exe manage.py test asistencia
```

### Ejecutar las 135 pruebas completas del proyecto:
```powershell
.\.venv\Scripts\python.exe manage.py test
```

### Ejecutar pruebas con reporte de detalle (Verbose):
```powershell
.\.venv\Scripts\python.exe manage.py test asistencia -v 2
```

---

## 5. Diferencia entre Pruebas Automatizadas y Pruebas Manuales

Es clave que en la sustentación puedas explicar la complementariedad de ambas:

| Criterio | Pruebas Automatizadas (Django Test Suite) | Pruebas Manuales de Validación |
| :--- | :--- | :--- |
| **Entorno** | Base de datos virtual temporal en memoria (`test_db`). | Base de datos de demostración ([`db.sqlite3.demo`](file:///c:/Users/cristian.fresnosG/Desktop/Python/SIGAE-UNIMINUTO/db.sqlite3.demo)). |
| **Objetivo** | Verificar que el código no tenga regresiones, que los modelos validen restricciones y que los algoritmos matemáticos y criptográficos funcionen. | Comprobar la experiencia visual del usuario, el flujo en navegadores móviles reales y el funcionamiento físico de la cámara web. |
| **Velocidad** | 135 pruebas se ejecutan en aproximadamente 100 segundos. | Ejecución guiada paso a paso por el evaluador. |
| **Dispositivos** | Simulados mediante `django.test.Client`. | Dispositivos físicos reales (Laptop con cámara + Teléfono celular en red Wi-Fi). |

---

## 6. Funcionalidades Recomendadas para Demostrar al Profesor

Durante la sustentación, se recomienda enfocar la demostración práctica en los siguientes puntos de alto impacto:

1. **Catálogo y Registro Dual:**
   - Mostrar el catálogo con cupos en vivo.
   - Inscribir a un usuario externo demostrando que no requiere cuenta previa y obtiene su pase de inmediato.
2. **Pase Digital y Criptografía QR:**
   - Mostrar el pase digital responsivo y explicar que el QR no expone la cédula sino un token firmado con HMAC-SHA256.
3. **Consola del Operador con Cámara Web:**
   - Abrir `/asistencia/evento/1/control/` y permitir que la cámara del PC escanee el pase digital de un asistente.
   - Mostrar cómo se produce el beep sonoro y la fila se actualiza a "Asistió" sin recargar la pantalla.
4. **Demostración de Rechazo Inteligente:**
   - Intentar escanear el QR común de salida en la cámara del operador: mostrar el mensaje explicativo (`QR_SALIDA_COMUN_NO_ES_PASE`).
5. **Check-out y Permanencia:**
   - Escanear el QR de salida común o abrir la página móvil de salida.
   - Confirmar la salida con cédula y correo.
   - Mostrar en pantalla el cálculo automático de permanencia (ej. *"Permanencia: 1h 30m"*).
6. **Descarga de Planilla Oficial en PDF:**
   - Descargar la planilla generada con ReportLab y mostrar el membrete institucional, la lista de asistentes y los espacios de firma.
7. **Bitácora de Auditoría:**
   - Ingresar con rol Administrador a `/auditoria/` y evidenciar que cada una de las acciones anteriores quedó registrada con IP, hora y usuario.
