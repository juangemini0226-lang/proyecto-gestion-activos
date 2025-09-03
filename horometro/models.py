from decimal import Decimal

from django.db import models
from django.conf import settings
from activos.models import Activo  # import explícito a nivel de módulo


# ----------------------------
# Config / helpers de ficheros
# ----------------------------
# Carpeta de subida: media/horometro/imports/<año>/<semana>/<archivo>
def path_horometro_imports(instance, filename):
    return f"horometro/imports/{instance.anio}/{int(instance.semana):02d}/{filename}"


# --------------------
# Lecturas semanales
# --------------------
class LecturaHorometro(models.Model):
    activo = models.ForeignKey(
        Activo, on_delete=models.PROTECT, related_name="lecturas_horometro"
    )
    anio = models.PositiveSmallIntegerField()
    semana = models.PositiveSmallIntegerField()  # ISO week (1–53)

    # Lectura principal (p.ej. "Ciclos actuales Sx")
    lectura = models.DecimalField(max_digits=12, decimal_places=2)

    # Campos adicionales (opcionales)
    ciclos_oracle = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ciclo_ultimo_preventivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ciclos_desde_ultimo_preventivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Guardar archivo origen en media/… ordenado por año/semana
    fuente_archivo = models.FileField(upload_to=path_horometro_imports, blank=True, null=True)

    # Trazabilidad (número de fila en el Excel)
    fila_excel = models.PositiveIntegerField(null=True, blank=True)

    # Metadatos de auditoría
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["activo", "anio", "semana"],
                name="uniq_lectura_activo_anio_semana",
            )
        ]
        indexes = [
            models.Index(fields=["anio", "semana"]),
            models.Index(fields=["activo"]),
        ]
        ordering = ("-anio", "-semana", "activo__codigo")

    def __str__(self):
        return f"{self.activo} — {self.anio}-W{self.semana:02d}: {self.lectura}"

    # Helper para UI/lógica
    @property
    def anio_semana(self) -> str:
        return f"{self.anio}-W{self.semana:02d}"


# --------------------
# Alertas de mantenimiento
# --------------------
ALERTA_UMBRAL_DEFAULT = Decimal("70000")


class AlertaMantenimiento(models.Model):
    ESTADOS = [
        ("NUEVA", "Nueva"),
        ("EN_PROCESO", "En proceso"),
        ("CERRADA", "Cerrada"),
    ]

    activo = models.ForeignKey(
        Activo, on_delete=models.PROTECT, related_name="alertas_mantenimiento"
    )
    # Lectura que originó (o actualizó) la alerta
    lectura = models.ForeignKey(
        LecturaHorometro, on_delete=models.CASCADE, related_name="alertas", null=True, blank=True
    )

    # Contexto temporal (para listar/filtrar rápidamente)
    anio = models.PositiveSmallIntegerField()
    semana = models.PositiveSmallIntegerField()

    # Métrica que dispara la alerta
    valor_ciclos = models.DecimalField(max_digits=12, decimal_places=2)  # = ciclos_desde_ultimo_preventivo
    umbral = models.DecimalField(max_digits=12, decimal_places=2, default=ALERTA_UMBRAL_DEFAULT)

    estado = models.CharField(max_length=12, choices=ESTADOS, default="NUEVA")
    notas = models.TextField(blank=True)

    # Auditoría
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["anio", "semana"]),
            models.Index(fields=["activo"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["activo", "anio", "semana"],
                name="uniq_alerta_activo_anio_semana",
            )
        ]
        ordering = ["-anio", "-semana", "activo__codigo"]

    def __str__(self):
        return f"[{self.estado}] {self.activo} — {self.anio}-W{self.semana:02d} ({self.valor_ciclos}/{self.umbral})"

    @property
    def abierta(self) -> bool:
        return self.estado in {"NUEVA", "EN_PROCESO"}

