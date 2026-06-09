from django.contrib import admin

from .models import Attempt, Conversation, Message, Skill


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "created_at")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("topic", "user", "lesson", "score", "attempts")
    list_filter = ("topic",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "correctness", "created_at")
