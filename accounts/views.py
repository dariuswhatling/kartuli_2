from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core import openrouter

from .forms import SignupForm
from .models import get_user_settings


def signup(request):
    if request.user.is_authenticated:
        return redirect("chat:home")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("chat:home")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def settings_view(request):
    user_settings = get_user_settings(request.user)
    bust = 1 if request.GET.get("refresh") else 0
    models = openrouter.list_models(cache_token=bust)

    if request.method == "POST":
        chat_model = request.POST.get("chat_model", "").strip()
        parser_model = request.POST.get("parser_model", "").strip()
        if chat_model:
            user_settings.chat_model = chat_model
        if parser_model:
            user_settings.parser_model = parser_model
        user_settings.save()
        return redirect("accounts:settings")

    from lessons.models import Lesson

    lessons = Lesson.objects.filter(user=request.user).order_by("-uploaded_at")
    return render(
        request,
        "accounts/settings.html",
        {
            "user_settings": user_settings,
            "models": models,
            "models_available": bool(models),
            "lessons": lessons,
        },
    )
