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
