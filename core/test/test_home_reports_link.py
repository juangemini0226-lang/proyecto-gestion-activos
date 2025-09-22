import pytest
from django.urls import reverse


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="tester", password="x")


@pytest.fixture
def client_logged(client, user):
    client.login(username="tester", password="x")
    return client


def test_home_contains_reports_link(client_logged):
    response = client_logged.get(reverse("home"))
    assert response.status_code == 200
    assert reverse("reports:asset_report") in response.content.decode()