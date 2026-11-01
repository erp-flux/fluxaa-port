from django.urls import path

from . import views

app_name = "secure"

urlpatterns = [
    path("", views.index, name="index"),
    path("journal/", views.access_log, name="log"),
    path("piece/<int:attachment_id>/", views.attachment, name="attachment"),
    path("<str:reference>/", views.item, name="item"),
]
