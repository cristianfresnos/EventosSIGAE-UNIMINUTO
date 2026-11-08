from django import forms
from django.core.exceptions import ValidationError
from .models import Evento, CategoriaEvento, ModalidadEvento, ModalidadInscripcion, EstadoEvento


class EventoForm(forms.ModelForm):
    """
    Formulario para creación y edición de eventos institucionales en SIGAE.
    """
    class Meta:
        model = Evento
        fields = [
            'nombre',
            'descripcion',
            'categoria',
            'fecha',
            'hora_inicio',
            'hora_fin',
            'lugar',
            'modalidad',
            'modalidad_inscripcion',
            'cupo',
            'estado',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Conferencia de Inteligencia Artificial',
                'required': True,
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe los objetivos, temáticas y ponentes del evento...',
                'required': True,
            }),
            'categoria': forms.Select(attrs={
                'class': 'form-control select-control',
                'required': True,
            }),
            'fecha': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'hora_inicio': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'required': True,
            }),
            'hora_fin': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time',
                'required': True,
            }),
            'lugar': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Auditorio Principal o Enlace Teams/Meet',
                'required': True,
            }),
            'modalidad': forms.Select(attrs={
                'class': 'form-control select-control',
                'required': True,
            }),
            'modalidad_inscripcion': forms.Select(attrs={
                'class': 'form-control select-control',
            }),
            'cupo': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Dejar vacío para cupo ilimitado',
            }),
            'estado': forms.Select(attrs={
                'class': 'form-control select-control',
                'required': True,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'modalidad_inscripcion' in self.fields:
            self.fields['modalidad_inscripcion'].required = False
            if not self.initial.get('modalidad_inscripcion'):
                self.initial['modalidad_inscripcion'] = (
                    self.instance.modalidad_inscripcion if (self.instance and self.instance.pk) else ModalidadInscripcion.SOLO_INVITACION
                )

    def clean_modalidad_inscripcion(self):
        val = self.cleaned_data.get('modalidad_inscripcion')
        return val or ModalidadInscripcion.SOLO_INVITACION

    def clean(self):
        cleaned_data = super().clean()
        hora_inicio = cleaned_data.get('hora_inicio')
        hora_fin = cleaned_data.get('hora_fin')

        if hora_inicio and hora_fin:
            if hora_fin <= hora_inicio:
                self.add_error('hora_fin', 'La hora de fin debe ser posterior a la hora de inicio.')

        return cleaned_data
