import datetime
import pandas as pd

from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .forms import ExcelUploadForm
from .models import (
    Activo,
    FamiliaActivo,
    CatalogoFalla,
    TareaMantenimiento,
    RegistroMantenimiento,
    DetalleMantenimiento,
    RegistroCiclosSemanal,
    EstadoOT,
    TipoOT,
    PlantillaChecklist,
    PlantillaItem,
    PlanPreventivo,
)
from core.models import HistorialOT


# ==========================
#  Import / Export Activos
# ==========================
class ActivoResource(resources.ModelResource):
    class Meta:
        model = Activo


@admin.register(Activo)
class ActivoAdmin(ImportExportModelAdmin):
    resource_class = ActivoResource
    list_display = ("codigo", "numero_activo", "nombre", "familia", "peso")
    list_filter = ("familia",)
    search_fields = ("codigo", "numero_activo", "nombre")
    ordering = ("codigo",)
    list_per_page = 25


# ==========================
#  Familias y Fallas
# ==========================
@admin.register(FamiliaActivo)
class FamiliaActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(CatalogoFalla)
class CatalogoFallaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


# ==========================
#  Tareas maestras
# ==========================
@admin.register(TareaMantenimiento)
class TareaMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre",)


# ==========================
#  Plantillas (con items)
# ==========================
class PlantillaItemInline(admin.TabularInline):
    model = PlantillaItem
    extra = 1
    fields = ("orden", "tarea", "obligatorio", "requiere_evidencia", "notas_sugeridas")
    autocomplete_fields = ("tarea",)
    ordering = ("orden", "id")


@admin.register(PlantillaChecklist)
class PlantillaChecklistAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "ambito", "falla", "version", "vigente", "creado_en")
    list_filter = ("tipo", "vigente", "es_global", "familia", "activo", "falla")
    search_fields = ("nombre", "activo__codigo", "familia__nombre", "falla__codigo", "falla__nombre")
    autocomplete_fields = ("activo", "familia", "falla", "creado_por")
    inlines = (PlantillaItemInline,)
    ordering = ("-creado_en", "-version", "nombre")

    def ambito(self, obj):
        if obj.activo_id:
            return f"ACT:{obj.activo.codigo}"
        if obj.familia_id:
            return f"FAM:{obj.familia.nombre}"
        if obj.es_global:
            return "GLOBAL"
        return "—"

    ambito.short_description = "Ámbito"


# ==========================
#  Inlines para OT
# ==========================
class DetalleInline(admin.TabularInline):
    model = DetalleMantenimiento
    extra = 0
    fields = ("orden", "tarea", "obligatorio", "requiere_evidencia", "completado", "observaciones")
    autocomplete_fields = ("tarea",)
    show_change_link = True
    ordering = ("orden", "id")


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
        "falla",
        "plantilla_aplicada",
        "estado_badge",
        "asignado_a",
        "creado_por",
        "fecha_creacion",
        "porcentaje_avance_display",
        "checklist_btn",
    )
    list_filter = ("estado", "tipo", "asignado_a", "falla", "plantilla_aplicada")
    search_fields = (
        "id",
        "activo__codigo",
        "activo__nombre",
        "asignado_a__username",
        "creado_por__username",
        "falla__codigo",
        "falla__nombre",
    )
    date_hierarchy = "fecha_creacion"
    ordering = ("-fecha_creacion", "-id")
    list_select_related = ("activo", "asignado_a", "creado_por", "completado_por", "falla", "plantilla_aplicada")
    autocomplete_fields = ("activo", "asignado_a", "creado_por", "completado_por", "falla", "plantilla_aplicada")
    inlines = (DetalleInline, HistorialInline)
    actions = (
        "action_aplicar_mejor_plantilla",
        "action_generar_checklist_base",
        "action_iniciar",
        "action_en_revision",
        "action_cerrar",
    )

    # ----- columnas auxiliares -----
    def activo_codigo(self, obj):
        return obj.activo.codigo

    activo_codigo.short_description = "Código"

    def activo_nombre(self, obj):
        return obj.activo.nombre

    activo_nombre.short_description = "Activo"

    def estado_badge(self, obj):
        color = {
            "PEN": "secondary",
            "PRO": "info",
            "REV": "warning",
            "CER": "success",
        }.get(obj.estado, "secondary")
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
    def action_aplicar_mejor_plantilla(self, request, queryset):
        """
        Encuentra y aplica la mejor plantilla (Activo → Familia → Global; por falla cuando aplique)
        recreando el checklist de cada OT seleccionada.
        """
        ok, sin = 0, []
        for ot in queryset.select_related("activo", "activo__familia", "falla"):
            plantilla = PlantillaChecklist.mejor_coincidencia(
                activo=ot.activo, tipo=ot.tipo, falla=ot.falla
            )
            if plantilla:
                ot.aplicar_plantilla(plantilla)
                ok += 1
            else:
                sin.append(f"#{ot.id} ({ot.activo.codigo})")
        if ok:
            self.message_user(request, f"Plantilla aplicada en {ok} OTs.", level=messages.SUCCESS)
        if sin:
            self.message_user(request, "Sin plantilla para: " + ", ".join(sin), level=messages.WARNING)

    action_aplicar_mejor_plantilla.short_description = "Aplicar mejor plantilla"

    def action_generar_checklist_base(self, request, queryset):
        """
        Fallback: genera checklist con todas las Tareas maestras (sin plantilla).
        """
        tareas = list(TareaMantenimiento.objects.all())
        if not tareas:
            self.message_user(request, "No hay Tareas Maestras para generar checklist.", level=messages.WARNING)
            return
        creados = 0
        for ot in queryset:
            existentes = set(
                DetalleMantenimiento.objects.filter(registro=ot).values_list("tarea_id", flat=True)
            )
            nuevos = [
                DetalleMantenimiento(registro=ot, tarea=t, orden=0)
                for t in tareas if t.id not in existentes
            ]
            if nuevos:
                DetalleMantenimiento.objects.bulk_create(nuevos)
                creados += len(nuevos)
        self.message_user(request, f"Checklist generado/actualizado: {creados} ítems creados.", level=messages.SUCCESS)

    action_generar_checklist_base.short_description = "Generar checklist base (sin plantilla)"

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
#  Planes preventivos
# ==========================================
@admin.register(PlanPreventivo)
class PlanPreventivoAdmin(admin.ModelAdmin):
    list_display = (
        "activo",
        "nombre",
        "plantilla",
        "trigger",
        "cada_n_dias",
        "cada_n_ciclos",
        "proxima_fecha",
        "activo_en",
    )
    list_filter = ("trigger", "activo_en", "activo__familia")
    search_fields = ("activo__codigo", "activo__nombre", "nombre", "plantilla__nombre")
    autocomplete_fields = ("activo", "plantilla")


# ==========================================
#  Registro de Ciclos + Excel
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
                    # Filtra filas de advertencia y sólo MOLD
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


# También visible por separado si quieres editar/filtrar suelto
@admin.register(DetalleMantenimiento)
class DetalleMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("registro", "tarea", "completado", "obligatorio", "requiere_evidencia", "orden")
    list_filter = ("completado", "obligatorio", "requiere_evidencia", "tarea", "registro__estado")
    search_fields = ("registro__id", "tarea__nombre", "registro__activo__codigo")
    ordering = ("registro", "orden", "id")
    autocomplete_fields = ("registro", "tarea")
