# alexa_voice/urls.py
from django.urls import path
from . import views

app_name = "alexa_voice"

urlpatterns = [
    path("voice-command/", views.alexa_voice_command, name="voice_command"),
]
