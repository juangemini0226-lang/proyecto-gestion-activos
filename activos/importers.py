"""Herramientas para importar jerarquías de taxonomía desde hojas de cálculo."""

from __future__ import annotations

import io
import re
import unicodedata
from typing import Iterable, Mapping, Optional

import pandas as pd
from django.db import transaction

from .models import Activo, ItemMantenible, Parte, Sistema, Subsistema


class TaxonomiaImporter:
    """Importa la jerarquía Sistema → Subsistema → Ítem → Parte para un activo."""

    def __init__(self, activo: Activo, archivo, hoja: Optional[str] = None):
        self.activo = activo
        self.archivo = archivo
        self.hoja = hoja

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def importar(self) -> None:
        datos = self._load_dataframe()
        with transaction.atomic():
            self._importar(datos)

    # ------------------------------------------------------------------
    # Carga de datos
    # ------------------------------------------------------------------
    def _load_dataframe(self) -> pd.DataFrame:
        if isinstance(self.archivo, pd.DataFrame):
            return self.archivo.copy()

        if isinstance(self.archivo, (list, tuple)):
            return pd.DataFrame(list(self.archivo))

        if hasattr(self.archivo, "read"):
            # Resetear el puntero para asegurar que pandas lea todo el archivo.
            try:
                pos = self.archivo.tell()
            except (AttributeError, OSError):
                pos = None
            if hasattr(self.archivo, "seek"):
                self.archivo.seek(0)
            df = pd.read_excel(self.archivo, sheet_name=self.hoja)
            if pos is not None and hasattr(self.archivo, "seek"):
                self.archivo.seek(pos)
            return df

        if isinstance(self.archivo, (str, bytes, io.IOBase)):
            return pd.read_excel(self.archivo, sheet_name=self.hoja)

        raise TypeError("Tipo de archivo no soportado para la importación de taxonomía.")

    # ------------------------------------------------------------------
    # Procesamiento fila a fila
    # ------------------------------------------------------------------
    def _importar(self, datos: pd.DataFrame | Iterable[Mapping[str, object]]) -> None:
        if isinstance(datos, pd.DataFrame):
            registros = datos.to_dict("records")
        else:
            registros = list(datos)

        for fila in registros:
            normalizada = self._normalizar_fila(fila)

            sistema_nombre = normalizada.get("sistema")
            if not sistema_nombre:
                continue

            sistema, _ = self._upsert_sistema(
                nombre=sistema_nombre,
                codigo=normalizada.get("sistema_codigo"),
                tag_excel=normalizada.get("sistema_tag"),
            )

            subsistema_nombre = normalizada.get("subsistema")
            if not subsistema_nombre:
                continue

            subsistema, _ = self._upsert_subsistema(
                sistema=sistema,
                nombre=subsistema_nombre,
                codigo=normalizada.get("subsistema_codigo"),
                tag_excel=normalizada.get("subsistema_tag"),
            )

            item_nombre = normalizada.get("item")
            if not item_nombre:
                continue

            item, _ = self._upsert_item(
                subsistema=subsistema,
                nombre=item_nombre,
                codigo=normalizada.get("item_codigo"),
                tag_excel=normalizada.get("item_tag"),
            )

            parte_nombre = normalizada.get("parte")
            if not parte_nombre:
                continue

            self._upsert_parte(
                item=item,
                nombre=parte_nombre,
                codigo=normalizada.get("parte_codigo"),
                tag_excel=normalizada.get("parte_tag"),
            )

    # ------------------------------------------------------------------
    # Upserts por nivel
    # ------------------------------------------------------------------
    def _upsert_sistema(self, nombre: str, codigo: Optional[str], tag_excel: Optional[str]):
        return self._upsert_taxonomia(
            modelo=Sistema,
            parent_field="activo",
            parent=self.activo,
            nombre=nombre,
            codigo=codigo,
            tag_excel=tag_excel,
            default_prefix="SYS",
            parent_tag=None,
        )

    def _upsert_subsistema(
        self,
        sistema: Sistema,
        nombre: str,
        codigo: Optional[str],
        tag_excel: Optional[str],
    ):
        return self._upsert_taxonomia(
            modelo=Subsistema,
            parent_field="sistema",
            parent=sistema,
            nombre=nombre,
            codigo=codigo,
            tag_excel=tag_excel,
            default_prefix="SUB",
            parent_tag=sistema.tag,
        )

    def _upsert_item(
        self,
        subsistema: Subsistema,
        nombre: str,
        codigo: Optional[str],
        tag_excel: Optional[str],
    ):
        return self._upsert_taxonomia(
            modelo=ItemMantenible,
            parent_field="subsistema",
            parent=subsistema,
            nombre=nombre,
            codigo=codigo,
            tag_excel=tag_excel,
            default_prefix="ITEM",
            parent_tag=subsistema.tag,
        )

    def _upsert_parte(
        self,
        item: ItemMantenible,
        nombre: str,
        codigo: Optional[str],
        tag_excel: Optional[str],
    ):
        return self._upsert_taxonomia(
            modelo=Parte,
            parent_field="item",
            parent=item,
            nombre=nombre,
            codigo=codigo,
            tag_excel=tag_excel,
            default_prefix="PAR",
            parent_tag=item.tag,
        )

    def _upsert_taxonomia(
        self,
        modelo,
        parent_field: str,
        parent,
        nombre: str,
        codigo: Optional[str],
        tag_excel: Optional[str],
        default_prefix: str,
        parent_tag: Optional[str],
    ):
        filtros = {parent_field: parent, "nombre__iexact": (nombre or "").strip()}
        instancia = modelo.objects.filter(**filtros).first()
        creada = instancia is None

        if creada:
            instancia = modelo(**{parent_field: parent})

        instancia.nombre = (nombre or "").strip()
        instancia.codigo = (codigo or "").strip()

        tag_excel = self._clean_explicit_tag(tag_excel)

        if creada:
            base = tag_excel or self._default_tag(default_prefix, instancia.nombre, parent_tag)
            instancia.tag = self._unique_tag(modelo, base)
        elif tag_excel and tag_excel != instancia.tag:
            instancia.tag = self._unique_tag(modelo, tag_excel, ignore_pk=instancia.pk)

        instancia.save()
        return instancia, creada

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _default_tag(self, prefix: str, nombre: str, parent_tag: Optional[str]) -> str:
        slug = self._slugify(nombre)
        if parent_tag:
            base = f"{parent_tag}-{slug}" if slug else parent_tag
        else:
            base = f"{prefix}-{slug}" if slug else prefix
        return base or prefix

    def _unique_tag(self, modelo, base: str, ignore_pk: Optional[int] = None) -> str:
        base = (base or "TAG").strip()
        if not base:
            base = "TAG"

        qs = modelo.objects.all()
        if ignore_pk is not None:
            qs = qs.exclude(pk=ignore_pk)

        if not qs.filter(tag=base).exists():
            return base

        sufijo = 2
        while True:
            candidato = f"{base}-{sufijo}"
            if not qs.filter(tag=candidato).exists():
                return candidato
            sufijo += 1

    def _slugify(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        value = unicodedata.normalize("NFKD", value)
        value = value.encode("ascii", "ignore").decode("ascii")
        value = re.sub(r"[^0-9A-Za-z]+", "-", value)
        value = re.sub(r"-+", "-", value)
        return value.strip("-").upper()

    def _clean_explicit_tag(self, tag: Optional[str]) -> str:
        if tag is None:
            return ""
        return str(tag).strip()

    def _normalizar_fila(self, fila: Mapping[str, object]) -> dict[str, Optional[str]]:
        normalizada: dict[str, Optional[str]] = {}
        for clave, valor in fila.items():
            if clave is None:
                continue
            key = self._normalizar_clave(str(clave))
            normalizada[key] = None if valor is None else str(valor).strip()
        return normalizada

    def _normalizar_clave(self, clave: str) -> str:
        clave = clave.strip().lower()
        clave = unicodedata.normalize("NFKD", clave)
        clave = clave.encode("ascii", "ignore").decode("ascii")
        clave = clave.replace(" ", "_")
        clave = clave.replace("-", "_")
        clave = clave.replace("__", "_")
        reemplazos = {
            "tag_sistema": "sistema_tag",
            "tag_subsistema": "subsistema_tag",
            "tag_item": "item_tag",
            "tag_parte": "parte_tag",
        }
        return reemplazos.get(clave, clave)