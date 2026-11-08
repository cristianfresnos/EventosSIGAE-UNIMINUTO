from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from auditoria.models import Auditoria
from .forms import LoginForm, RegistroUsuarioForm
from .models import TokenVerificacionCorreo
from .services import enviar_correo_verificacion


def get_client_ip(request):
    """Obtiene la IP del cliente considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def login_view(request):
    """
    Vista de autenticación institucional del portal web.
    """
    if request.user.is_authenticated:
        return redirect('inicio')

    next_url = request.GET.get('next') or request.POST.get('next') or 'inicio'

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Registro de auditoría
            Auditoria.objects.create(
                usuario=user,
                accion='INICIAR_SESION',
                modulo='USUARIOS',
                registro_afectado=f"Usuario ID {user.pk} - {user.username}",
                ip=get_client_ip(request)
            )

            messages.success(request, f"¡Bienvenido(a), {user.get_full_name() or user.username}!")
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('inicio')
        else:
            messages.error(request, "Nombre de usuario o contraseña incorrectos. Por favor verifique sus credenciales.")
    else:
        form = LoginForm(request)

    response = render(request, 'usuarios/login.html', {
        'form': form,
        'next': next_url,
    })
    response['Referrer-Policy'] = 'same-origin'
    return response


def registro_view(request):
    """
    Vista de registro institucional para nuevos usuarios y personas invitadas a eventos.
    """
    if request.user.is_authenticated:
        return redirect('inicio')

    next_url = request.GET.get('next') or request.POST.get('next') or 'inicio'

    initial_data = {}
    inv_id = request.session.get('invitacion_id')
    token_hash = request.session.get('invitacion_token_hash')
    if inv_id and token_hash:
        from participantes.models import InvitacionEvento, EstadoInvitacion
        inv = InvitacionEvento.objects.filter(pk=inv_id, token_hash=token_hash, estado=EstadoInvitacion.PENDIENTE).first()
        if inv and not inv.ha_expirado:
            initial_data['email'] = inv.correo
            initial_data['nombres'] = inv.nombres
            initial_data['apellidos'] = inv.apellidos

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)

            # Generar y enviar correo de verificación institucional
            _, raw_tok_verif = TokenVerificacionCorreo.crear_para_usuario(user)
            enviar_correo_verificacion(user, raw_tok_verif, request)

            Auditoria.objects.create(
                usuario=user,
                accion='REGISTRO_USUARIO',
                modulo='USUARIOS',
                registro_afectado=f"Usuario ID {user.pk} - {user.username} ({user.email})",
                ip=get_client_ip(request)
            )

            messages.success(
                request,
                f"¡Bienvenido(a), {user.get_full_name()}! Hemos enviado un correo a {user.email} para verificar tu dirección institucional."
            )
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('inicio')
        else:
            messages.error(request, "Por favor corrige los errores señalados en el formulario de registro.")
    else:
        form = RegistroUsuarioForm(initial=initial_data)

    response = render(request, 'usuarios/registro.html', {
        'form': form,
        'next': next_url,
    })
    response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
def solicitar_verificacion_email_view(request):
    """
    Permite al usuario autenticado solicitar el envío de un nuevo enlace de verificación de correo.
    """
    if request.user.email_verificado:
        messages.info(request, "Tu correo institucional ya se encuentra verificado.")
        if request.session.get('invitacion_id'):
            return redirect('participantes:ver_invitacion')
        return redirect('inicio')

    _, raw_token = TokenVerificacionCorreo.crear_para_usuario(request.user)
    enviado = enviar_correo_verificacion(request.user, raw_token, request)

    Auditoria.objects.create(
        usuario=request.user,
        accion='SOLICITAR_VERIFICACION_EMAIL',
        modulo='USUARIOS',
        registro_afectado=f"Usuario ID {request.user.pk} - {request.user.email}",
        ip=get_client_ip(request)
    )

    if enviado:
        messages.success(request, f"Hemos enviado un nuevo enlace de verificación a {request.user.email}. Por favor revisa tu bandeja de entrada.")
    else:
        messages.warning(request, "No fue posible entregar el correo de verificación en este momento. Intenta nuevamente más tarde.")

    if request.session.get('invitacion_id'):
        return redirect('participantes:ver_invitacion')
    return redirect('inicio')


def verificar_correo_view(request, token):
    """
    Valida el token de verificación de correo de un solo uso.
    """
    exito, user, msg = TokenVerificacionCorreo.verificar_token(token)
    if exito and user:
        Auditoria.objects.create(
            usuario=user,
            accion='VERIFICAR_EMAIL',
            modulo='USUARIOS',
            registro_afectado=f"Usuario ID {user.pk} - {user.email}",
            ip=get_client_ip(request)
        )
        messages.success(request, msg)
        if request.session.get('invitacion_id'):
            return redirect('participantes:ver_invitacion')
        return redirect('inicio')
    else:
        messages.error(request, msg)
        return redirect('inicio')


def logout_view(request):
    """
    Cierra la sesión del usuario actual y registra la auditoría.
    """
    if request.user.is_authenticated:
        user = request.user
        Auditoria.objects.create(
            usuario=user,
            accion='CERRAR_SESION',
            modulo='USUARIOS',
            registro_afectado=f"Usuario ID {user.pk} - {user.username}",
            ip=get_client_ip(request)
        )
        logout(request)
        messages.info(request, "Has cerrado sesión correctamente. ¡Hasta pronto!")
    return redirect('inicio')


from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


class CustomPasswordResetView(auth_views.PasswordResetView):
    """
    Solicitud de restablecimiento de contraseña mediante correo institucional (RF-02).
    Genera tokens criptográficos de un solo uso y audita la solicitud sin filtrar existencia de cuentas.
    """
    template_name = 'usuarios/password_reset_form.html'
    email_template_name = 'usuarios/password_reset_email.html'
    subject_template_name = 'usuarios/password_reset_subject.txt'
    success_url = reverse_lazy('usuarios:password_reset_done')

    def form_valid(self, form):
        email = form.cleaned_data.get('email')
        Auditoria.objects.create(
            usuario=None,
            accion='SOLICITAR_RECUPERACION_PASSWORD',
            modulo='USUARIOS',
            registro_afectado=f"Solicitud de token enviada para ({email})",
            ip=get_client_ip(self.request)
        )
        return super().form_valid(form)


class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    Confirmación y cambio seguro de contraseña mediante token validado.
    Audita el cambio de clave exitoso.
    """
    template_name = 'usuarios/password_reset_confirm.html'
    success_url = reverse_lazy('usuarios:password_reset_complete')

    def form_valid(self, form):
        user = form.user
        Auditoria.objects.create(
            usuario=user,
            accion='CAMBIO_PASSWORD_RECUPERACION',
            modulo='USUARIOS',
            registro_afectado=f"Contraseña actualizada exitosamente vía token para {user.username}",
            ip=get_client_ip(self.request)
        )
        return super().form_valid(form)

