import json
from django.shortcuts import render
from django.db.models import Count
from activos.models import Novedad


def dashboard(request):
    fallas_qs = (
        Novedad.objects.values("falla__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    labels_fallas = [row["falla__nombre"] or "Sin falla" for row in fallas_qs]
    counts_fallas = [row["total"] for row in fallas_qs]
    total = sum(counts_fallas) or 1
    cumulative = []
    acc = 0
    for c in counts_fallas:
        acc += c
        cumulative.append(round(acc * 100 / total, 2))
    etapas_qs = (
        Novedad.objects.values("etapa")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    labels_etapas = [row["etapa"] or "Sin etapa" for row in etapas_qs]
    counts_etapas = [row["total"] for row in etapas_qs]
    ctx = {
        "labels_fallas": json.dumps(labels_fallas),
        "counts_fallas": json.dumps(counts_fallas),
        "cumulative_fallas": json.dumps(cumulative),
        "labels_etapas": json.dumps(labels_etapas),
        "counts_etapas": json.dumps(counts_etapas),
    }
    return render(request, "reports/dashboard.html", ctx)