from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from lessons.models import Lesson

from .agent import generate_reply
from .models import Conversation, Message, Skill


@login_required
def home(request):
    conversation = (
        Conversation.objects.filter(user=request.user).order_by("-updated_at").first()
    )
    if conversation is None:
        conversation = Conversation.objects.create(user=request.user)
    return redirect("chat:conversation", pk=conversation.pk)


@login_required
def conversation_view(request, pk: int):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    conversations = Conversation.objects.filter(user=request.user)
    weak_skills = Skill.objects.filter(user=request.user).order_by("score")[:6]
    has_lessons = Lesson.objects.filter(
        user=request.user, status=Lesson.Status.READY
    ).exists()
    return render(
        request,
        "chat/conversation.html",
        {
            "conversation": conversation,
            "conversations": conversations,
            "messages_list": conversation.messages.all(),
            "weak_skills": weak_skills,
            "has_lessons": has_lessons,
            "openrouter_ready": bool(settings.OPENROUTER_API_KEY),
        },
    )


@login_required
@require_POST
def new_conversation(request):
    conversation = Conversation.objects.create(user=request.user)
    return redirect("chat:conversation", pk=conversation.pk)


@login_required
@require_POST
def send_message(request, pk: int):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    content = (request.POST.get("message") or "").strip()
    if not content:
        return JsonResponse({"error": "Empty message."}, status=400)

    user_msg = Message.objects.create(
        conversation=conversation, role=Message.Role.USER, content=content
    )
    if conversation.messages.count() == 1:
        conversation.title = content[:60]
        conversation.save(update_fields=["title"])

    try:
        assistant_msg = generate_reply(conversation, content)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {
                "user": {"content": user_msg.content},
                "error": f"The model request failed: {exc}",
            },
            status=502,
        )

    return JsonResponse(
        {
            "user": {"content": user_msg.content},
            "assistant": {"content": assistant_msg.content},
        }
    )


@login_required
@require_POST
def delete_conversation(request, pk: int):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    conversation.delete()
    return redirect("chat:home")


@login_required
def progress(request):
    skills = Skill.objects.filter(user=request.user).order_by("score")
    return render(request, "chat/progress.html", {"skills": skills})
