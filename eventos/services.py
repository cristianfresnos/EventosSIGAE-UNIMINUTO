"""
Servicios de dominio para el sistema obligatorio de calificación de eventos mediante estrellas (RF-24 a RF-30).
Proyecto: EventosSIGAE-UNIMINUTO
"""

from django.db import transaction, IntegrityError
from django.db.models import Avg, Count, Exists, OuterRef, Q

from auditoria.models import Auditoria
from asistencia.models import Asistencia, EstadoAsistencia
from participantes.models import AccesoExternoInscripcion, Inscripcion, EstadoInscripcion
from .models import CalificacionEvento


ETIQUETAS_ESTRELLAS = dict(CalificacionEvento.ETIQUETAS_PUNTUACION)
MENSAJE_SIN_CALIFICACIONES = "Este evento todavía no tiene calificaciones registradas"


def es_estudiante_elegible_rol(user):
    """
    Determina si el usuario autenticado posee exclusivamente el rol institucional Estudiante.
    Los administradores, coordinadores, docentes, staff y superusuarios no pueden calificar
    eventos en nombre de estudiantes (RF-25, RF-28).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff:
        return False
    rol = getattr(user, 'rol', None)
    if not rol or getattr(rol, 'nombre', None) != 'Estudiante':
        return False
    return True


def verificar_elegibilidad_calificacion(user, evento):
    """
    Valida en backend todas las condiciones de elegibilidad para calificar un evento (RF-25):
    1. Usuario autenticado.
    2. Rol institucional Estudiante (no docente ni administrador).
    3. Inscripción activa y válida en el evento.
    4. Registro de entrada válido (Asistencia REGISTRADA con hora_entrada).
    5. Registro de salida válido (hora_salida confirmada).

    No depende del estado global FINALIZADO del evento: el estudiante puede calificar
    inmediatamente después de registrar su salida individual.

    Retorna diccionario con:
      - elegible (bool)
      - codigo (str)
      - mensaje (str)
      - inscripcion (Inscripcion | None)
      - asistencia (Asistencia | None)
      - calificacion_existente (CalificacionEvento | None)
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return {
            'elegible': False,
            'codigo': 'NO_AUTENTICADO',
            'mensaje': 'Debes iniciar sesión con tu cuenta estudiantil para calificar este evento.',
            'inscripcion': None,
            'asistencia': None,
            'calificacion_existente': None,
        }

    if not es_estudiante_elegible_rol(user):
        return {
            'elegible': False,
            'codigo': 'ROL_NO_AUTORIZADO',
            'mensaje': 'Solo los estudiantes participantes pueden registrar o actualizar calificaciones de eventos.',
            'inscripcion': None,
            'asistencia': None,
            'calificacion_existente': None,
        }

    inscripcion = (
        Inscripcion.objects
        .select_related('participante', 'asistencia', 'evento')
        .filter(
            evento=evento,
            participante__usuario=user,
            estado=EstadoInscripcion.ACTIVA,
        )
        .first()
    )
    if not inscripcion:
        return {
            'elegible': False,
            'codigo': 'SIN_INSCRIPCION_VALIDA',
            'mensaje': 'No cuentas con una inscripción válida y activa en este evento para calificarlo.',
            'inscripcion': None,
            'asistencia': None,
            'calificacion_existente': None,
        }

    asistencia = Asistencia.objects.filter(inscripcion=inscripcion).first()
    if not asistencia or asistencia.estado != EstadoAsistencia.REGISTRADA or not asistencia.hora_entrada:
        return {
            'elegible': False,
            'codigo': 'SIN_ENTRADA_REGISTRADA',
            'mensaje': 'Debes contar con un registro de entrada confirmado en este evento antes de calificarlo.',
            'inscripcion': inscripcion,
            'asistencia': asistencia,
            'calificacion_existente': None,
        }

    if not asistencia.hora_salida:
        return {
            'elegible': False,
            'codigo': 'SIN_SALIDA_REGISTRADA',
            'mensaje': 'Debes registrar tu salida mediante el código QR del evento antes de enviar tu calificación.',
            'inscripcion': inscripcion,
            'asistencia': asistencia,
            'calificacion_existente': None,
        }

    calificacion_existente = CalificacionEvento.objects.filter(
        Q(evento=evento, estudiante=user) | Q(inscripcion=inscripcion)
    ).first()

    return {
        'elegible': True,
        'codigo': 'ELEGIBLE_ACTUALIZACION' if calificacion_existente else 'ELEGIBLE_NUEVA',
        'mensaje': 'Elegible para calificar el evento.',
        'inscripcion': inscripcion,
        'asistencia': asistencia,
        'calificacion_existente': calificacion_existente,
    }


def verificar_elegibilidad_calificacion_externa(inscripcion, evento=None, acceso_externo=None):
    """
    Valida estrictamente en backend todas las condiciones de elegibilidad para que un
    participante externo (usuario_id=NULL) califique un evento usando su inscripción y
    su AccesoExternoInscripcion vigente (RF-31):
    1. Inscripción activa perteneciente al evento evaluado.
    2. Participante sin cuenta institucional (usuario_id IS NULL).
    3. AccesoExternoInscripcion válido, vigente y no revocado para esa inscripción.
    4. Registro de entrada válido (Asistencia REGISTRADA con hora_entrada).
    5. Registro de salida válido (hora_salida confirmada).
    """
    if not inscripcion or inscripcion.estado != EstadoInscripcion.ACTIVA:
        return {
            'elegible': False,
            'codigo': 'SIN_INSCRIPCION_VALIDA',
            'mensaje': 'No cuentas con una inscripción válida y activa en este evento para calificarlo.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    if evento is not None and inscripcion.evento_id != evento.pk:
        return {
            'elegible': False,
            'codigo': 'EVENTO_DISTINTO',
            'mensaje': 'Tu inscripción activa no corresponde al evento que intentas calificar.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    participante = getattr(inscripcion, 'participante', None)
    if not participante or participante.usuario_id is not None:
        return {
            'elegible': False,
            'codigo': 'CUENTA_INSTITUCIONAL',
            'mensaje': 'Esta inscripción pertenece a una cuenta institucional. Inicia sesión para calificar el evento.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    acceso_eval = acceso_externo
    if acceso_eval is None:
        acceso_eval = AccesoExternoInscripcion.objects.filter(inscripcion=inscripcion).first()

    if not acceso_eval or acceso_eval.inscripcion_id != inscripcion.pk:
        return {
            'elegible': False,
            'codigo': 'ACCESO_EXTERNO_INVALIDO',
            'mensaje': 'No se encontró un acceso externo válido para esta inscripción.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    if acceso_eval.revocado:
        return {
            'elegible': False,
            'codigo': 'ACCESO_EXTERNO_REVOCADO',
            'mensaje': 'El acceso a esta inscripción fue revocado y no puede utilizarse para calificar el evento.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    if not acceso_eval.es_valido:
        return {
            'elegible': False,
            'codigo': 'ACCESO_EXTERNO_EXPIRADO',
            'mensaje': 'Tu acceso externo ha expirado. Recupera nuevamente tu inscripción en el evento para calificar.',
            'inscripcion': inscripcion,
            'asistencia': None,
            'calificacion_existente': None,
        }

    asistencia = Asistencia.objects.filter(inscripcion=inscripcion).first()
    if not asistencia or asistencia.estado != EstadoAsistencia.REGISTRADA or not asistencia.hora_entrada:
        return {
            'elegible': False,
            'codigo': 'SIN_ENTRADA_REGISTRADA',
            'mensaje': 'Debes contar con un registro de entrada confirmado en este evento antes de calificarlo.',
            'inscripcion': inscripcion,
            'asistencia': asistencia,
            'calificacion_existente': None,
        }

    if not asistencia.hora_salida:
        return {
            'elegible': False,
            'codigo': 'SIN_SALIDA_REGISTRADA',
            'mensaje': 'Debes registrar tu salida mediante el código QR del evento antes de enviar tu calificación.',
            'inscripcion': inscripcion,
            'asistencia': asistencia,
            'calificacion_existente': None,
        }

    calificacion_existente = CalificacionEvento.objects.filter(
        inscripcion=inscripcion,
    ).first()

    return {
        'elegible': True,
        'codigo': 'ELEGIBLE_ACTUALIZACION' if calificacion_existente else 'ELEGIBLE_NUEVA',
        'mensaje': 'Elegible para calificar el evento.',
        'inscripcion': inscripcion,
        'asistencia': asistencia,
        'calificacion_existente': calificacion_existente,
    }


def obtener_evaluacion_pendiente_externa(acceso_externo):
    """
    Retorna la Inscripcion asociada a un AccesoExternoInscripcion válido si cumple
    entrada + salida confirmadas y todavía no registra CalificacionEvento (RF-31).
    En cualquier otro caso (sin acceso, revocado, expirado, sin salida o ya calificado)
    retorna None.
    """
    if not acceso_externo or acceso_externo.revocado or not acceso_externo.es_valido:
        return None
    inscripcion = getattr(acceso_externo, 'inscripcion', None)
    if not inscripcion:
        return None
    eleg = verificar_elegibilidad_calificacion_externa(
        inscripcion,
        acceso_externo=acceso_externo,
    )
    if eleg['elegible'] and eleg['calificacion_existente'] is None:
        return inscripcion
    return None


def obtener_evaluaciones_pendientes(user):
    """
    Retorna el QuerySet de inscripciones del estudiante que cumplen:
    - Inscripción ACTIVA
    - Asistencia REGISTRADA con hora_entrada y hora_salida confirmadas
    - Sin CalificacionEvento registrada por el estudiante para ese evento

    Ordenadas desde la salida más reciente hacia atrás.
    """
    if not es_estudiante_elegible_rol(user):
        return Inscripcion.objects.none()

    calificacion_subquery = CalificacionEvento.objects.filter(
        Q(evento_id=OuterRef('evento_id'), estudiante=user) | Q(inscripcion_id=OuterRef('pk'))
    )

    return (
        Inscripcion.objects
        .filter(
            participante__usuario=user,
            estado=EstadoInscripcion.ACTIVA,
            asistencia__estado=EstadoAsistencia.REGISTRADA,
            asistencia__hora_entrada__isnull=False,
            asistencia__hora_salida__isnull=False,
        )
        .annotate(tiene_calificacion=Exists(calificacion_subquery))
        .filter(tiene_calificacion=False)
        .select_related('evento', 'evento__categoria', 'asistencia')
        .order_by('-asistencia__fecha', '-asistencia__hora_salida', '-asistencia__fecha_registro')
    )


def obtener_primera_evaluacion_pendiente(user):
    """
    Retorna la inscripción con evaluación obligatoria pendiente más prioritaria
    para el estudiante autenticado, o None si no tiene evaluaciones pendientes.
    """
    return obtener_evaluaciones_pendientes(user).first()


def validar_puntuacion_estrellas(puntuacion_raw):
    """
    Valida estrictamente en backend que la puntuación sea un entero explícito entre 1 y 5.
    No asigna valores por defecto ni acepta valores nulos, decimales o fuera de rango.
    Retorna (valida: bool, valor_int | None, mensaje_error | None).
    """
    if puntuacion_raw is None or isinstance(puntuacion_raw, bool):
        return False, None, 'Debes seleccionar obligatoriamente una puntuación de 1 a 5 estrellas.'

    if isinstance(puntuacion_raw, str):
        limpio = puntuacion_raw.strip()
        if not limpio:
            return False, None, 'Debes seleccionar obligatoriamente una puntuación de 1 a 5 estrellas.'
        if not limpio.lstrip('-').isdigit():
            return False, None, 'La calificación debe ser un número entero entre 1 y 5 estrellas.'
        valor = int(limpio)
    elif isinstance(puntuacion_raw, int):
        valor = puntuacion_raw
    else:
        return False, None, 'La calificación debe ser un número entero entre 1 y 5 estrellas.'

    if valor < 1 or valor > 5:
        return False, None, 'La puntuación permitida debe estar entre 1 y 5 estrellas.'

    return True, valor, None


def registrar_o_actualizar_calificacion(user, evento, puntuacion_raw, ip=None):
    """
    Registra o actualiza la calificación única del estudiante para un evento (RF-24, RF-27, RF-28).

    Opera en su propia transacción atómica, completamente independiente del registro de asistencia
    y salida: un error en este proceso jamás altera ni revierte la salida previamente persistida.
    """
    elegibilidad = verificar_elegibilidad_calificacion(user, evento)
    if not elegibilidad['elegible']:
        return {
            'exito': False,
            'codigo': elegibilidad['codigo'],
            'mensaje': elegibilidad['mensaje'],
            'calificacion': None,
            'creada': False,
            'actualizada': False,
            'status_http': 403,
        }

    valida, puntuacion, err_msg = validar_puntuacion_estrellas(puntuacion_raw)
    if not valida:
        return {
            'exito': False,
            'codigo': 'PUNTUACION_INVALIDA',
            'mensaje': err_msg,
            'calificacion': elegibilidad['calificacion_existente'],
            'creada': False,
            'actualizada': False,
            'status_http': 400,
        }

    inscripcion = elegibilidad['inscripcion']

    with transaction.atomic():
        if inscripcion is not None:
            Inscripcion.objects.select_for_update().filter(pk=inscripcion.pk).first()

        existente = (
            CalificacionEvento.objects
            .select_for_update()
            .filter(Q(evento=evento, estudiante=user) | Q(inscripcion=inscripcion))
            .first()
        )

        if existente:
            existente.puntuacion = puntuacion
            update_fields = ['puntuacion', 'fecha_actualizacion']
            if existente.estudiante_id is None:
                existente.estudiante = user
                update_fields.append('estudiante')
            if inscripcion is not None and existente.inscripcion_id is None:
                existente.inscripcion = inscripcion
                update_fields.append('inscripcion')
            existente.full_clean()
            existente.save(update_fields=update_fields)
            calificacion = existente
            creada = False
            actualizada = True
            accion_audit = 'ACTUALIZAR_CALIFICACION_EVENTO'
        else:
            try:
                with transaction.atomic():
                    calificacion = CalificacionEvento(
                        evento=evento,
                        estudiante=user,
                        inscripcion=inscripcion,
                        puntuacion=puntuacion,
                    )
                    calificacion.full_clean()
                    calificacion.save()
                creada = True
                actualizada = False
                accion_audit = 'CREAR_CALIFICACION_EVENTO'
            except IntegrityError:
                # Protección frente a doble envío simultáneo: actualizar el registro único
                existente_conc = (
                    CalificacionEvento.objects
                    .select_for_update()
                    .filter(Q(evento=evento, estudiante=user) | Q(inscripcion=inscripcion))
                    .first()
                )
                existente_conc.puntuacion = puntuacion
                update_fields = ['puntuacion', 'fecha_actualizacion']
                if existente_conc.estudiante_id is None:
                    existente_conc.estudiante = user
                    update_fields.append('estudiante')
                if inscripcion is not None and existente_conc.inscripcion_id is None:
                    existente_conc.inscripcion = inscripcion
                    update_fields.append('inscripcion')
                existente_conc.full_clean()
                existente_conc.save(update_fields=update_fields)
                calificacion = existente_conc
                creada = False
                actualizada = True
                accion_audit = 'ACTUALIZAR_CALIFICACION_EVENTO'

        Auditoria.objects.create(
            usuario=user,
            accion=accion_audit,
            modulo='EVENTOS',
            registro_afectado=f"Calificacion ID {calificacion.pk} - Evento {evento.pk} ({puntuacion}/5)"[:100],
            ip=ip,
        )

    return {
        'exito': True,
        'codigo': 'CALIFICACION_ACTUALIZADA' if actualizada else 'CALIFICACION_REGISTRADA',
        'mensaje': '¡Gracias por tu opinión! Tu calificación ha sido registrada correctamente.',
        'calificacion': calificacion,
        'creada': creada,
        'actualizada': actualizada,
        'status_http': 200,
    }


def registrar_o_actualizar_calificacion_externa(inscripcion, acceso_externo, evento, puntuacion_raw, ip=None):
    """
    Registra o actualiza la calificación única de un participante externo sin cuenta
    institucional mediante su inscripción y su AccesoExternoInscripcion vigente (RF-31).

    Opera en su propia transacción atómica con bloqueo select_for_update sobre el acceso
    externo y la inscripción para evitar duplicados por doble clic o concurrencia y
    garantizar que un acceso revocado concurrentemente sea rechazado.
    """
    elegibilidad = verificar_elegibilidad_calificacion_externa(
        inscripcion,
        evento=evento,
        acceso_externo=acceso_externo,
    )
    if not elegibilidad['elegible']:
        return {
            'exito': False,
            'codigo': elegibilidad['codigo'],
            'mensaje': elegibilidad['mensaje'],
            'calificacion': None,
            'creada': False,
            'actualizada': False,
            'status_http': 403,
        }

    valida, puntuacion, err_msg = validar_puntuacion_estrellas(puntuacion_raw)
    if not valida:
        return {
            'exito': False,
            'codigo': 'PUNTUACION_INVALIDA',
            'mensaje': err_msg,
            'calificacion': elegibilidad['calificacion_existente'],
            'creada': False,
            'actualizada': False,
            'status_http': 400,
        }

    with transaction.atomic():
        inscripcion_lock = (
            Inscripcion.objects
            .select_for_update()
            .select_related('participante')
            .filter(pk=inscripcion.pk, evento=evento, estado=EstadoInscripcion.ACTIVA)
            .first()
        )
        acceso_lock = (
            AccesoExternoInscripcion.objects
            .select_for_update()
            .filter(pk=acceso_externo.pk, inscripcion_id=inscripcion.pk)
            .first()
        )
        if (
            not inscripcion_lock
            or inscripcion_lock.participante.usuario_id is not None
            or not acceso_lock
            or acceso_lock.revocado
            or not acceso_lock.es_valido
        ):
            return {
                'exito': False,
                'codigo': 'ACCESO_EXTERNO_REVOCADO' if (acceso_lock and acceso_lock.revocado) else 'ACCESO_EXTERNO_INVALIDO',
                'mensaje': 'Tu acceso externo ya no es válido para registrar o actualizar la calificación.',
                'calificacion': None,
                'creada': False,
                'actualizada': False,
                'status_http': 403,
            }

        existente = (
            CalificacionEvento.objects
            .select_for_update()
            .filter(inscripcion=inscripcion_lock)
            .first()
        )

        if existente:
            existente.puntuacion = puntuacion
            existente.full_clean()
            existente.save(update_fields=['puntuacion', 'fecha_actualizacion'])
            calificacion = existente
            creada = False
            actualizada = True
            accion_audit = 'ACTUALIZAR_CALIFICACION_EVENTO'
        else:
            try:
                with transaction.atomic():
                    calificacion = CalificacionEvento(
                        evento=evento,
                        estudiante=None,
                        inscripcion=inscripcion_lock,
                        puntuacion=puntuacion,
                    )
                    calificacion.full_clean()
                    calificacion.save()
                creada = True
                actualizada = False
                accion_audit = 'CREAR_CALIFICACION_EVENTO'
            except IntegrityError:
                existente_conc = (
                    CalificacionEvento.objects
                    .select_for_update()
                    .get(inscripcion=inscripcion_lock)
                )
                existente_conc.puntuacion = puntuacion
                existente_conc.full_clean()
                existente_conc.save(update_fields=['puntuacion', 'fecha_actualizacion'])
                calificacion = existente_conc
                creada = False
                actualizada = True
                accion_audit = 'ACTUALIZAR_CALIFICACION_EVENTO'

        Auditoria.objects.create(
            usuario=None,
            accion=accion_audit,
            modulo='EVENTOS',
            registro_afectado=f"Calificacion ID {calificacion.pk} - Insc {inscripcion_lock.pk} - Evento {evento.pk} ({puntuacion}/5)"[:100],
            ip=ip,
        )

    return {
        'exito': True,
        'codigo': 'CALIFICACION_ACTUALIZADA' if actualizada else 'CALIFICACION_REGISTRADA',
        'mensaje': '¡Gracias por tu opinión! Tu calificación ha sido registrada correctamente.',
        'calificacion': calificacion,
        'creada': creada,
        'actualizada': actualizada,
        'status_http': 200,
    }


def _construir_diccionario_estadisticas(qs):
    """
    Calcula dinámicamente a partir de un QuerySet de CalificacionEvento:
    - Promedio real
    - Total de evaluaciones
    - Conteo exacto para 1, 2, 3, 4 y 5 estrellas
    - Distribución porcentual por estrella
    """
    agg = qs.aggregate(
        total=Count('id_calificacion'),
        promedio=Avg('puntuacion'),
        estrellas_1=Count('id_calificacion', filter=Q(puntuacion=1)),
        estrellas_2=Count('id_calificacion', filter=Q(puntuacion=2)),
        estrellas_3=Count('id_calificacion', filter=Q(puntuacion=3)),
        estrellas_4=Count('id_calificacion', filter=Q(puntuacion=4)),
        estrellas_5=Count('id_calificacion', filter=Q(puntuacion=5)),
    )

    total = agg['total'] or 0
    promedio = round(float(agg['promedio']), 2) if (total > 0 and agg['promedio'] is not None) else 0.0
    promedio_display = f"{promedio:.1f}" if total > 0 else "0.0"

    conteos = {
        1: agg['estrellas_1'] or 0,
        2: agg['estrellas_2'] or 0,
        3: agg['estrellas_3'] or 0,
        4: agg['estrellas_4'] or 0,
        5: agg['estrellas_5'] or 0,
    }

    porcentajes = {}
    for estrella in range(1, 6):
        porcentajes[estrella] = round((conteos[estrella] / total) * 100.0, 1) if total > 0 else 0.0

    distribucion = [
        {
            'estrellas': estrella,
            'etiqueta': ETIQUETAS_ESTRELLAS[estrella],
            'cantidad': conteos[estrella],
            'porcentaje': porcentajes[estrella],
            'porcentaje_css': f"{porcentajes[estrella]:.1f}",
        }
        for estrella in range(5, 0, -1)
    ]

    return {
        'tiene_calificaciones': total > 0,
        'total_calificaciones': total,
        'promedio': promedio,
        'promedio_display': promedio_display,
        'estrellas_llenas': int(round(promedio)) if total > 0 else 0,
        'conteos': conteos,
        'porcentajes': porcentajes,
        'distribucion': distribucion,
        'mensaje_vacio': MENSAJE_SIN_CALIFICACIONES,
    }


def calcular_estadisticas_calificacion(evento):
    """
    Calcula en tiempo real las estadísticas de calificación de un evento específico (RF-30).
    """
    qs = CalificacionEvento.objects.filter(evento=evento)
    return _construir_diccionario_estadisticas(qs)


def calcular_estadisticas_calificacion_global(eventos_qs):
    """
    Calcula en tiempo real las estadísticas consolidadas de calificación para un conjunto
    de eventos filtrado en el dashboard analítico (RF-30).
    """
    qs = CalificacionEvento.objects.filter(evento__in=eventos_qs)
    return _construir_diccionario_estadisticas(qs)
