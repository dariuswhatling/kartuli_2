(function () {
    var composer = document.getElementById("composer");
    var input = document.getElementById("message-input");
    var messages = document.getElementById("messages");
    var sendBtn = document.getElementById("send-btn");
    if (!composer) return;

    var csrf = composer.querySelector("[name=csrfmiddlewaretoken]").value;
    var url = composer.dataset.url;

    /* Sessions drawer (mobile) */
    var toggle = document.getElementById("sessions-toggle");
    var drawer = document.getElementById("sessions-drawer");
    var backdrop = document.getElementById("sessions-backdrop");

    function closeDrawer() {
        if (drawer) drawer.classList.remove("open");
        if (backdrop) backdrop.classList.remove("open");
        document.body.style.overflow = "";
    }

    function openDrawer() {
        if (drawer) drawer.classList.add("open");
        if (backdrop) backdrop.classList.add("open");
        document.body.style.overflow = "hidden";
    }

    if (toggle) {
        toggle.addEventListener("click", function () {
            if (drawer && drawer.classList.contains("open")) closeDrawer();
            else openDrawer();
        });
    }
    if (backdrop) backdrop.addEventListener("click", closeDrawer);

    /* Auto-resize textarea */
    function resizeInput() {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 120) + "px";
    }
    input.addEventListener("input", resizeInput);

    function scrollDown() {
        messages.scrollTop = messages.scrollHeight;
    }

    function addMessage(role, text) {
        var div = document.createElement("div");
        div.className = "msg " + role;
        div.textContent = text;
        messages.appendChild(div);
        scrollDown();
        return div;
    }

    scrollDown();

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            composer.requestSubmit();
        }
    });

    composer.addEventListener("submit", async function (e) {
        e.preventDefault();
        var text = input.value.trim();
        if (!text) return;

        addMessage("user", text);
        input.value = "";
        resizeInput();
        input.disabled = true;
        sendBtn.disabled = true;
        var thinking = addMessage("assistant", "…");

        try {
            var resp = await fetch(url, {
                method: "POST",
                headers: { "X-CSRFToken": csrf },
                body: new URLSearchParams({ message: text }),
            });
            var data = await resp.json();
            if (data.error) {
                thinking.textContent = "⚠ " + data.error;
            } else {
                thinking.textContent = data.assistant.content;
            }
        } catch (err) {
            thinking.textContent = "⚠ Network error. Please try again.";
        } finally {
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
            scrollDown();
        }
    });
})();
