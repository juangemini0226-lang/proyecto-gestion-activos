from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import (
    Activo,
    TareaMantenimiento,
    PlantillaChecklist,
    RegistroMantenimiento,
    EvidenciaDetalle,
    CatalogoFalla,
    EstadoOT,
)

User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
# Formularios de Activos
# ──────────────────────────────────────────────────────────────────────────────


class ActivoForm(forms.ModelForm):
    class Meta:
        model = Activo
        fields = [
            "codigo",
            "numero_activo",
            "nombre",
            "peso",
            "familia",
            "categoria",
            "estado",
            "ubicacion",
        ]

# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────
def _operarios_queryset():
    """
    Devuelve el queryset de usuarios del grupo 'Operarios'.
    Si el grupo no existe o está vacío, hace fallback a usuarios activos.
    """
    qs = User.objects.all()
    try:
        qs_grp = User.objects.filter(groups__name="Operarios")
        if qs_grp.exists():
            return qs_grp.order_by("username", "first_name", "last_name")
    except Exception:
        pass
    return qs.filter(is_active=True).order_by("username", "first_name", "last_name")

# ──────────────────────────────────────────────────────────────────────────────
# Carga de Excel (odómetro)
# ──────────────────────────────────────────────────────────────────────────────
class ExcelUploadForm(forms.Form):
    semana = forms.ChoiceField(label="Selecciona la Semana del Informe")
    archivo_excel = forms.FileField(label="Selecciona el archivo Excel de Odómetro")

    def __init__(self, *args, **kwargs):
        semanas_usadas = kwargs.pop("semanas_usadas", [])
        super().__init__(*args, **kwargs)

        opciones_semana = [(i, f"Semana {i}") for i in range(1, 53)]
        opciones_disponibles = [op for op in opciones_semana if op[0] not in semanas_usadas]
        self.fields["semana"].choices = opciones_disponibles

# ──────────────────────────────────────────────────────────────────────────────
# Añadir tarea rápida al checklist
# ──────────────────────────────────────────────────────────────────────────────
class AddTareaRapidaForm(forms.Form):
    tarea_existente = forms.ModelChoiceField(
        queryset=TareaMantenimiento.objects.all().order_by("nombre"),
        required=False,
        label="Tarea existente",
    )
    nueva_tarea = forms.CharField(
        required=False,
        label="Nueva tarea",
        help_text="Si no está en la lista, escribe el nombre y se creará.",
    )

    def clean(self):
        data = super().clean()
        if not data.get("tarea_existente") and not (data.get("nueva_tarea") or "").strip():
            raise forms.ValidationError("Selecciona una tarea o escribe una nueva.")
        return data

# ──────────────────────────────────────────────────────────────────────────────
# Cargar una plantilla a una OT
# ──────────────────────────────────────────────────────────────────────────────
class CargarPlantillaForm(forms.Form):
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaChecklist.objects.none(),
        label="Plantilla",
    )

    def __init__(self, *args, **kwargs):
        activo = kwargs.pop("activo", None)
        tipo = kwargs.pop("tipo", None)
        falla = kwargs.pop("falla", None)
        super().__init__(*args, **kwargs)

        qs = PlantillaChecklist.objects.all()

        if hasattr(PlantillaChecklist, "vigente"):
            qs = qs.filter(vigente=True)

        if tipo and hasattr(PlantillaChecklist, "tipo"):
            qs = qs.filter(tipo=tipo)

        if falla is not None and hasattr(PlantillaChecklist, "falla"):
            qs = qs.filter(Q(falla=falla) | Q(falla__isnull=True))

        if activo:
            ambito_q = Q()
            if hasattr(PlantillaChecklist, "es_global"):
                ambito_q |= Q(es_global=True)
            if hasattr(PlantillaChecklist, "familia") and getattr(activo, "familia_id", None):
                ambito_q |= Q(familia=activo.familia)
            if hasattr(PlantillaChecklist, "activo"):
                ambito_q |= Q(activo=activo)
            qs = qs.filter(ambito_q) if ambito_q else qs
        else:
            if hasattr(PlantillaChecklist, "es_global"):
                qs = qs.filter(es_global=True)

        order_by = []
        if hasattr(PlantillaChecklist, "es_global"):
            order_by.append("-es_global")
        if hasattr(PlantillaChecklist, "version"):
            order_by.append("-version")
        order_by.append("nombre")
        self.fields["plantilla"].queryset = qs.order_by(*order_by)

# ──────────────────────────────────────────────────────────────────────────────
# Guardar checklist como plantilla
# ──────────────────────────────────────────────────────────────────────────────
class GuardarComoPlantillaForm(forms.Form):
    nombre = forms.CharField(max_length=120)
    es_global = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Marcar si quieres que esté disponible para cualquier activo.",
    )

# ──────────────────────────────────────────────────────────────────────────────
# Asignar OT a un operario
# ──────────────────────────────────────────────────────────────────────────────
class AsignarOTForm(forms.Form):
    operario = forms.ModelChoiceField(
        queryset=_operarios_queryset(),
        required=True,
        label="Asignar a"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional: Allow empty label for operario selection.
        # self.fields["operario"].empty_label = "— Selecciona un operario —"

# ──────────────────────────────────────────────────────────────────────────────
# Registro de mantenimiento
# ──────────────────────────────────────────────────────────────────────────────
class RegistroMantenimientoForm(forms.ModelForm):
    class Meta:
        model = RegistroMantenimiento
        fields = ['activo', 'tipo', 'falla']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'falla' in self.fields:
            self.fields['falla'].required = False
            self.fields['falla'].queryset = CatalogoFalla.objects.all().order_by('nombre')

# ──────────────────────────────────────────────────────────────────────────────
# Formulario para evidencia detallada
# ──────────────────────────────────────────────────────────────────────────────
class EvidenciaDetalleForm(forms.ModelForm):
    class Meta:
        model = EvidenciaDetalle
        fields = ['archivo']
