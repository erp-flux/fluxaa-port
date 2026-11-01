from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("compte/connexion/", views.LoginView.as_view(), name="login"),
    path("compte/deconnexion/", views.logout_view, name="logout"),
    path("compte/langue/", views.language, name="language"),
    path("compte/mfa/activer/", views.mfa_setup, name="mfa_setup"),
    path("compte/mfa/verifier/", views.mfa_verify, name="mfa_verify"),
    path("compte/", views.profile, name="profile"),
]
