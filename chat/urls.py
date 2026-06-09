from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.home, name="home"),
    path("c/new/", views.new_conversation, name="new_conversation"),
    path("c/<int:pk>/", views.conversation_view, name="conversation"),
    path("c/<int:pk>/send/", views.send_message, name="send"),
    path("c/<int:pk>/interact/", views.widget_interact, name="interact"),
    path("c/<int:pk>/delete/", views.delete_conversation, name="delete_conversation"),
]
