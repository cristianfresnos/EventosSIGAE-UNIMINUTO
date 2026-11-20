from django import forms
from .models import Participante, TipoParticipante, InvitacionEvento


class InscripcionExternaForm(forms.ModelForm):
    """
    Formulario de registro e inscripción pública para participantes externos (sin cuenta institucional).
    Incorpora consentimiento expreso e informado de tratamiento de datos personales (RNF-14 / Etapa 7.2.2).
    """
    acepta_politica_tratamiento = forms.BooleanField(
        required=True,
        label='Acepto la política de tratamiento de datos personales de UNIMINUTO',
        error_messages={
            'required': 'Debes autorizar el tratamiento de datos personales conforme a la política institucional para completar tu inscripción.'
        },
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'acepta_politica_tratamiento',
            'required': True,
        })
    )

    class Meta:
        model = Participante
        fields = [
            'documento',
            'nombres',
            'apellidos',
            'correo',
            'telefono',
            'institucion',
        ]
        widgets = {
            'documento': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 10203040',
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
            'correo': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo.personal@ejemplo.com',
                'required': True,
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 3101234567 (opcional)',
            }),
            'institucion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Empresa, universidad o entidad de procedencia (opcional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['telefono'].required = False
        self.fields['institucion'].required = False

    def clean_documento(self):
        doc = self.cleaned_data.get('documento')
        return doc.strip() if doc else ''

    def clean_correo(self):
        correo = self.cleaned_data.get('correo')
        return correo.strip().lower() if correo else ''

    def clean_nombres(self):
        nombres = self.cleaned_data.get('nombres')
        return nombres.strip() if nombres else ''

    def clean_apellidos(self):
        apellidos = self.cleaned_data.get('apellidos')
        return apellidos.strip() if apellidos else ''

    def clean_telefono(self):
        tel = self.cleaned_data.get('telefono')
        return tel.strip() if tel else ''

    def clean_institucion(self):
        inst = self.cleaned_data.get('institucion')
        return inst.strip() if inst else ''


# Alias institucional para consistencia terminológica
InscripcionPublicaForm = InscripcionExternaForm


class ConsultaInscripcionPublicaForm(forms.Form):
    """
    Formulario público de consulta y recuperación de inscripción existente para un evento.
    Solicita número de documento y un segundo dato de verificación ya registrado en el
    formulario de inscripción (correo electrónico o teléfono) sin requerir inicio de sesión.
    """
    documento = forms.CharField(
        max_length=20,
        required=True,
        label='Número de documento',
        error_messages={
            'required': 'Ingresa tu número de documento para consultar tu inscripción.',
        },
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'consulta_documento',
            'placeholder': 'Ej. 10203040',
            'autocomplete': 'off',
            'required': True,
        })
    )
    dato_verificacion = forms.CharField(
        max_length=254,
        required=True,
        label='Correo electrónico o teléfono registrado',
        error_messages={
            'required': 'Ingresa el correo electrónico o el teléfono con el que te inscribiste.',
        },
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'consulta_dato_verificacion',
            'placeholder': 'Ej. correo@ejemplo.com o 3101234567',
            'autocomplete': 'off',
            'required': True,
        })
    )

    def clean_documento(self):
        doc = self.cleaned_data.get('documento', '')
        return doc.strip()

    def clean_dato_verificacion(self):
        val = self.cleaned_data.get('dato_verificacion', '')
        return val.strip()


class InvitacionEventoForm(forms.ModelForm):
    """
    Formulario para el envío de invitaciones individuales a eventos institucionales (RF-01).
    Permite a los profesores y organizadores registrar datos del invitado.
    """
    class Meta:
        model = InvitacionEvento
        fields = [
            'correo',
            'nombres',
            'apellidos',
            'institucion',
        ]
        widgets = {
            'correo': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'correo.invitado@ejemplo.com',
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
            'institucion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Empresa o institución de procedencia (opcional)',
            }),
        }

    def clean_correo(self):
        correo = self.cleaned_data.get('correo')
        if correo:
            return correo.strip().lower()
        return correo

    def clean_nombres(self):
        nombres = self.cleaned_data.get('nombres')
        return nombres.strip() if nombres else ''

    def clean_apellidos(self):
        apellidos = self.cleaned_data.get('apellidos')
        return apellidos.strip() if apellidos else ''
