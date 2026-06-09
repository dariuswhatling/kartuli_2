from django.conf import settings
from django.db import models


class UserSettings(models.Model):
    """Per-user model selections for chat + PDF parsing."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    chat_model = models.CharField(
        max_length=200,
        default="openai/gpt-4o-mini",
        help_text="OpenRouter model used for the tutoring chat.",
    )
    parser_model = models.CharField(
        max_length=200,
        default="openai/gpt-4o-mini",
        help_text="OpenRouter model used to parse and categorise uploaded PDFs.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Settings for {self.user}"


def get_user_settings(user) -> "UserSettings":
    obj, _ = UserSettings.objects.get_or_create(user=user)
    return obj
