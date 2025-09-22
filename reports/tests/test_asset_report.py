import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_asset_report_get(client, user):
    client.force_login(user)
    resp = client.get(reverse("reports:asset_report"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_asset_report_technical_pdf(client, user, activo):
    client.force_login(user)
    data = {"asset": activo.pk, "report_type": "TECH"}
    resp = client.post(reverse("reports:asset_report"), data)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"