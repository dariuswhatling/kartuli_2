from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("upload/", views.upload, name="upload"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("<int:pk>/reprocess/", views.reprocess, name="reprocess"),
]
