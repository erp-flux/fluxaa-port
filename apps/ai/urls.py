from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("assistant/", views.port, name="port"),
    path("escales/<int:pk>/assistant/extraction/<int:doc_id>/", views.extract, name="extract"),
    path("escales/<int:pk>/assistant/verification/<int:review_id>/", views.extraction, name="extraction"),
    path("escales/<int:pk>/assistant/revue/", views.review, name="review"),
    path("escales/<int:pk>/assistant/revue/<int:run_id>/alerte/<int:index>/", views.raise_alert, name="raise_alert"),
    path("escales/<int:pk>/assistant/echange/<int:thread_id>/", views.summarize, name="summarize"),
    path("escales/<int:pk>/assistant/remarques/", views.remarks, name="remarks"),
]
