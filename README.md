# EventosSIGAE-UNIMINUTO 🎓🏛️

**SIGAE** (Sistema Integrado de Gestión de Asistencia y Eventos) es una solución institucional desarrollada sobre Django para la gestión integral del ciclo de vida de eventos académicos, culturales y corporativos en la **Corporación Universitaria Minuto de Dios - UNIMINUTO**.

---

## 📁 Estructura del Proyecto

```text
EventosSIGAE-UNIMINUTO/
│
├── .venv/                      # Entorno virtual aislado de Python
│
├── manage.py                   # Utilidad CLI principal de Django
│
├── config/                     # Configuración principal del proyecto
│   ├── __init__.py
│   ├── settings.py             # Configuración central (apps, i18n es-co, tz Bogotá, static/media)
│   ├── urls.py                 # Enrutador principal del sistema
│   ├── asgi.py
│   └── wsgi.py
│
├── usuarios/                   # Gestión de usuarios, autenticación y perfiles
│   ├── migrations/
│   ├── templates/usuarios/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   └── forms.py
│
├── eventos/                    # Gestión, programación y estado de eventos
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── participantes/              # Registro e inscripción de la comunidad institucional y externos
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── asistencia/                 # Control de asistencia y validación en tiempo real (QR, check-in)
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── reportes/                   # Generación y exportación de informes (PDF, Excel, certificados)
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── analitica/                  # Indicadores de asistencia, métricas e impacto institucional
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── auditoria/                  # Bitácoras de trazabilidad, seguridad y logs de operaciones
│   ├── migrations/
│   ├── admin.py, apps.py, models.py, urls.py, views.py, forms.py
│
├── templates/                  # Plantillas globales del proyecto
│   └── base.html               # Plantilla maestra institucional
│
├── static/                     # Archivos estáticos globales
│   ├── css/
│   │   └── styles.css          # Estilos institucionales UNIMINUTO
│   ├── js/
│   │   └── main.js
│   └── img/
│
├── media/                      # Archivos cargados por usuarios (logos, firmas, certificados)
│
├── requirements.txt            # Dependencias del proyecto
├── .gitignore                  # Exclusiones de control de versiones
└── README.md                   # Documentación general
```

---

## 🚀 Requisitos e Instalación

### 1. Prerrequisitos
- Python 3.12+ (Probado con Python 3.13)
- Git

### 2. Activación del Entorno Virtual

En Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```

En Windows (CMD):
```cmd
.\.venv\Scripts\activate.bat
```

En Linux / macOS:
```bash
source .venv/bin/activate
```

### 3. Instalación de Dependencias
```powershell
pip install -r requirements.txt
```

### 4. Migraciones Iniciales
```powershell
python manage.py migrate
```

### 5. Crear Superusuario (Administrador)
```powershell
python manage.py createsuperuser
```

### 6. Ejecutar Servidor de Desarrollo
```powershell
python manage.py runserver
```

Acceder en el navegador a: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🧩 Módulos del Sistema

| Módulo | Responsabilidad Principal |
| :--- | :--- |
| **`usuarios`** | Autenticación, roles (administrador, docente, organizador, estudiante) y perfiles institucionales. |
| **`eventos`** | Creación y administración de eventos, fechas, auditorios, cupos y categorías. |
| **`participantes`** | Registro e inscripción de asistentes internos y externos a los eventos. |
| **`asistencia`** | Registro y toma de asistencia digital mediante lectura QR y verificación de asistencia. |
| **`reportes`** | Generación de certificados de asistencia, listados en Excel y actas en PDF. |
| **`analitica`** | Dashboards y tableros estadísticos con métricas de cobertura y participación. |
| **`auditoria`** | Registro cronológico inmutable de actividades y trazabilidad de seguridad. |

---

## 🎨 Configuración Institucional
- **Idioma**: `es-co` (Español Colombia).
- **Zona Horaria**: `America/Bogota` (Hora legal de Colombia).
- **Paleta de Colores**:
  - Azul Institucional: `#002d62`
  - Dorado UNIMINUTO: `#eaaa00`
  - Gris Fondo: `#f8fafc`
