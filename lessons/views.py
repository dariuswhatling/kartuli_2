import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Lesson
from .services import process_lesson


def _process_async(lesson_id: int) -> None:
    """Run ingestion off the request thread so uploads return quickly."""
    from django.db import connection

    try:
        lesson = Lesson.objects.get(pk=lesson_id)
        process_lesson(lesson)
    finally:
        connection.close()


@login_required
def upload(request):
    if request.method != "POST":
        return redirect("accounts:settings")

    files = request.FILES.getlist("pdfs")
    if not files:
        messages.error(request, "Please choose at least one PDF.")
        return redirect("accounts:settings")

    for f in files:
        title = f.name.rsplit(".", 1)[0]
        lesson = Lesson.objects.create(
            user=request.user,
            title=title,
            original_filename=f.name,
            file=f,
            status=Lesson.Status.PENDING,
        )
        threading.Thread(
            target=_process_async, args=(lesson.pk,), daemon=True
        ).start()

    messages.success(
        request,
        f"Uploaded {len(files)} file(s). Parsing happens in the background; "
        "refresh to see status.",
    )
    return redirect("accounts:settings")


@login_required
def detail(request, pk: int):
    lesson = get_object_or_404(Lesson, pk=pk, user=request.user)
    return render(request, "lessons/detail.html", {"lesson": lesson})


@login_required
def delete(request, pk: int):
    lesson = get_object_or_404(Lesson, pk=pk, user=request.user)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Lesson deleted.")
    return redirect("accounts:settings")


@login_required
def reprocess(request, pk: int):
    lesson = get_object_or_404(Lesson, pk=pk, user=request.user)
    if request.method == "POST":
        threading.Thread(
            target=_process_async, args=(lesson.pk,), daemon=True
        ).start()
        messages.success(request, "Re-parsing started.")
    return redirect("accounts:settings")
