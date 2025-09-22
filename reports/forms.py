from django import forms
from activos.models import Activo


class AssetReportForm(forms.Form):
    REPORT_CHOICES = [
        ("TECH", "Ficha técnica"),
        ("CYCLE", "Historial de ciclos"),
        ("FAIL", "Historial de fallos"),
        ("TRACE", "Trazabilidad"),
    ]

    asset = forms.ModelChoiceField(
        queryset=Activo.objects.all(),
        required=False,
        label="Activo",
        empty_label="Todos",
    )
    report_type = forms.ChoiceField(choices=REPORT_CHOICES, label="Tipo de informe")
    start_date = forms.DateField(required=False, label="Desde")
    end_date = forms.DateField(required=False, label="Hasta")