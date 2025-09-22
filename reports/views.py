import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from activos.models import (
    Activo,
    RegistroCiclosSemanal,
    RegistroMantenimiento,
    Novedad,
)

from .forms import AssetReportForm


def dashboard(request):
    return redirect("dashboard_novedades")


def _link_callback(uri, rel):
    """Permite a xhtml2pdf acceder a archivos estáticos y de medios."""
    if uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, ""))
        if path:
            return path
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    return uri


@login_required
def asset_report(request):
    """Genera distintos tipos de informes para uno o varios activos."""
    if request.method == "POST":
        form = AssetReportForm(request.POST)
        if form.is_valid():
            asset = form.cleaned_data.get("asset")
            rtype = form.cleaned_data["report_type"]
            start = form.cleaned_data.get("start_date")
            end = form.cleaned_data.get("end_date")
            context = {"asset": asset, "start": start, "end": end, "pdf": True}

            if rtype == "TECH":
                if asset:
                    context["original"] = asset
                    html = render_to_string("activos/ficha_tecnica.html", context)
                    filename = f"ficha_{asset.codigo}.pdf"
                else:
                    context["activos"] = Activo.objects.all()
                    html = render_to_string("reports/technical_general.html", context)
                    filename = "fichas_tecnicas.pdf"
            elif rtype == "CYCLE":
                qs = RegistroCiclosSemanal.objects.all()
                if asset:
                    qs = qs.filter(activo=asset)
                if start:
                    qs = qs.filter(fecha_carga__date__gte=start)
                if end:
                    qs = qs.filter(fecha_carga__date__lte=end)
                context["registros"] = qs.order_by("año", "semana")
                html = render_to_string("reports/cycle_report.html", context)
                code = asset.codigo if asset else "general"
                filename = f"ciclos_{code}.pdf"
            elif rtype == "FAIL":
                qs = Novedad.objects.all()
                if asset:
                    qs = qs.filter(activo=asset)
                if start:
                    qs = qs.filter(fecha__date__gte=start)
                if end:
                    qs = qs.filter(fecha__date__lte=end)
                context["novedades"] = qs.order_by("-fecha")
                html = render_to_string("reports/failure_report.html", context)
                code = asset.codigo if asset else "general"
                filename = f"fallos_{code}.pdf"
            else:  # TRACE
                qs = RegistroMantenimiento.objects.all()
                if asset:
                    qs = qs.filter(activo=asset)
                if start:
                    qs = qs.filter(fecha_creacion__date__gte=start)
                if end:
                    qs = qs.filter(fecha_creacion__date__lte=end)
                context["ordenes"] = qs.order_by("-fecha_creacion")
                html = render_to_string("reports/trace_report.html", context)
                code = asset.codigo if asset else "general"
                filename = f"trazabilidad_{code}.pdf"

            response = HttpResponse(content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            from xhtml2pdf import pisa

            pisa.CreatePDF(html, dest=response, link_callback=_link_callback)
            return response
    else:
        form = AssetReportForm()
    return render(request, "reports/report_form.html", {"form": form})