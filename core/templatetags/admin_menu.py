"""Custom helpers to organise the Django admin dashboard."""

from __future__ import annotations
from collections import OrderedDict
from typing import Iterable, List, MutableMapping

from django import template
from django.utils.translation import gettext_lazy as _


register = template.Library()


# ``app_list`` entries contain keys such as ``app_label`` and ``models``.
# We only rely on those keys so the helper continues to work with future
# Django versions.
AppList = MutableMapping[str, object]
ModelInfo = MutableMapping[str, object]


# Definition of the sections we want to show for each app.  The values are
# sets of ``object_name`` strings so that they stay stable even if the verbose
# names shown in the UI change.
APP_SECTIONS = {
    "activos": OrderedDict(
        [
            (
                _("Operación"),
                {
                    "Activo",
                    "RegistroMantenimiento",
                    "DetalleMantenimiento",
                    "EvidenciaDetalle",
                    "DocumentoActivo",
                },
            ),
            (
                _("Catálogos"),
                {
                    "FamiliaActivo",
                    "CategoriaActivo",
                    "EstadoActivo",
                    "CatalogoFalla",
                    "TareaMantenimiento",
                    "PlantillaChecklist",
                    "PlantillaItem",
                    "Sistema",
                    "Subsistema",
                    "ItemMantenible",
                    "Parte",
                    "Ubicacion",
                    "RegistroCiclosSemanal",
                },
            ),
        ]
    ),
    "horometro": OrderedDict(
        [
            (_("Seguimiento"), {"LecturaHorometro"}),
            (_("Alertas"), {"AlertaMantenimiento"}),
        ]
    ),
    "auth": OrderedDict([(_("Gestión"), {"User", "Group"})]),
}

OTHER_SECTION_LABEL = _("Otros")


@register.filter
def organise_admin_app(app: AppList) -> AppList:
    """Return a copy of an ``app_list`` entry with grouped model sections.

    ``app`` is the dictionary provided by Django.  We calculate a ``sections``
    key that contains the grouped models so the template can iterate over them.
    """

    app_label = str(app.get("app_label", ""))
    models: Iterable[ModelInfo] = app.get("models", [])  # type: ignore[assignment]
    config = APP_SECTIONS.get(app_label, OrderedDict())

    # Keep a predictable order.  ``models`` is already ordered by Django, so we
    # store them in a dictionary keyed by ``object_name`` for quick lookups but
    # iterate preserving the input ordering.
    ordered_models: List[ModelInfo] = list(models)
    model_by_object = {str(m.get("object_name")): m for m in ordered_models}
    used = set()
    sections = []

    for title, object_names in config.items():
        section_models = [
            model_by_object[name]
            for name in ordered_models_object_names(ordered_models)
            if name in object_names and name in model_by_object and name not in used
        ]
        if section_models:
            sections.append({"title": title, "models": section_models})
            used.update(m.get("object_name") for m in section_models)

    remaining = [m for m in ordered_models if m.get("object_name") not in used]
    if remaining:
        sections.append({"title": OTHER_SECTION_LABEL, "models": remaining})

    if sections:
        show_titles = len(sections) > 1
        for section in sections:
            section["show_title"] = show_titles

    # Return a shallow copy to avoid mutating the original data structure.
    grouped = dict(app)
    grouped["sections"] = sections
    return grouped


def ordered_models_object_names(models: Iterable[ModelInfo]) -> Iterable[str]:
    for model in models:
        yield str(model.get("object_name"))
