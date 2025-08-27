# activos/forms.py
from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import (
    Activo,
    TareaMantenimiento,
    PlantillaChecklist,
    RegistroMantenimiento,  # <-- AÑADIDO
    EvidenciaDetalle,       # <-- AÑADIDO
    CatalogoFalla,          # <-- tu modelo de fallas
)

User = get_user_model()

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
    """
    Muestra solo las plantillas aplicables al contexto.
    Compatible con los campos existentes:
      - tipo (si se pasa)
      - falla (si el modelo PlantillaChecklist lo tiene)
      - ámbitos por es_global / familia / activo (si existen)
    """
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaChecklist.objects.none(),
        label="Plantilla",
    )

    def __init__(self, *args, **kwargs):
        activo = kwargs.pop("activo", None)
        tipo = kwargs.pop("tipo", None)
        falla = kwargs.pop("falla", None)  # opcional
        super().__init__(*args, **kwargs)

        qs = PlantillaChecklist.objects.all()

        # Si el modelo tiene 'vigente', filtramos a las vigentes
        if hasattr(PlantillaChecklist, "vigente"):
            qs = qs.filter(vigente=True)

        # Filtro por tipo, si existe en el modelo
        if tipo and hasattr(PlantillaChecklist, "tipo"):
            qs = qs.filter(tipo=tipo)

        # Filtro por falla si el modelo tiene FK 'falla'
        if falla is not None and hasattr(PlantillaChecklist, "falla"):
            qs = qs.filter(Q(falla=falla) | Q(falla__isnull=True))

        # Ámbito global / familia / activo (compatibilidad con tu esquema actual)
        if activo:
            ambito_q = Q()
            if hasattr(PlantillaChecklist, "es_global"):
                ambito_q |= Q(es_global=True)
            if hasattr(PlantillaChecklist, "familia") and getattr(activo, "familia_id", None):
                ambito_q |= Q(familia=activo.familia)
            # Si el modelo posee FK directo a 'activo', agregamos esa opción
            if hasattr(PlantillaChecklist, "activo"):
                ambito_q |= Q(activo=activo)
            qs = qs.filter(ambito_q) if ambito_q else qs
        else:
            if hasattr(PlantillaChecklist, "es_global"):
                qs = qs.filter(es_global=True)

        # Orden recomendado
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
    """
    Versión simple: nombre + es_global.
    (Si amplías a familia/falla, aquí añadimos esos campos sin romper compatibilidad.)
    """
    nombre = forms.CharField(max_length=120)
    es_global = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Marcar si quieres que esté disponible para cualquier activo.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# NUEVO: Asignación de OT (soluciona el ImportError en views)
# ──────────────────────────────────────────────────────────────────────────────
class AsignarOTForm(forms.Form):
    """
    Form genérico para asignar una OT a un operario.
    Usamos un Form (no ModelForm) para no acoplarnos al nombre del campo en el modelo.
    La vista decide si guarda en .asignado_a, .responsable, .ejecutor, etc.
    """
    operario = forms.ModelChoiceField(
        queryset=_operarios_queryset(),
        required=True,
        label="Asignar a"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si quieres permitir vacío temporalmente:
        # self.fields["operario"].empty_label = "— Selecciona un operario —"


# ──────────────────────────────────────────────────────────────────────────────
# OT: creación/edición y evidencia
# ──────────────────────────────────────────────────────────────────────────────
class RegistroMantenimientoForm(forms.ModelForm):
    """
    Formulario para la creación y edición de Órdenes de Trabajo (OT).
    """
    class Meta:
        model = RegistroMantenimiento
        fields = ['activo', 'tipo', 'falla']  # agrega más si lo necesitas

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Campo de falla opcional y ordenado
        if 'falla' in self.fields:
            self.fields['falla'].required = False
            self.fields['falla'].queryset = CatalogoFalla.objects.all().order_by('nombre')


class EvidenciaDetalleForm(forms.ModelForm):
    """
    Formulario específico para subir un archivo de evidencia.
    """
    class Meta:
        model = EvidenciaDetalle
        fields = ['archivo']
        # Si quisieras múltiples archivos:
        # widgets = {'archivo': forms.ClearableFileInput(attrs={'multiple': True})}
