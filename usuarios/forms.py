from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Usuario, Rol


class LoginForm(AuthenticationForm):
    """
    Formulario de autenticación con estilos institucionales UNIMINUTO.
    """
    username = forms.CharField(
        label='Nombre de usuario',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej. usuario.sigae',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
        })
    )


class PerfilUsuarioForm(forms.ModelForm):
    """
    Formulario para actualización de datos de contacto de usuario.
    """
    class Meta:
        model = Usuario
        fields = ['nombres', 'apellidos', 'email', 'telefono']
        widgets = {
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 3001234567'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
            if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("Ya existe un usuario registrado con este correo electrónico.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if 'email' in self.changed_data:
            user.email_verificado = False
        if commit:
            user.save()
        return user


class RegistroUsuarioForm(forms.ModelForm):
    """
    Formulario de registro institucional para nuevos usuarios / invitados.
    Garantiza unicidad de documento, username, correo y validación de contraseñas seguras.
    """
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
            'required': True,
        }),
        help_text='Mínimo 8 caracteres alfanuméricos.'
    )
    confirm_password = forms.CharField(
        label='Confirmar Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••',
            'required': True,
        })
    )

    class Meta:
        model = Usuario
        fields = [
            'username',
            'documento',
            'nombres',
            'apellidos',
            'email',
            'telefono',
        ]
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. nombre.apellido',
                'required': True,
            }),
            'documento': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 1020304050',
                'required': True,
            }),
            'nombres': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombres completos',
                'required': True,
            }),
            'apellidos': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Apellidos completos',
                'required': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo@ejemplo.com',
                'required': True,
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 3101234567',
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
            if Usuario.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError("Ya existe un usuario registrado con este correo electrónico.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            username = username.strip().lower()
            if Usuario.objects.filter(username__iexact=username).exists():
                raise forms.ValidationError("Este nombre de usuario ya se encuentra en uso.")
        return username

    def clean_documento(self):
        documento = self.cleaned_data.get('documento')
        if documento:
            documento = documento.strip()
            if Usuario.objects.filter(documento=documento).exists():
                raise forms.ValidationError("Ya existe un usuario registrado con este documento de identidad.")
        return documento

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')

        if p1 and p2:
            if p1 != p2:
                self.add_error('confirm_password', 'Las contraseñas no coinciden.')
            else:
                user_temp = Usuario(
                    username=cleaned_data.get('username', ''),
                    email=cleaned_data.get('email', ''),
                    nombres=cleaned_data.get('nombres', ''),
                    apellidos=cleaned_data.get('apellidos', '')
                )
                try:
                    validate_password(p1, user=user_temp)
                except ValidationError as e:
                    self.add_error('password', e)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if not getattr(user, 'rol_id', None):
            rol_default = Rol.objects.filter(nombre='Estudiante').first() or Rol.objects.first()
            user.rol = rol_default
        user.is_active = True
        user.email_verificado = False
        if commit:
            user.save()
        return user
