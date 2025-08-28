from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.core.files import File
from io import BytesIO
import qrcode


# -------- Tarea maestra --------
class TareaMantenimiento(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre de la Tarea")
    descripcion = models.TextField(blank=True, help_text="Instrucciones detalladas de la tarea.")
    def __str__(self): return self.nombre


# -------- Familias de activos --------
class FamiliaActivo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    def __str__(self): return self.nombre


# -------- Categorías y Estados --------
class CategoriaActivo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.nombre


class EstadoActivo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.nombre


# -------- Activo --------
class Activo(models.Model):
    codigo = models.CharField(max_length=100, unique=True, verbose_name="Código")
    numero_activo = models.CharField(max_length=255, verbose_name="# Activo")
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    peso = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Peso")
    familia = models.ForeignKey("FamiliaActivo", null=True, blank=True, on_delete=models.SET_NULL, related_name="activos")
    categoria = models.ForeignKey("CategoriaActivo", null=True, blank=True, on_delete=models.SET_NULL, related_name="activos")
    estado = models.ForeignKey("EstadoActivo", null=True, blank=True, on_delete=models.SET_NULL, related_name="activos")
    ubicacion = models.ForeignKey("Ubicacion", null=True, blank=True, on_delete=models.SET_NULL, related_name="activos")
    qr_code = models.ImageField(upload_to="qr_codes", blank=True, null=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.qr_code:
            url = reverse("activos:detalle_activo_por_codigo", args=[self.codigo])
            img = qrcode.make(url)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            filename = f"qr_{self.pk}.png"
            self.qr_code.save(filename, File(buffer), save=False)
            super().save(update_fields=["qr_code"])


# -------- Catálogo de fallas --------
class CatalogoFalla(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    def __str__(self): return f"{self.codigo} - {self.nombre}"


# -------- Choices --------
class EstadoOT(models.TextChoices):
    PEN = "PEN", "Pendiente"
    PRO = "PRO", "En Progreso"
    REV = "REV", "Pendiente Revisión"
    CER = "CER", "Cerrada"

class TipoOT(models.TextChoices):
    PRE = "PRE", "Preventivo"
    COR = "COR", "Correctivo"

class PrioridadOT(models.TextChoices):
    NONE = "NONE", "Ninguna"
    BAJA = "BAJA", "Baja"
    MEDI = "MEDI", "Media"
    ALTA = "ALTA", "Alta"

class RecurrenciaOT(models.TextChoices):
    NONE = "NONE", "No se repite"
    DAIL = "DAIL", "Diario"
    WEEK = "WEEK", "Semanal"
    MDATE = "MDATE", "Mensualmente por fecha"
    MDOW = "MDOW", "Mensualmente por día de la semana"
    YEAR = "YEAR", "Anual"


# -------- Ubicación (jerárquica opcional) --------
class Ubicacion(models.Model):
    nombre = models.CharField(max_length=120)
    padre = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="hijos")

    class Meta:
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"

    def __str__(self):
        return f"{self.padre} / {self.nombre}" if self.padre else self.nombre


# -------- Registro de mantenimiento --------
class RegistroMantenimiento(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name="mantenimientos")

    estado = models.CharField(max_length=3, choices=EstadoOT.choices, default=EstadoOT.PEN)
    tipo = models.CharField(max_length=3, choices=TipoOT.choices, default=TipoOT.PRE)

    # ---- Campos “Nueva OT” (inspirado MaintainX) ----
    titulo = models.CharField(max_length=160, default="", blank=False)
    descripcion = models.TextField(blank=True, default="")
    prioridad = models.CharField(max_length=4, choices=PrioridadOT.choices, default=PrioridadOT.NONE)
    fecha_inicio = models.DateField(null=True, blank=True)
    vencimiento = models.DateField(null=True, blank=True)
    recurrencia = models.CharField(max_length=5, choices=RecurrenciaOT.choices, default=RecurrenciaOT.NONE)
    tiempo_estimado_minutos = models.PositiveIntegerField(default=0)
    ubicacion = models.ForeignKey(Ubicacion, null=True, blank=True, on_delete=models.SET_NULL, related_name="ordenes")

    # Correctivos / trazabilidad
    falla = models.ForeignKey("CatalogoFalla", null=True, blank=True, on_delete=models.SET_NULL, related_name="ots")
    plantilla_aplicada = models.ForeignKey(
        "PlantillaChecklist", null=True, blank=True, on_delete=models.SET_NULL, related_name="ots_usadas"
    )

    # Fechas de ciclo de vida
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_inicio_ejecucion = models.DateTimeField(null=True, blank=True)
    fecha_fin_ejecucion = models.DateTimeField(null=True, blank=True)

    # Cierre / lecturas
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    anio_ejecucion = models.PositiveSmallIntegerField(null=True, blank=True)
    semana_ejecucion = models.PositiveSmallIntegerField(null=True, blank=True)
    lectura_ejecucion = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Usuarios
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ordenes_creadas")
    asignado_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_asignadas")
    completado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_completadas")

    # ---- Lógica de estados ----
    def can_transition_to(self, nuevo: str) -> bool:
        mapa = {
            EstadoOT.PEN: {EstadoOT.PRO},
            EstadoOT.PRO: {EstadoOT.REV},
            EstadoOT.REV: {EstadoOT.CER},
            EstadoOT.CER: set(),
        }
        return nuevo in mapa.get(self.estado, set())

    def transition_to(self, nuevo: str, usuario=None, motivo: str = ""):
        if nuevo == self.estado:
            return
        if not self.can_transition_to(nuevo):
            raise ValueError(f"Transición inválida: {self.estado} → {nuevo}")

        if nuevo == EstadoOT.PRO and not self.asignado_a:
            raise ValueError("Para pasar a 'PRO' la OT debe estar asignada a un usuario.")
        if nuevo == EstadoOT.PRO and not self.fecha_inicio_ejecucion:
            self.fecha_inicio_ejecucion = timezone.now()

        if nuevo == EstadoOT.REV:
            if self.porcentaje_avance < 100:
                raise ValueError("No puede pasar a revisión: el checklist no está completo.")
            if not self.fecha_fin_ejecucion:
                self.fecha_fin_ejecucion = timezone.now()

        if nuevo == EstadoOT.CER:
            return self.cerrar(usuario=usuario, motivo=motivo)

        self.estado = nuevo
        self.save(update_fields=["estado", "fecha_inicio_ejecucion", "fecha_fin_ejecucion"])

    def cerrar(self, usuario=None, motivo: str = ""):
        ahora = timezone.now()
        if not self.fecha_inicio_ejecucion:
            self.fecha_inicio_ejecucion = ahora
        if not self.fecha_fin_ejecucion:
            self.fecha_fin_ejecucion = ahora

        self.fecha_cierre = ahora
        if usuario and getattr(usuario, "pk", None):
            self.completado_por = usuario

        self.estado = EstadoOT.CER
        self.save(update_fields=[
            "estado", "fecha_inicio_ejecucion", "fecha_fin_ejecucion", "fecha_cierre", "completado_por"
        ])

    # Aplicar plantilla → recrea checklist
    def aplicar_plantilla(self, plantilla: "PlantillaChecklist"):
        items = [
            DetalleMantenimiento(
                registro=self,
                tarea=it.tarea,
                obligatorio=it.obligatorio,
                requiere_evidencia=getattr(it, "requiere_evidencia", False),
                orden=it.orden,
            )
            for it in plantilla.items.select_related("tarea").all()
        ]
        DetalleMantenimiento.objects.filter(registro=self).delete()
        if items:
            DetalleMantenimiento.objects.bulk_create(items, batch_size=200)
        self.plantilla_aplicada = plantilla
        self.save(update_fields=["plantilla_aplicada"])

    @property
    def porcentaje_avance(self) -> int:
        total = self.detalles.count()
        if total == 0:
            return 0
        hechos = self.detalles.filter(completado=True).count()
        return round(100 * hechos / total)

    # Compatibilidad con nombres antiguos usados en tests
    @property
    def fecha_fin(self):
        """Alias de ``fecha_fin_ejecucion`` mantenido para compatibilidad."""
        return self.fecha_fin_ejecucion

    @property
    def cerrado_por(self):
        """Alias de ``completado_por`` mantenido para compatibilidad."""
        return self.completado_por

    def __str__(self):
        base = f"{self.get_tipo_display()} de {self.activo.nombre} - {self.get_estado_display()}"
        return f"[{self.titulo}] {base}" if self.titulo else base

    class Meta:
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["prioridad"]),
            models.Index(fields=["-fecha_creacion"]),
            models.Index(fields=["-fecha_inicio_ejecucion"]),
            models.Index(fields=["-fecha_cierre"]),
            models.Index(fields=["vencimiento"]),
            models.Index(fields=["activo"]),
            models.Index(fields=["asignado_a"]),
            models.Index(fields=["ubicacion"]),
        ]
        ordering = ["-fecha_creacion", "-id"]


# -------- Detalle de mantenimiento --------
class DetalleMantenimiento(models.Model):
    registro = models.ForeignKey(RegistroMantenimiento, on_delete=models.CASCADE, related_name="detalles")
    tarea = models.ForeignKey(TareaMantenimiento, on_delete=models.CASCADE)
    completado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    obligatorio = models.BooleanField(default=False)
    requiere_evidencia = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self): return f"Tarea '{self.tarea.nombre}' para registro {self.registro.id}"


# -------- Manager de plantillas --------
class PlantillaChecklistManager(models.Manager):
    def get_best_template_for(self, *, activo: Activo, tipo: str, falla: "CatalogoFalla" = None):
        qs = self.filter(vigente=True, tipo=tipo)
        if falla:
            template = qs.filter(falla=falla).order_by("-version").first()
            if template: return template
        template = qs.filter(activo=activo).order_by("-version").first()
        if template: return template
        if activo.familia:
            template = qs.filter(familia=activo.familia).order_by("-version").first()
            if template: return template
        return qs.filter(es_global=True).order_by("-version").first()


# -------- Plantillas de checklist --------
class PlantillaChecklist(models.Model):
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=3, choices=TipoOT.choices, default=TipoOT.PRE)
    activo = models.ForeignKey(Activo, null=True, blank=True, on_delete=models.CASCADE, related_name="plantillas")
    familia = models.ForeignKey("FamiliaActivo", null=True, blank=True, on_delete=models.CASCADE, related_name="plantillas")
    es_global = models.BooleanField(default=False, help_text="Disponible para cualquier activo")
    falla = models.ForeignKey("CatalogoFalla", null=True, blank=True, on_delete=models.SET_NULL, related_name="plantillas")
    version = models.PositiveIntegerField(default=1)
    vigente = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "nombre"]
        indexes = [
            models.Index(fields=["tipo", "vigente"]),
            models.Index(fields=["es_global"]),
            models.Index(fields=["activo"]),
            models.Index(fields=["familia"]),
            models.Index(fields=["falla"]),
        ]

    def __str__(self):
        if self.activo_id:
            scope = f"ACT:{self.activo.codigo}"
        elif self.familia_id:
            scope = f"FAM:{self.familia.nombre}"
        elif self.es_global:
            scope = "GLOBAL"
        else:
            scope = "SIN ÁMBITO"
        falla = f" · Falla:{self.falla.codigo}" if self.falla_id else ""
        return f"{self.nombre} ({self.get_tipo_display()} · {scope}{falla}) v{self.version}"

    objects = PlantillaChecklistManager()


class PlantillaItem(models.Model):
    plantilla = models.ForeignKey(PlantillaChecklist, on_delete=models.CASCADE, related_name="items")
    tarea = models.ForeignKey(TareaMantenimiento, on_delete=models.CASCADE)
    obligatorio = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)
    notas_sugeridas = models.TextField(blank=True)
    requiere_evidencia = models.BooleanField(default=False)

    class Meta:
        unique_together = (("plantilla", "tarea"),)
        ordering = ["orden", "id"]

    def __str__(self): return f"{self.plantilla.nombre} · {self.tarea.nombre}"


# -------- Plan preventivo --------
class PlanPreventivo(models.Model):
    class Trigger(models.TextChoices):
        DIAS = "DIAS", "Por tiempo"
        CICL = "CICL", "Por ciclos"
        EVT = "EVT", "Por evento"

    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name="planes_preventivos")
    nombre = models.CharField(max_length=120)
    plantilla = models.ForeignKey(PlantillaChecklist, on_delete=models.PROTECT, limit_choices_to={"tipo": TipoOT.PRE})
    trigger = models.CharField(max_length=4, choices=Trigger.choices, default=Trigger.DIAS)
    cada_n_dias = models.PositiveIntegerField(null=True, blank=True)
    cada_n_ciclos = models.PositiveIntegerField(null=True, blank=True)
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    proxima_fecha = models.DateField(null=True, blank=True)
    activo_en = models.BooleanField(default=True)

    def __str__(self): return f"PM '{self.nombre}' ({self.get_trigger_display()}) - {self.activo.codigo}"


# -------- Historial de ciclos --------
class RegistroCiclosSemanal(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name="historial_ciclos")
    año = models.PositiveIntegerField()
    semana = models.PositiveIntegerField()
    ciclos = models.PositiveIntegerField(default=0)
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("activo", "año", "semana"),)
        indexes = [
            models.Index(fields=["activo"]),
            models.Index(fields=["año", "semana"]),
            models.Index(fields=["-fecha_carga"]),
        ]

    def __str__(self): return f"{self.activo.codigo} - Año {self.año}, Semana {self.semana}: {self.ciclos} ciclos"


# -------- Evidencias por detalle --------
class EvidenciaDetalle(models.Model):
    class TipoArchivo(models.TextChoices):
        IMG = "IMG", "Imagen"
        FILE = "FILE", "Archivo"

    detalle_mantenimiento = models.ForeignKey(DetalleMantenimiento, on_delete=models.CASCADE, related_name="evidencias")
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="Subido por")
    archivo = models.FileField(upload_to="evidencias_mantenimiento/%Y/%m/%d/")
    tipo = models.CharField(max_length=4, choices=TipoArchivo.choices, default=TipoArchivo.FILE)
    fecha_carga = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidencia para '{self.detalle_mantenimiento.tarea.nombre}' - OT #{self.detalle_mantenimiento.registro.id}"


# -------- Adjuntos a nivel OT --------
def ot_adjuntos_path(instance, filename):
    from datetime import date
    today = date.today()
    return f"ot_adjuntos/{today:%Y/%m/%d}/OT_{instance.registro_id}/{filename}"

class AdjuntoWO(models.Model):
    registro = models.ForeignKey("RegistroMantenimiento", on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to=ot_adjuntos_path)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="wo_adjuntos")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adjunto de OT"
        verbose_name_plural = "Adjuntos de OT"

    def __str__(self): return f"Adjunto OT#{self.registro_id} - {self.archivo.name}"
