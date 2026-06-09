from django.conf import settings
from django.db import models


class Lesson(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    title = models.CharField(max_length=300)
    original_filename = models.CharField(max_length=300, blank=True)
    file = models.FileField(upload_to="lessons/", blank=True, null=True)
    raw_text = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    topics = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def chunk_count(self) -> int:
        return self.chunks.count()


class Chunk(models.Model):
    """A categorised slice of a lesson, with its embedding for retrieval."""

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="chunks"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    order = models.PositiveIntegerField(default=0)
    text = models.TextField()
    topics = models.JSONField(default=list, blank=True)
    section = models.CharField(max_length=200, blank=True)
    grammar_points = models.JSONField(default=list, blank=True)
    vocab = models.JSONField(default=list, blank=True)
    embedding = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["lesson_id", "order"]

    def __str__(self) -> str:
        return f"{self.lesson.title} #{self.order}"
