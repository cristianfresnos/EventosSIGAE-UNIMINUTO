from django import forms
from eventos.models import Evento, CategoriaEvento, ModalidadEvento, EstadoEvento


class FiltroDashboardForm(forms.Form):
    """
    Formulario para el filtrado multidimensional de indicadores en el dashboard analítico.
    Permite filtrar por rango de fechas, evento individual, categoría, modalidad y estado.
    """
    fecha_desde = forms.DateField(
        required=False,
        label="Fecha desde",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'AAAA-MM-DD'
        })
    )
    fecha_hasta = forms.DateField(
        required=False,
        label="Fecha hasta",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'AAAA-MM-DD'
        })
    )
    evento = forms.ModelChoiceField(
        queryset=Evento.objects.none(),
        required=False,
        empty_label="— Todos los eventos permitidos —",
        label="Evento",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    categoria = forms.ModelChoiceField(
        queryset=CategoriaEvento.objects.filter(activo=True),
        required=False,
        empty_label="— Todas las categorías —",
        label="Categoría",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    modalidad = forms.ChoiceField(
        choices=[('', '— Todas las modalidades —')] + list(ModalidadEvento.choices),
        required=False,
        label="Modalidad",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    estado = forms.ChoiceField(
        choices=[('', '— Todos los estados —')] + list(EstadoEvento.choices),
        required=False,
        label="Estado del evento",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, eventos_permitidos=None, **kwargs):
        super().__init__(*args, **kwargs)
        if eventos_permitidos is not None:
            self.fields['evento'].queryset = eventos_permitidos
