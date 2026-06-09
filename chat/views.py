from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import memory

from lessons.models import Lesson

from .agent import generate_reply
from .models import Conversation, Message
from .widgets import client_payload, grade_widget, memory_note


def _assistant_payload(msg: Message) -> dict:
    widgets = msg.metadata.get("widgets") or []
    return {
        "id": msg.id,
        "content": msg.content,
        "widgets": [client_payload(w) for w in widgets],
    }


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
            "has_lessons": has_lessons,
            "openrouter_ready": bool(settings.OPENROUTER_API_KEY),
            "interact_url": f"/c/{conversation.pk}/interact/",
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
            "assistant": _assistant_payload(assistant_msg),
        }
    )


@login_required
@require_POST
def widget_interact(request, pk: int):
    """Grade a click/tap on an interactive widget."""
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    try:
        message_id = int(request.POST.get("message_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid message."}, status=400)

    widget_id = (request.POST.get("widget_id") or "").strip()
    response = (request.POST.get("response") or "").strip()
    if not widget_id or not response:
        return JsonResponse({"error": "Missing widget or response."}, status=400)

    msg = get_object_or_404(
        Message,
        pk=message_id,
        conversation=conversation,
        role=Message.Role.ASSISTANT,
    )
    widgets = list(msg.metadata.get("widgets") or [])
    target = next((w for w in widgets if w.get("id") == widget_id), None)
    if target is None:
        return JsonResponse({"error": "Widget not found."}, status=404)
    if target.get("answered"):
        return JsonResponse({"error": "Already answered.", "result": target.get("result")})

    result = grade_widget(target, response)
    if target["type"] == "flashcard" and response == "reveal":
        return JsonResponse(
            {
                "reveal": True,
                "back": target.get("back", ""),
                "hint": target.get("hint", ""),
            }
        )

    target["answered"] = True
    target["result"] = result
    msg.metadata["widgets"] = widgets
    msg.save(update_fields=["metadata"])

    scope = msg.metadata.get("scope") or {}
    memory.remember(
        conversation.user.id,
        memory_note(target, result),
        metadata={"widget_type": target["type"], "scope": scope},
    )

    return JsonResponse({"result": result})


@login_required
@require_POST
def delete_conversation(request, pk: int):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    conversation.delete()
    return redirect("chat:home")
