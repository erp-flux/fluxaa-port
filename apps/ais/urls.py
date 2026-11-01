from django.urls import path

from . import views

app_name = "ais"

urlpatterns = [
    path("carte/", views.board, name="board"),
    path("carte/fond/", views.background, name="background"),
]
