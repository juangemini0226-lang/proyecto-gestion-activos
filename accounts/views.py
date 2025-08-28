from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User


@login_required
def users_list(request):
    """Muestra un listado simple de usuarios registrados."""
    users = User.objects.all()
    context = {"users": users, "section": "usuarios"}
    return render(request, "accounts/users_list.html", context)
