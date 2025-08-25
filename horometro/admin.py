from datetime import date
import csv

from django import forms
from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html
from django.http import HttpResponse

from .models import LecturaHorometro, AlertaMantenimiento
from .services import importer
from .services.alerts import THRESHOLD  # umbral 70.000


# -------- Formulario de carga (Año/Semana) --------
class UploadForm(forms.Form):
    archivo = forms.FileField(label="Archivo Excel")
    hoja = forms.CharField(required=False, help_text="Nombre de hoja (opcional)")

    # Defaults: ISO actuales
    _iso = date.today().isocalendar()
    anio = forms.IntegerField(label="Año (ISO)", min_value=2000, max_value=2100, initial=getattr(_iso, "year", _iso[0]))
    semana = forms.IntegerField(label="Semana (ISO)", min_value=1, max_value=53, initial=getattr(_iso, "week", _iso[1]))

    dry_run = forms.BooleanField(initial=True, required=False, help_text="Simular sin guardar")
    generar_alertas = forms.BooleanField(
        initial=False,
        required=False,
        help_text="Crear/actualizar alertas con esta carga"
    )


@admin.register(AlertaMantenimiento)
class AlertaMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("activo", "anio", "semana", "valor_ciclos", "umbral", "estado", "creado_en")
    list_filter = ("estado", "anio", "semana")
    search_fields = ("activo__codigo", "activo__numero_activo", "activo__nombre")
    readonly_fields = ("creado_en", "actualizado_en", "cerrado_en")


@admin.register(LecturaHorometro)
class LecturaHorometroAdmin(admin.ModelAdmin):
    # -------- Lista --------
    list_display = (
        "activo", "anio", "semana", "lectura",
        "ciclos_oracle", "ciclo_ultimo_preventivo", "ciclos_desde_ultimo_preventivo",
        "estado_riesgo",  # ← badge semáforo
        "archivo_origen", "fila_excel", "creado_en",
    )
    search_fields = ("activo__codigo", "activo__numero_activo", "activo__nombre")
    list_filter = ("anio", "semana")
    ordering = ("-anio", "-semana", "activo__codigo")
    list_per_page = 50
    date_hierarchy = "creado_en"

    # -------- Form de edición --------
    readonly_fields = ("creado_en", "creado_por", "archivo_origen")
    fields = (
        "activo", "anio", "semana", "lectura",
        "ciclos_oracle", "ciclo_ultimo_preventivo", "ciclos_desde_ultimo_preventivo",
        "fuente_archivo", "archivo_origen", "fila_excel",
        "creado_por", "creado_en",
    )

    # Plantilla con botón "Cargar Excel"
    change_list_template = "admin/horometro/lecturahorometro_changelist.html"

    # Optimización de consultas
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("activo", "creado_por")

    # Link al archivo fuente
    def archivo_origen(self, obj):
        if obj.fuente_archivo:
            return format_html('<a href="{}" target="_blank">Descargar</a>', obj.fuente_archivo.url)
        return "—"
    archivo_origen.short_description = "Archivo origen"

    # Badge de estado (semaforo)
    def estado_riesgo(self, obj):
        delta = obj.ciclos_desde_ultimo_preventivo or 0
        try:
            v = float(delta)
        except Exception:
            v = 0.0
        t = float(THRESHOLD)
        if v >= t:
            return format_html('<span class="badge bg-danger">Alerta</span>')
        elif v >= 0.9 * t:
            return format_html('<span class="badge bg-warning text-dark">Cercano</span>')
        else:
            return format_html('<span class="badge bg-success">OK</span>')
    estado_riesgo.short_description = "Riesgo"

    # -------- Acción: Exportar CSV --------
    actions = ["exportar_csv"]

    def exportar_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="lecturas_horometro.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "ActivoNombre", "Codigo", "Numero", "Año", "Semana", "Lectura",
            "CiclosOracle", "CicloUltimoPreventivo", "CiclosDesdeUltimoPreventivo",
            "Archivo", "FilaExcel", "CreadoEn",
        ])
        for l in queryset.select_related("activo"):
            writer.writerow([
                getattr(l.activo, "nombre", ""),
                getattr(l.activo, "codigo", ""),
                getattr(l.activo, "numero_activo", ""),
                l.anio, l.semana, l.lectura,
                l.ciclos_oracle, l.ciclo_ultimo_preventivo, l.ciclos_desde_ultimo_preventivo,
                (l.fuente_archivo.url if l.fuente_archivo else ""),
                l.fila_excel,
                l.creado_en.strftime("%Y-%m-%d %H:%M"),
            ])
        return response
    exportar_csv.short_description = "Exportar a CSV"

    # -------- URL extra: Cargar Excel --------
    def get_urls(self):
        return [
            path("cargar/", self.admin_site.admin_view(self.cargar_excel), name="horometro_cargar_excel"),
            *super().get_urls(),
        ]

    def cargar_excel(self, request):
        if request.method == "POST":
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                resultado = importer.importar_excel(
                    archivo=request.FILES["archivo"],
                    nombre_hoja=form.cleaned_data.get("hoja") or None,
                    dry_run=form.cleaned_data.get("dry_run"),
                    usuario=request.user,
                    anio_fijo=form.cleaned_data["anio"],
                    semana_fija=form.cleaned_data["semana"],
                    generar_alertas=form.cleaned_data["generar_alertas"],  # ← pasa el flag al importador
                )
                if form.cleaned_data.get("dry_run"):
                    messages.info(request, f"Dry-run: {resultado['resumen']}")
                else:
                    msg = f"Importación OK: {resultado['resumen']}"
                    if not form.cleaned_data["generar_alertas"]:
                        msg += " (alertas NO generadas)"
                    messages.success(request, msg)
                return render(
                    request,
                    "admin/horometro/reporte_import.html",
                    {"resultado": resultado, "dry": form.cleaned_data.get("dry_run")},
                )
        else:
            form = UploadForm()
        return render(request, "admin/horometro/subir_excel.html", {"form": form})
