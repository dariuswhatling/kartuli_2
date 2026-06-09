from django.conf import settings
from django.db import models

from lessons.models import Lesson


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    title = models.CharField(max_length=200, default="New session")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"


class Skill(models.Model):
    """A trackable competency: a topic, optionally scoped to one lesson.

    Mastery is stored here directly (exponential moving average of correctness)
    so the tutor can bias toward weak areas.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="skills",
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="skills",
    )
    topic = models.CharField(max_length=120)
    label = models.CharField(max_length=200, blank=True)
    score = models.FloatField(default=0.5)  # 0 = weak, 1 = strong
    attempts = models.PositiveIntegerField(default=0)
    correct_count = models.FloatField(default=0.0)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "lesson", "topic")
        ordering = ["score", "-last_seen"]

    def __str__(self) -> str:
        scope = self.lesson.title if self.lesson else "all"
        return f"{self.topic} ({scope}): {self.score:.2f}"

    def register_attempt(self, correctness: float, weight: float = 0.35) -> None:
        correctness = max(0.0, min(1.0, correctness))
        self.score = round(self.score * (1 - weight) + correctness * weight, 4)
        self.attempts += 1
        self.correct_count += correctness
        self.save(update_fields=["score", "attempts", "correct_count", "last_seen"])


class Attempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="attempt_log"
    )
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    correctness = models.FloatField(default=0.0)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
