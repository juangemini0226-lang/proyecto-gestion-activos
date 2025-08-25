from django.db import models
from django.conf import settings
from django.utils import timezone


# -------- Tarea maestra --------
class TareaMantenimiento(models.Model):
    nombre = models.CharField(max_length=255, verbose_name="Nombre de la Tarea")
    descripcion = models.TextField(blank=True, help_text="Instrucciones detalladas de la tarea.")

    def __str__(self):
        return self.nombre


# -------- NUEVO: Familias de activos (para plantillas por familia) --------
class FamiliaActivo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.nombre


# -------- Activo --------
class Activo(models.Model):
    codigo = models.CharField(max_length=100, unique=True, verbose_name="Código")
    numero_activo = models.CharField(max_length=255, verbose_name="# Activo")
    nombre = models.CharField(max_length=255, verbose_name="Nombre")
    peso = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Peso")

    # NUEVO: familia
    familia = models.ForeignKey(
        "FamiliaActivo", null=True, blank=True, on_delete=models.SET_NULL, related_name="activos"
    )

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


# -------- NUEVO: Catálogo de fallas (para correctivos) --------
class CatalogoFalla(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


# -------- Choices de dominio --------
class EstadoOT(models.TextChoices):
    PEN = "PEN", "Pendiente"
    PRO = "PRO", "En Progreso"
    REV = "REV", "Pendiente Revisión"
    CER = "CER", "Cerrada"  # <- estado de cierre usado por señales/servicios


class TipoOT(models.TextChoices):
    PRE = "PRE", "Preventivo"
    COR = "COR", "Correctivo"


# -------- Registro de mantenimiento (UNIFICADO) --------
class RegistroMantenimiento(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name="mantenimientos")

    estado = models.CharField(max_length=3, choices=EstadoOT.choices, default=EstadoOT.PEN)
    tipo = models.CharField(max_length=3, choices=TipoOT.choices, default=TipoOT.PRE)

    # NUEVO: para correctivas y trazabilidad de plantilla usada
    falla = models.ForeignKey("CatalogoFalla", null=True, blank=True, on_delete=models.SET_NULL, related_name="ots")
    plantilla_aplicada = models.ForeignKey(
        "PlantillaChecklist", null=True, blank=True, on_delete=models.SET_NULL, related_name="ots_usadas"
    )

    # Fechas del ciclo de vida
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_inicio_ejecucion = models.DateTimeField(null=True, blank=True)
    fecha_fin_ejecucion = models.DateTimeField(null=True, blank=True)

    # Cierre / lectura (para baseline en horómetro si aplica)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    anio_ejecucion = models.PositiveSmallIntegerField(null=True, blank=True)
    semana_ejecucion = models.PositiveSmallIntegerField(null=True, blank=True)
    lectura_ejecucion = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Usuarios
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ordenes_creadas"
    )
    asignado_a = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_asignadas"
    )
    completado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tareas_completadas"
    )

    # ---------- Reglas de transición y utilidades ----------
    def can_transition_to(self, nuevo: str) -> bool:
        mapa = {
            EstadoOT.PEN: {EstadoOT.PRO},
            EstadoOT.PRO: {EstadoOT.REV},
            EstadoOT.REV: {EstadoOT.CER},
            EstadoOT.CER: set(),
        }
        return nuevo in mapa.get(self.estado, set())

    def transition_to(self, nuevo: str, usuario=None, motivo: str = ""):
        """
        Punto único de cambio de estado (usar en vistas/servicios).
        Valida transición y fija sellos mínimos.
        """
        if nuevo == self.estado:
            return
        if not self.can_transition_to(nuevo):
            raise ValueError(f"Transición inválida: {self.estado} → {nuevo}")

        # Reglas mínimas por transición
        if nuevo == EstadoOT.PRO and not self.asignado_a:
            raise ValueError("Para pasar a 'PRO' la OT debe estar asignada a un usuario.")

        if nuevo == EstadoOT.PRO and not self.fecha_inicio_ejecucion:
            self.fecha_inicio_ejecucion = timezone.now()

        if nuevo == EstadoOT.REV:
            # Validar checklist completo antes de revisión
            if self.porcentaje_avance < 100:
                raise ValueError("No puede pasar a revisión: el checklist no está completo.")
            if not self.fecha_fin_ejecucion:
                self.fecha_fin_ejecucion = timezone.now()

        if nuevo == EstadoOT.CER:
            return self.cerrar(usuario=usuario, motivo=motivo)

        self.estado = nuevo
        self.save(update_fields=["estado", "fecha_inicio_ejecucion", "fecha_fin_ejecucion"])

    def cerrar(self, usuario=None, motivo: str = ""):
        """
        Cierre formal de la OT. Fija fecha_cierre y completado_por.
        Efectos colaterales (baseline/alertas) se manejan en señales/servicios.
        """
        ahora = timezone.now()
        if not self.fecha_inicio_ejecucion:
            self.fecha_inicio_ejecucion = ahora
        if not self.fecha_fin_ejecucion:
            self.fecha_fin_ejecucion = ahora

        self.fecha_cierre = ahora
        if usuario and getattr(usuario, "pk", None):
            self.completado_por = usuario

        self.estado = EstadoOT.CER
        self.save(
            update_fields=[
                "estado",
                "fecha_inicio_ejecucion",
                "fecha_fin_ejecucion",
                "fecha_cierre",
                "completado_por",
            ]
        )

    # NUEVO: aplicar una plantilla a la OT (recrea el checklist)
    def aplicar_plantilla(self, plantilla: "PlantillaChecklist"):
        items = []
        for it in plantilla.items.select_related("tarea").all():
            items.append(
                DetalleMantenimiento(
                    registro=self,
                    tarea=it.tarea,
                    obligatorio=it.obligatorio,
                    requiere_evidencia=getattr(it, "requiere_evidencia", False),
                    orden=it.orden,
                )
            )
        # Limpiar y cargar
        DetalleMantenimiento.objects.filter(registro=self).delete()
        if items:
            DetalleMantenimiento.objects.bulk_create(items, batch_size=200)
        self.plantilla_aplicada = plantilla
        self.save(update_fields=["plantilla_aplicada"])

    @property
    def porcentaje_avance(self) -> int:
        """
        % de avance del checklist (DetalleMantenimiento.completado).
        """
        total = getattr(self, "detalles", None).count() if hasattr(self, "detalles") else 0
        if total == 0:
            return 0
        hechos = self.detalles.filter(completado=True).count()
        return round(100 * hechos / total)

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.activo.nombre} - {self.get_estado_display()}"

    class Meta:
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["-fecha_creacion"]),
            models.Index(fields=["-fecha_inicio_ejecucion"]),
            models.Index(fields=["-fecha_cierre"]),
            models.Index(fields=["activo"]),
            models.Index(fields=["asignado_a"]),
        ]
        ordering = ["-fecha_creacion", "-id"]


# -------- Detalle de mantenimiento --------
class DetalleMantenimiento(models.Model):
    registro = models.ForeignKey(
        RegistroMantenimiento,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    tarea = models.ForeignKey(TareaMantenimiento, on_delete=models.CASCADE)
    completado = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True, verbose_name="Observaciones")

    # NUEVO: metadatos venidos de la plantilla
    obligatorio = models.BooleanField(default=False)
    requiere_evidencia = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return f"Tarea '{self.tarea.nombre}' para registro {self.registro.id}"


# -------- Plantillas de checklist (para cargar y reutilizar) --------
class PlantillaChecklist(models.Model):
    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=3, choices=TipoOT.choices, default=TipoOT.PRE)

    # Alcance
    activo = models.ForeignKey(Activo, null=True, blank=True, on_delete=models.CASCADE, related_name="plantillas")
    familia = models.ForeignKey("FamiliaActivo", null=True, blank=True, on_delete=models.CASCADE, related_name="plantillas")
    es_global = models.BooleanField(default=False, help_text="Disponible para cualquier activo")

    # Opcional por falla (útil en correctivos)
    falla = models.ForeignKey("CatalogoFalla", null=True, blank=True, on_delete=models.SET_NULL, related_name="plantillas")

    # Versionado / vigencia
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

    @classmethod
    def mejor_coincidencia(cls, *, activo, tipo, falla=None):
        """
        Prioridad: Activo → Familia → Global.
        Si 'falla' viene, prioriza plantillas con esa falla (o sin falla).
        """
        qs = cls.objects.filter(vigente=True, tipo=tipo)
        if falla:
            qs = qs.filter(models.Q(falla=falla) | models.Q(falla__isnull=True))

        cand = qs.filter(activo=activo).order_by("-version").first()
        if cand:
            return cand

        if activo.familia_id:
            cand = qs.filter(familia=activo.familia).order_by("-version").first()
            if cand:
                return cand

        return qs.filter(es_global=True).order_by("-version").first()


class PlantillaItem(models.Model):
    plantilla = models.ForeignKey(PlantillaChecklist, on_delete=models.CASCADE, related_name="items")
    tarea = models.ForeignKey(TareaMantenimiento, on_delete=models.CASCADE)
    obligatorio = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)
    notas_sugeridas = models.TextField(blank=True)
    # NUEVO: si la evidencia es obligatoria (foto/archivo, lo usarás en la vista)
    requiere_evidencia = models.BooleanField(default=False)

    class Meta:
        unique_together = (("plantilla", "tarea"),)
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.plantilla.nombre} · {self.tarea.nombre}"


# -------- Plan preventivo (mínimo viable) --------
class PlanPreventivo(models.Model):
    class Trigger(models.TextChoices):
        DIAS = "DIAS", "Por tiempo"
        CICL = "CICL", "Por ciclos"
        EVT = "EVT", "Por evento"

    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name="planes_preventivos")
    nombre = models.CharField(max_length=120)
    plantilla = models.ForeignKey(PlantillaChecklist, on_delete=models.PROTECT, limit_choices_to={"tipo": TipoOT.PRE})
    trigger = models.CharField(max_length=4, choices=Trigger.choices, default=Trigger.DIAS)

    # Si trigger=DIAS
    cada_n_dias = models.PositiveIntegerField(null=True, blank=True)

    # Si trigger=CICL
    cada_n_ciclos = models.PositiveIntegerField(null=True, blank=True)

    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    proxima_fecha = models.DateField(null=True, blank=True)
    activo_en = models.BooleanField(default=True)

    def __str__(self):
        return f"PM '{self.nombre}' ({self.get_trigger_display()}) - {self.activo.codigo}"


# -------- Historial de ciclos (si lo sigues usando) --------
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

    def __str__(self):
        return f"{self.activo.codigo} - Año {self.año}, Semana {self.semana}: {self.ciclos} ciclos"
