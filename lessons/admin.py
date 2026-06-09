from django.contrib import admin

from .models import Chunk, Lesson


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "uploaded_at")
    list_filter = ("status",)
    search_fields = ("title",)


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("lesson", "order", "section")
    search_fields = ("text",)
