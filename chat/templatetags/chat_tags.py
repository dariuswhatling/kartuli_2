import json

from django import template
from django.utils.safestring import mark_safe

from chat.widgets import client_payload

register = template.Library()


@register.inclusion_tag("chat/message.html", takes_context=True)
def render_message(context, message):
    widgets = []
    if message.role == "assistant":
        raw_widgets = message.metadata.get("widgets") or []
        for w in raw_widgets:
            payload = client_payload(w)
            if w.get("answered"):
                payload["answered"] = True
                payload["result"] = w.get("result", {})
            widgets.append(payload)

    return {
        "message": message,
        "widgets": widgets,
        "widgets_json": mark_safe(json.dumps(widgets).replace("'", "&#39;")),
    }
