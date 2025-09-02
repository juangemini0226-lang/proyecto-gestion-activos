from django.shortcuts import redirect


def dashboard(request):
    return redirect("dashboard_novedades")