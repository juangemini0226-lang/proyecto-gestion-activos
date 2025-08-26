# activos/forms.py
from django import forms
from django.db.models import Q

from .models import (
    Activo,
    TareaMantenimiento,
    PlantillaChecklist,
    RegistroMantenimiento, # <-- AÑADIR
    EvidenciaDetalle,      # <-- AÑADIR
    CatalogoFalla,  
)


# -----------------------------
# Carga de Excel (odómetro)
# -----------------------------
class ExcelUploadForm(forms.Form):
    semana = forms.ChoiceField(label="Selecciona la Semana del Informe")
    archivo_excel = forms.FileField(label="Selecciona el archivo Excel de Odómetro")

    def __init__(self, *args, **kwargs):
        semanas_usadas = kwargs.pop("semanas_usadas", [])
        super().__init__(*args, **kwargs)

        opciones_semana = [(i, f"Semana {i}") for i in range(1, 53)]
        opciones_disponibles = [op for op in opciones_semana if op[0] not in semanas_usadas]
        self.fields["semana"].choices = opciones_disponibles


# -----------------------------
# Añadir tarea rápida al checklist
# -----------------------------
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


# -----------------------------
# Cargar una plantilla a una OT
# -----------------------------
class CargarPlantillaForm(forms.Form):
    """
    Muestra sólo las plantillas aplicables al contexto:
      - por tipo (requerido si se pasa)
      - por falla (si está disponible en el modelo y se pasa)
      - por ámbito: Global / Familia / Activo (si el modelo tiene 'familia')
    """
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaChecklist.objects.none(),
        label="Plantilla",
    )

    def __init__(self, *args, **kwargs):
        # Contexto que nos pasa la vista
        activo = kwargs.pop("activo", None)
        tipo = kwargs.pop("tipo", None)
        falla = kwargs.pop("falla", None)  # opcional para futuro
        super().__init__(*args, **kwargs)

        # Base: todas (o sólo vigentes si existe el campo)
        qs = PlantillaChecklist.objects.all()
        if hasattr(PlantillaChecklist, "vigente"):
            qs = qs.filter(vigente=True)

        # Filtro por tipo
        if tipo:
            qs = qs.filter(tipo=tipo)

        # Filtro por falla si existe el campo en el modelo
        if falla is not None and hasattr(PlantillaChecklist, "falla"):
            qs = qs.filter(Q(falla=falla) | Q(falla__isnull=True))

        # Ámbito: Global / (Familia) / Activo
        if activo:
            ambito_q = Q(es_global=True)
            if hasattr(PlantillaChecklist, "familia") and getattr(activo, "familia_id", None):
                ambito_q |= Q(familia=activo.familia)
            qs = qs.filter(ambito_q | Q(activo=activo))
        else:
            qs = qs.filter(es_global=True)

        # Orden recomendado: global primero, luego versión (si existe) y nombre
        order_by = []
        if hasattr(PlantillaChecklist, "es_global"):
            order_by.append("-es_global")
        if hasattr(PlantillaChecklist, "version"):
            order_by.append("-version")
        order_by.append("nombre")

        self.fields["plantilla"].queryset = qs.order_by(*order_by)


# -----------------------------
# Guardar checklist como plantilla
# -----------------------------
class GuardarComoPlantillaForm(forms.Form):
    """
    Versión simple (modelo actual): nombre + es_global.
    Si más adelante añades ámbitos por familia/falla, ampliamos aquí sin romper.
    """
    nombre = forms.CharField(max_length=120)
    es_global = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Marcar si quieres que esté disponible para cualquier activo.",
    )

# --- AÑADIR ESTAS DOS NUEVAS CLASES ---

class RegistroMantenimientoForm(forms.ModelForm):
    """
    Formulario para la creación y edición de Órdenes de Trabajo (OT).
    """
    class Meta:
        model = RegistroMantenimiento
        fields = ['activo', 'tipo', 'falla'] # Puedes añadir más campos si lo necesitas

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacemos que el campo de falla sea opcional
        self.fields['falla'].required = False
        self.fields['falla'].queryset = CatalogoFalla.objects.all().order_by('nombre')


class EvidenciaDetalleForm(forms.ModelForm):
    """
    Formulario específico para subir un archivo de evidencia.
    """
    class Meta:
        model = EvidenciaDetalle
        fields = ['archivo']