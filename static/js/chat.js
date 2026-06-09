(function () {
    const composer = document.getElementById("composer");
    const input = document.getElementById("message-input");
    const messages = document.getElementById("messages");
    const sendBtn = document.getElementById("send-btn");
    if (!composer) return;

    const csrf = composer.querySelector("[name=csrfmiddlewaretoken]").value;
    const url = composer.dataset.url;

    function scrollDown() {
        messages.scrollTop = messages.scrollHeight;
    }

    function addMessage(role, text) {
        const div = document.createElement("div");
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
        const text = input.value.trim();
        if (!text) return;

        addMessage("user", text);
        input.value = "";
        input.disabled = true;
        sendBtn.disabled = true;
        const thinking = addMessage("assistant", "…");

        try {
            const resp = await fetch(url, {
                method: "POST",
                headers: { "X-CSRFToken": csrf },
                body: new URLSearchParams({ message: text }),
            });
            const data = await resp.json();
            if (data.error) {
                thinking.textContent = "⚠ " + data.error;
                thinking.classList.add("bad");
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
