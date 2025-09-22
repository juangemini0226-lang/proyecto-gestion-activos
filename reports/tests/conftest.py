import pytest
from django.contrib.auth.models import Group

from activos.models import Activo


@pytest.fixture
def user(django_user_model):
    u = django_user_model.objects.create_user(
        username="operario1", password="x", is_active=True
    )
    grp, _ = Group.objects.get_or_create(name="Operarios")
    u.groups.add(grp)
    return u


@pytest.fixture
def activo():
    return Activo.objects.create(
        codigo="AC-001",
        numero_activo="1001",
        nombre="Compresor principal",
        peso=100.0,
    )