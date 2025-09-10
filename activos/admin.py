import datetime
import os
import pandas as pd

from django.contrib import admin, messages
import nested_admin
from django import forms
from django.forms.models import BaseInlineFormSet
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.staticfiles import finders

from xhtml2pdf import pisa

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .forms import ExcelUploadForm
from .models import (
    Activo,
    TareaMantenimiento,
    RegistroMantenimiento,
    DetalleMantenimiento,
    RegistroCiclosSemanal,
    EstadoOT,
    TipoOT,
    FamiliaActivo,
    CategoriaActivo,
    EstadoActivo,
    Ubicacion,
    CatalogoFalla,
    PlantillaChecklist,
    PlantillaItem,
    EvidenciaDetalle,
    DocumentoActivo,
    TipoUbicacion,
    Subsistema,
    ItemMantenible,
    Parte,
)
from core.models import HistorialOT


# ==========================
#  Import / Export Activos
# ==========================
class ActivoResource(resources.ModelResource):
    class Meta:
        model = Activo

class DocumentoActivoInline(nested_admin.NestedTabularInline):
    model = DocumentoActivo
    extra = 0
    fields = ("nombre", "tipo", "archivo")


class BaseUbicacionFormSet(BaseInlineFormSet):
    tipo = None

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if isinstance(instance, Activo):
            kwargs["instance"] = instance.ubicacion
        super().__init__(*args, **kwargs)

    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit=False)
        obj.tipo = self.tipo
        if commit:
            obj.save()
        return obj


class DatalistTextInput(forms.TextInput):
    def __init__(self, datalist_id="", options=None, attrs=None):
        super().__init__(attrs)
        self.datalist_id = datalist_id
        self.options = options or []
        self.attrs.setdefault("list", datalist_id)

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        options_html = "".join(f"<option value=\"{o}\"></option>" for o in self.options)
        datalist_html = f"<datalist id='{self.datalist_id}'>{options_html}</datalist>"
        return mark_safe(input_html + datalist_html)


class UbicacionInlineForm(forms.ModelForm):
    class Meta:
        model = Ubicacion
        fields = ["nombre"]

    def __init__(self, *args, tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tipo:
            nombres = (
                Ubicacion.objects.filter(tipo=tipo)
                .values_list("nombre", flat=True)
                .distinct()
                .order_by("nombre")
            )
            datalist_id = f"nombres_{tipo.lower()}"
            self.fields["nombre"].widget = DatalistTextInput(datalist_id, nombres)


class ParteForm(UbicacionInlineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, tipo=TipoUbicacion.PARTE, **kwargs)


class ItemForm(UbicacionInlineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, tipo=TipoUbicacion.ITEM, **kwargs)


class SubsistemaForm(UbicacionInlineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, tipo=TipoUbicacion.SUBUNIDAD, **kwargs)


class ParteInline(nested_admin.NestedTabularInline):
    model = Ubicacion
    fk_name = "padre"
    extra = 0
    fields = ("nombre", "tipo_label")
    readonly_fields = ("tipo_label",)
    form = ParteForm
    formset = type("ParteFormSet", (BaseUbicacionFormSet,), {"tipo": TipoUbicacion.PARTE})

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo=TipoUbicacion.PARTE)

    def tipo_label(self, obj=None):
        return TipoUbicacion.PARTE.label
    tipo_label.short_description = "Tipo"


class ItemMantenibleInline(nested_admin.NestedStackedInline):
    model = Ubicacion
    fk_name = "padre"
    extra = 0
    fields = ("nombre", "tipo_label")
    readonly_fields = ("tipo_label",)
    inlines = [ParteInline]
    form = ItemForm
    formset = type("ItemFormSet", (BaseUbicacionFormSet,), {"tipo": TipoUbicacion.ITEM})

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo=TipoUbicacion.ITEM)

    def tipo_label(self, obj=None):
        return TipoUbicacion.ITEM.label
    tipo_label.short_description = "Tipo"


class SubsistemaInline(nested_admin.NestedStackedInline):
    model = Ubicacion
    fk_name = "padre"
    extra = 0
    fields = ("nombre", "tipo_label")
    readonly_fields = ("tipo_label",)
    inlines = [ItemMantenibleInline]
    form = SubsistemaForm
    formset = type("SubsistemaFormSet", (BaseUbicacionFormSet,), {"tipo": TipoUbicacion.SUBUNIDAD})

    def __init__(self, parent_model, admin_site):
        super().__init__(Ubicacion, admin_site)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(tipo=TipoUbicacion.SUBUNIDAD)

    def tipo_label(self, obj=None):
        return TipoUbicacion.SUBUNIDAD.label
    tipo_label.short_description = "Tipo"




@admin.register(Activo)
class ActivoAdmin(ImportExportModelAdmin, nested_admin.NestedModelAdmin):
    resource_class = ActivoResource
    change_form_template = "admin/activos/activo/change_form.html"
    list_display = (
        "codigo",
        "numero_activo",
        "nombre",
        "industria",
        "empresa",
        "planta",
        "proceso",
        "seccion",
        "unidad",
        "subunidad",
        "item_mantenible",
        "parte",
        "familia",
        "categoria",
        "estado",
        "ubicacion",
        "peso",
        "ficha_link",
    )
    search_fields = ("codigo", "numero_activo", "nombre")
    list_filter = ("familia", "categoria", "estado")
    list_select_related = ("familia", "categoria", "estado", "ubicacion")
    autocomplete_fields = ("familia", "categoria", "estado", "ubicacion")
    filter_horizontal = ("componentes",)
    ordering = ("codigo",)
    list_per_page = 25
    inlines = (DocumentoActivoInline, SubsistemaInline)
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "componentes":
            kwargs["queryset"] = Activo.objects.filter(
                ubicacion__tipo__in=[
                    TipoUbicacion.SUBUNIDAD,
                    TipoUbicacion.ITEM,
                    TipoUbicacion.PARTE,
                ]
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/ficha/",
                self.admin_site.admin_view(self.ficha_view),
                name="activos_activo_ficha",
            ),
            path(
                "<int:object_id>/ficha/pdf/",
                self.admin_site.admin_view(self.ficha_pdf_view),
                name="activos_activo_ficha_pdf",
            ),
        ]
        return custom + urls

    def ficha_view(self, request, object_id, *args, **kwargs):
        activo = self.get_object(request, object_id)
        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            original=activo,
            pdf_url=reverse("admin:activos_activo_ficha_pdf", args=[activo.pk]),
        )
        return render(request, "activos/ficha_tecnica.html", context)

    def _link_callback(self, uri, rel):
        from django.conf import settings

        if uri.startswith(settings.STATIC_URL):
            path = finders.find(uri.replace(settings.STATIC_URL, ""))
            if path:
                return path
        if uri.startswith(settings.MEDIA_URL):
            return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        return uri

    def ficha_pdf_view(self, request, object_id, *args, **kwargs):
        activo = self.get_object(request, object_id)
        context = {
            "original": activo,
            "pdf": True,
        }
        html = render_to_string("activos/ficha_tecnica.html", context)
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="ficha_{activo.codigo}.pdf"'
        pisa.CreatePDF(html, dest=response, link_callback=self._link_callback)
        return response

    def ficha_link(self, obj):
        url = reverse("admin:activos_activo_ficha", args=[obj.pk])
        return format_html('<a href="{}" class="button">Ficha</a>', url)
    ficha_link.short_description = "Ficha"

    def response_post_save_change(self, request, obj):
        if "_continue" not in request.POST and "_addanother" not in request.POST:
            return redirect(reverse("admin:activos_activo_ficha", args=[obj.pk]))
        return super().response_post_save_change(request, obj)

@admin.register(DocumentoActivo)
class DocumentoActivoAdmin(admin.ModelAdmin):
    list_display = ("activo", "nombre", "tipo", "archivo", "subido")
    list_filter = ("tipo",)
    search_fields = ("nombre", "archivo")

# ==========================
#  Familias de activos
# ==========================
@admin.register(FamiliaActivo)
class FamiliaActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


# ==========================
#  Categorías de activos
# ==========================
@admin.register(CategoriaActivo)
class CategoriaActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


# ==========================
#  Estados de activos
# ==========================
@admin.register(EstadoActivo)
class EstadoActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)

# ==========================
# ==========================
#  Jerarquía ISO 14224
# ==========================
# ==========================
#  Ubicaciones
# ==========================
@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "padre")
    list_filter = ("tipo",)
    search_fields = ("nombre",)


@admin.register(Subsistema)
class SubsistemaAdmin(admin.ModelAdmin):
    list_display = ("activo", "codigo", "nombre")
    search_fields = ("codigo", "nombre", "activo__nombre")


@admin.register(ItemMantenible)
class ItemMantenibleAdmin(admin.ModelAdmin):
    list_display = ("subsistema", "codigo", "nombre")
    search_fields = ("codigo", "nombre", "subsistema__nombre")


@admin.register(Parte)
class ParteAdmin(admin.ModelAdmin):
    list_display = ("item", "codigo", "nombre")
    search_fields = ("codigo", "nombre", "item__nombre")


# ==========================
#  Catálogo de fallas
# ==========================
@admin.register(CatalogoFalla)
class CatalogoFallaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")
    # evitamos list_filter porque no hay familia/criticidad/activa


# ==========================
#  Tareas maestras
# ==========================
@admin.register(TareaMantenimiento)
class TareaMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre",)


# ==========================
#  Plantillas de checklist
# ==========================
class PlantillaItemInline(admin.TabularInline):
    model = PlantillaItem
    extra = 0
    fields = ("tarea",)  # en tu modelo no aparece 'requiere_evidencia' en el item
    autocomplete_fields = ("tarea",)


@admin.register(PlantillaChecklist)
class PlantillaChecklistAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "tipo",
        "es_global",
        "activo",
        "familia",
        "falla",
        "version",
        "vigente",
        "creado_por",
    )
    list_filter = ("tipo", "es_global", "vigente", "familia", "falla", "activo")
    search_fields = ("nombre",)
    inlines = (PlantillaItemInline,)


# ==========================
#  Evidencias por detalle
# ==========================
@admin.register(EvidenciaDetalle)
class EvidenciaDetalleAdmin(admin.ModelAdmin):
    # tu modelo muestra: detalle, subido_por, archivo, tipo
    list_display = ("id", "detalle_ref", "subido_por", "archivo", "tipo")
    list_filter = ("tipo", "subido_por")
    search_fields = ("archivo",)

    def detalle_ref(self, obj):
        # soporte si el campo se llama 'detalle' o 'detalle_mantenimiento'
        return getattr(obj, "detalle", None) or getattr(obj, "detalle_mantenimiento", None)
    detalle_ref.short_description = "Detalle"


class EvidenciaInline(admin.TabularInline):
    model = EvidenciaDetalle
    extra = 0
    fields = ("archivo", "tipo", "subido_por")  # quitamos 'descripcion' y 'creado'
    # si prefieres setear subido_por automáticamente, puedes marcarlo readonly y asignarlo en save_model


# ==========================
#  Inlines para OT
# ==========================
class DetalleInline(admin.TabularInline):
    model = DetalleMantenimiento
    extra = 0
    fields = ("tarea", "completado", "observaciones", "requiere_evidencia")
    autocomplete_fields = ("tarea",)
    show_change_link = True


class HistorialInline(admin.TabularInline):
    model = HistorialOT
    extra = 0
    can_delete = False
    readonly_fields = ("estado_anterior", "estado_nuevo", "usuario", "comentario", "timestamp")
    fields = ("timestamp", "estado_anterior", "estado_nuevo", "usuario", "comentario")
    ordering = ("-timestamp",)


# ==========================
#  Admin para OTs
# ==========================
@admin.register(RegistroMantenimiento)
class RegistroMantenimientoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "activo_codigo",
        "activo_nombre",
        "tipo",
        "estado_badge",
        "falla_nombre",
        "asignado_a",
        "creado_por",
        "fecha_creacion",
        "porcentaje_avance_display",
        "checklist_btn",
    )
    list_filter = ("estado", "tipo", "asignado_a", "falla")
    search_fields = ("id", "activo__codigo", "activo__nombre", "asignado_a__username", "creado_por__username")
    date_hierarchy = "fecha_creacion"
    ordering = ("-fecha_creacion", "-id")
    list_select_related = ("activo", "asignado_a", "creado_por", "completado_por", "falla")
    autocomplete_fields = ("activo", "asignado_a", "creado_por", "completado_por", "falla")
    inlines = (DetalleInline, HistorialInline)
    actions = ("action_generar_checklist_base", "action_iniciar", "action_en_revision", "action_cerrar")

    # ----- columnas auxiliares -----
    def activo_codigo(self, obj):
        return obj.activo.codigo
    activo_codigo.short_description = "Código"

    def activo_nombre(self, obj):
        return obj.activo.nombre
    activo_nombre.short_description = "Activo"

    def falla_nombre(self, obj):
        return getattr(getattr(obj, "falla", None), "nombre", "—")
    falla_nombre.short_description = "Falla"

    def estado_badge(self, obj):
        color = {"PEN": "secondary", "PRO": "info", "REV": "warning", "CER": "success"}.get(obj.estado, "secondary")
        return format_html('<span class="badge text-bg-{}">{}</span>', color, obj.get_estado_display())
    estado_badge.short_description = "Estado"
    estado_badge.admin_order_field = "estado"

    def checklist_btn(self, obj):
        url = reverse("activos:checklist_mantenimiento", args=[obj.id])
        return format_html('<a class="button" href="{}">Checklist</a>', url)
    checklist_btn.short_description = "Checklist"

    def porcentaje_avance_display(self, obj):
        return f"{obj.porcentaje_avance}%"
    porcentaje_avance_display.short_description = "Avance"

    # ----- acciones masivas -----
    def action_generar_checklist_base(self, request, queryset):
        tareas = list(TareaMantenimiento.objects.all())
        if not tareas:
            self.message_user(request, "No hay Tareas Maestras para generar checklist.", level=messages.WARNING)
            return
        creados = 0
        for ot in queryset:
            existentes = set(
                DetalleMantenimiento.objects.filter(registro=ot).values_list("tarea_id", flat=True)
            )
            nuevos = [DetalleMantenimiento(registro=ot, tarea=t) for t in tareas if t.id not in existentes]
            if nuevos:
                DetalleMantenimiento.objects.bulk_create(nuevos)
                creados += len(nuevos)
        self.message_user(request, f"Checklist generado/actualizado: {creados} ítems creados.", level=messages.SUCCESS)
    action_generar_checklist_base.short_description = "Generar checklist base"

    def _transition_bulk(self, request, queryset, nuevo_estado: str, success_msg: str):
        ok, fail = 0, []
        for ot in queryset.select_related("asignado_a"):
            try:
                ot.transition_to(nuevo_estado, usuario=request.user)
                ok += 1
            except Exception as e:
                fail.append(f"#{ot.id}: {e}")
        if ok:
            self.message_user(request, f"{success_msg}: {ok}", level=messages.SUCCESS)
        if fail:
            self.message_user(request, "Errores:\n" + "\n".join(fail), level=messages.ERROR)

    def action_iniciar(self, request, queryset):
        self._transition_bulk(request, queryset, EstadoOT.PRO, "OTs iniciadas")
    action_iniciar.short_description = "Iniciar (PEN → PRO)"

    def action_en_revision(self, request, queryset):
        self._transition_bulk(request, queryset, EstadoOT.REV, "OTs enviadas a revisión")
    action_en_revision.short_description = "Enviar a revisión (PRO → REV)"

    def action_cerrar(self, request, queryset):
        self._transition_bulk(request, queryset, EstadoOT.CER, "OTs cerradas")
    action_cerrar.short_description = "Cerrar (REV → CER)"


# ==========================================
#  Admin para Registro de Ciclos + Excel
# ==========================================
@admin.register(RegistroCiclosSemanal)
class RegistroCiclosSemanalAdmin(admin.ModelAdmin):
    list_display = ("activo", "año", "semana", "ciclos", "fecha_carga")
    list_filter = ("año", "semana", "activo")
    search_fields = ("activo__codigo", "activo__nombre")
    ordering = ("-año", "-semana", "activo__codigo")
    list_per_page = 25

    def get_urls(self):
        urls = super().get_urls()
        custom = [path("upload-excel/", self.upload_excel_view, name="upload_excel")]
        return custom + urls

    def upload_excel_view(self, request):
        año_actual = datetime.date.today().year
        semanas_con_datos = RegistroCiclosSemanal.objects.filter(año=año_actual).values_list("semana", flat=True)

        if request.method == "POST":
            form = ExcelUploadForm(request.POST, request.FILES, semanas_usadas=semanas_con_datos)
            if form.is_valid():
                excel_file = request.FILES["archivo_excel"]
                semana_seleccionada = int(form.cleaned_data["semana"])

                try:
                    df = pd.read_excel(excel_file, sheet_name="Odometro", header=4, engine="openpyxl")
                    df = df[~df["NUMERO ACTIVO"].astype(str).str.contains("El Activo de EAM", na=False)]
                    df_moldes = df[df["TIPO ACTIVO"] == "MOLD"].copy()

                    if df_moldes.empty:
                        messages.warning(request, "No se encontraron registros de tipo 'MOLD' en el archivo.")
                        return redirect("..")

                    creados_o_actualizados = 0
                    for _, row in df_moldes.iterrows():
                        codigo = str(row["NUMERO ACTIVO"]).strip()
                        try:
                            activo_obj = Activo.objects.get(codigo=codigo)
                            RegistroCiclosSemanal.objects.update_or_create(
                                activo=activo_obj,
                                año=año_actual,
                                semana=semana_seleccionada,
                                defaults={"ciclos": row["MEDIDOR"]},
                            )
                            creados_o_actualizados += 1
                        except Activo.DoesNotExist:
                            messages.warning(request, f"Activo {codigo} no encontrado. Se omitió.")

                    messages.success(
                        request, f"Semana {semana_seleccionada} procesada. Registros: {creados_o_actualizados}."
                    )
                    return redirect("..")

                except KeyError as e:
                    messages.error(request, f"Columna faltante en Excel: {e}.")
                    return redirect("..")
                except Exception as e:
                    messages.error(request, f"Ocurrió un error inesperado: {e}")

        else:
            form = ExcelUploadForm(semanas_usadas=semanas_con_datos)

        return render(request, "admin/carga_odometro.html", {"form": form, "title": "Cargar Odómetro"})


# ==========================
#  Detalle + Evidencias
# ==========================
@admin.register(DetalleMantenimiento)
class DetalleMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("registro", "tarea", "completado", "requiere_evidencia")
    list_filter = ("completado", "requiere_evidencia", "tarea", "registro__estado")
    search_fields = ("registro__id", "tarea__nombre", "registro__activo__codigo")
    autocomplete_fields = ("registro", "tarea")
    inlines = (EvidenciaInline,)
