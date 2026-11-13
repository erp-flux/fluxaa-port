from django.urls import path

from . import views

app_name = "registry"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("escales/", views.call_list, name="call_list"),
    path("escales/nouvelle/", views.call_create, name="call_create"),
    path("escales/port/", views.board, name="board"),
    path("escales/port/occupation/", views.board_occupation, name="board_occupation"),
    path("escales/nouvelle/occupation/", views.berth_occupation, name="berth_occupation"),
    path("escales/<int:pk>/", views.call_detail, name="call_detail"),
    path("escales/<int:pk>/action/<str:action>/", views.call_action, name="call_action"),
    path("escales/<int:pk>/documents/<int:doc_id>/", views.document_download, name="document_download"),
    path("escales/<int:pk>/export/", views.export_call, name="export_call"),
    path("escales/<int:pk>/rapport-des-faits/", views.statement_preview, name="statement_preview"),
    path("escales/<int:pk>/formulaires/", views.form_list, name="form_list"),
    path("escales/<int:pk>/formulaires/<str:code>/", views.form_preview, name="form_preview"),
    path("escales/<int:pk>/terrain/", views.field_app, name="field_app"),
    path("escales/<int:pk>/liste-de-controle/", views.checklist_page, name="checklist"),
    path("notifications/", views.notifications, name="notifications"),
    path("pilotage/", views.calibration, name="calibration"),
    path("statistiques/", views.statistics, name="statistics"),
    path("bord/", views.master_entry, name="master_entry"),
    path("bord/sortie/", views.master_logout, name="master_logout"),
    path("bord/nom/", views.link_name, name="link_name"),
    path("bord/<str:token>/", views.master_token, name="master_token"),
    path("verifier/", views.verify, name="verify"),
    path("verifier/<str:code>/", views.verify, name="verify_code"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
]
