from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from .models import (
    Activo,
    TareaMantenimiento,
    PlantillaChecklist,
    RegistroMantenimiento,
    EvidenciaDetalle,
    CatalogoFalla,
    EstadoOT,
    Novedad,
    Sistema,
    Subsistema,
    ItemMantenible,
    Parte,
)

User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
# Formularios de Activos
# ──────────────────────────────────────────────────────────────────────────────


class ImportarTaxonomiaForm(forms.Form):
    archivo = forms.FileField(
        label="Plantilla Excel",
        help_text="Archivo .xlsx con las pestañas Activos, Sistemas, Subsistemas y Partes.",
        widget=forms.ClearableFileInput(
            attrs={"accept": ".xlsx", "class": "form-control"}
        ),
    )



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
            "componentes",
        ]


class TaxonomiaUploadForm(forms.Form):
    """Formulario sencillo para importar la taxonomía desde Excel."""

    activo = forms.ModelChoiceField(
        queryset=Activo.objects.none(),
        label="Activo",
        help_text="Selecciona el activo que recibirá la taxonomía.",
    )
    archivo = forms.FileField(
        label="Archivo Excel (.xlsx)",
        help_text="Debe contener columnas para sistema, subsistema, ítem y parte.",
    )
    limpiar = forms.BooleanField(
        label="Reemplazar jerarquía existente",
        required=False,
        help_text="Si marcas esta opción se borrará la taxonomía previa del activo.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activo"].queryset = Activo.objects.order_by("codigo", "nombre")
        self.fields["activo"].widget.attrs.setdefault("class", "form-select form-select-sm")
        self.fields["archivo"].widget.attrs.setdefault("class", "form-control form-control-sm")
        self.fields["limpiar"].widget.attrs.setdefault("class", "form-check-input")


class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["tag", "codigo", "nombre"]


class SubsistemaForm(forms.ModelForm):
    class Meta:
        model = Subsistema
        fields = ["tag", "codigo", "nombre"]


class ItemMantenibleForm(forms.ModelForm):
    class Meta:
        model = ItemMantenible
        fields = ["tag", "codigo", "nombre"]


class ParteForm(forms.ModelForm):
    class Meta:
        model = Parte
        fields = ["tag", "codigo", "nombre"]


SistemaFormSet = inlineformset_factory(
    Activo,
    Sistema,
    form=SistemaForm,
    fields=["tag", "codigo", "nombre"],
    extra=1,
    can_delete=True,
)


SubsistemaFormSet = inlineformset_factory(
    Sistema,
    Subsistema,
    form=SubsistemaForm,
    fields=["tag", "codigo", "nombre"],
    extra=1,
    can_delete=True,
)


ItemMantenibleFormSet = inlineformset_factory(
    Subsistema,
    ItemMantenible,
    form=ItemMantenibleForm,
    fields=["tag", "codigo", "nombre"],
    extra=1,
    can_delete=True,
)


ParteFormSet = inlineformset_factory(
    ItemMantenible,
    Parte,
    form=ParteForm,
    fields=["tag", "codigo", "nombre"],
    extra=1,
    can_delete=True,
)


def build_taxonomia_formsets(activo, data=None, files=None):
    """Crea el árbol de formsets (Sistema → Subsistema → Item → Parte)."""

    sistema_formset = SistemaFormSet(
        data=data,
        files=files,
        instance=activo,
        prefix="sistemas",
    )

    for sistema_form in sistema_formset.forms:
        sistema_instance = sistema_form.instance
        subsistema_formset = SubsistemaFormSet(
            data=data,
            files=files,
            instance=sistema_instance,
            prefix=f"{sistema_form.prefix}-subsistemas",
        )
        sistema_form.nested = {"subsistemas": subsistema_formset}

        for subsistema_form in subsistema_formset.forms:
            subsistema_instance = subsistema_form.instance
            item_formset = ItemMantenibleFormSet(
                data=data,
                files=files,
                instance=subsistema_instance,
                prefix=f"{subsistema_form.prefix}-items",
            )
            subsistema_form.nested = {"items": item_formset}

            for item_form in item_formset.forms:
                item_instance = item_form.instance
                parte_formset = ParteFormSet(
                    data=data,
                    files=files,
                    instance=item_instance,
                    prefix=f"{item_form.prefix}-partes",
                )
                item_form.nested = {"partes": parte_formset}

    return sistema_formset

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
        label="Asignar a",
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
        fields = [
            "titulo",
            "descripcion",
            "ubicacion",
            "activo",
            "tipo",
            "asignado_a",
            "falla",
            "prioridad",
            "fecha_inicio",
            "vencimiento",
            "recurrencia",
            "tiempo_estimado_minutos",
        ]
        labels = {
            "titulo": "¿Qué hay que hacer?",
            "descripcion": "Descripción",
            "asignado_a": "Asignar a",
            "ubicacion": "Ubicación",
            "prioridad": "Prioridad",
            "fecha_inicio": "Fecha de inicio",
            "vencimiento": "Fecha de vencimiento",
            "recurrencia": "Recurrencia",
            "tipo": "Tipo de trabajo",
            "tiempo_estimado_minutos": "Tiempo estimado (minutos)",
        }
        widgets = {
            "titulo": forms.Textarea(
                attrs={"rows": 3, "placeholder": "¿Qué hay que hacer?"}
            ),
            "descripcion": forms.Textarea(attrs={"rows": 3, "placeholder": "Agregar una descripción"}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "vencimiento": forms.DateInput(attrs={"type": "date"}),
            "tiempo_estimado_minutos": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Añadir clases de Bootstrap a los widgets
        for field in self.fields.values():
            widget = field.widget
            base_class = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {base_class}".strip()

        falla_field = self.fields.get("falla")
        if falla_field:
            falla_field.required = False
            falla_field.queryset = CatalogoFalla.objects.order_by("nombre")

        asignado_field = self.fields.get("asignado_a")
        if asignado_field:
            asignado_field.required = False
            asignado_field.queryset = _operarios_queryset()

        ubicacion_field = self.fields.get("ubicacion")
        if ubicacion_field:
            ubicacion_field.required = False

        prioridad_field = self.fields.get("prioridad")
        if prioridad_field:
            prioridad_field.required = False

        fecha_inicio_field = self.fields.get("fecha_inicio")
        if fecha_inicio_field:
            fecha_inicio_field.required = False

        vencimiento_field = self.fields.get("vencimiento")
        if vencimiento_field:
            vencimiento_field.required = False

        recurrencia_field = self.fields.get("recurrencia")
        if recurrencia_field:
            recurrencia_field.required = False

        tiempo_estimado_field = self.fields.get("tiempo_estimado_minutos")
        if tiempo_estimado_field:
            tiempo_estimado_field.required = False

# ──────────────────────────────────────────────────────────────────────────────
# Formulario para evidencia detallada
# ──────────────────────────────────────────────────────────────────────────────
class EvidenciaDetalleForm(forms.ModelForm):
    class Meta:
        model = EvidenciaDetalle
        fields = ["archivo"]
        widgets = {
            "archivo": forms.ClearableFileInput(attrs={"class": "form-control"})
        }


# ──────────────────────────────────────────────────────────────────────────────
# Reportar novedad de activo
# ──────────────────────────────────────────────────────────────────────────────
class NovedadForm(forms.ModelForm):
    crear_ot = forms.BooleanField(required=False, label="Crear OT")
    archivo = forms.FileField(required=False, label="Adjunto")

    class Meta:
        model = Novedad
        fields = ["etapa", "descripcion", "falla", "archivo", "crear_ot"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        falla_field = self.fields.get("falla")
        if falla_field:
            falla_field.required = False
            falla_field.queryset = CatalogoFalla.objects.order_by("nombre")


class CrearOTDesdeNovedadForm(RegistroMantenimientoForm):
    class Meta(RegistroMantenimientoForm.Meta):
        fields = [
            "titulo",
            "descripcion",
            "asignado_a",
            "prioridad",
            "fecha_inicio",
            "vencimiento",
        ]