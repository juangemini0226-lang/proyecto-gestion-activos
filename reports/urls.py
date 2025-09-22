from django.urls import path
from . import views

app_name = "reports"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("asset-report/", views.asset_report, name="asset_report"),

]
