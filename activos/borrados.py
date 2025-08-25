# activos/admin.py
from django.contrib import admin
from .models import Activo
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# Define la clase Resource para el modelo Activo.
class ActivoResource(resources.ModelResource):
    class Meta:
        model = Activo

# Registra el modelo Activo en el admin con la funcionalidad de importación.
@admin.register(Activo)
class ActivoAdmin(ImportExportModelAdmin):
    resource_class = ActivoResource
    list_display = ('codigo', 'numero_activo', 'nombre', 'peso')
    search_fields = ('codigo', 'nombre')































import pandas as pd
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from .models import Activo, TareaMantenimiento, RegistroMantenimiento, DetalleMantenimiento, RegistroCiclosSemanal
from .forms import ExcelUploadForm
from import_export import resources
from import_export.admin import ImportExportModelAdmin

# --- IMPORTACIÓN DE ACTIVOS (YA LO TENÍAS) ---
class ActivoResource(resources.ModelResource):
    class Meta:
        model = Activo

@admin.register(Activo)
class ActivoAdmin(ImportExportModelAdmin):
    resource_class = ActivoResource
    list_display = ('codigo', 'numero_activo', 'nombre', 'peso')
    search_fields = ('codigo', 'nombre')

# --- REGISTRO DE OTROS MODELOS (YA LO TENÍAS) ---
@admin.register(TareaMantenimiento)
class TareaMantenimientoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

admin.site.register(DetalleMantenimiento)


#@admin.register(RegistroMantenimiento)
#class RegistroMantenimientoAdmin(admin.ModelAdmin):
    # Reemplazamos los nombres de los campos por los correctos del modelo
#    list_display = ('activo', 'estado', 'tipo', 'asignado_a', 'fecha_creacion')




# --- LÓGICA DE CARGA DE CICLOS DESDE EL ADMIN ---
@admin.register(RegistroCiclosSemanal)
class RegistroCiclosSemanalAdmin(admin.ModelAdmin):
    list_display = ('activo', 'año', 'semana', 'ciclos', 'fecha_carga')
    list_filter = ('año', 'semana', 'activo')

    # 1. Definimos la URL personalizada
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-excel/', self.upload_excel_view, name='upload_excel'),
        ]
        return custom_urls + urls

    # 2. La vista que procesa el archivo
    def upload_excel_view(self, request):
        if request.method == 'POST':
            form = ExcelUploadForm(request.POST, request.FILES)
            if form.is_valid():
                excel_file = request.FILES['archivo_excel']
                try:
                    df = pd.read_excel(excel_file, sheet_name='Odometro')
                    df_moldes = df[df['TIPO ACTIVO'] == 'MOLD'].copy()

                    df_moldes['fecha'] = pd.to_datetime(df_moldes['CICLO INICIAL'])
                    df_moldes['año'] = df_moldes['fecha'].dt.isocalendar().year
                    df_moldes['semana'] = df_moldes['fecha'].dt.isocalendar().week

                    for _, row in df_moldes.iterrows():
                        try:
                            activo_obj = Activo.objects.get(codigo=row['NUMERO ACTIVO'])
                            RegistroCiclosSemanal.objects.update_or_create(
                                activo=activo_obj,
                                año=row['año'],
                                semana=row['semana'],
                                defaults={'ciclos': row['MEDIDOR']}
                            )
                        except Activo.DoesNotExist:
                            messages.warning(request, f"Activo {row['NUMERO ACTIVO']} no encontrado. Se omitió.")
                    
                    messages.success(request, "El archivo de Odómetro se ha procesado con éxito.")
                    return redirect("..") # Vuelve a la lista de registros

                except Exception as e:
                    messages.error(request, f"Ocurrió un error al procesar el archivo: {e}")
                
        else:
            form = ExcelUploadForm()

        return render(
            request, 
            "admin/carga_odometro.html", 
            {"form": form}
        )


