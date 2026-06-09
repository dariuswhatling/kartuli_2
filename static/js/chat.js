(function () {
    var composer = document.getElementById("composer");
    var input = document.getElementById("message-input");
    var messages = document.getElementById("messages");
    var sendBtn = document.getElementById("send-btn");
    if (!composer) return;

    var csrf = composer.querySelector("[name=csrfmiddlewaretoken]").value;
    var sendUrl = composer.dataset.url;
    var interactUrl = composer.dataset.interactUrl;

    var TYPE_LABELS = {
        mcq: "Multiple choice",
        true_false: "True or false",
        translate_pick: "Translation",
        flashcard: "Flashcard",
        fill_blank: "Fill the blank",
        conjugate: "Conjugation",
        self_rating: "Confidence check",
    };

    function resizeInput() {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 120) + "px";
    }
    input.addEventListener("input", resizeInput);

    function scrollDown() {
        messages.scrollTop = messages.scrollHeight;
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    }

    function showFeedback(widgetEl, result) {
        var existing = widgetEl.querySelector(".widget-feedback");
        if (existing) existing.remove();
        var fb = el("div", "widget-feedback");
        if (result.correct === true) fb.classList.add("ok");
        else if (result.correct === false) fb.classList.add("no");
        else fb.classList.add("neutral");
        fb.textContent = result.feedback || (result.correct ? "Correct!" : "Not quite.");
        widgetEl.appendChild(fb);
    }

    async function postInteract(messageId, widgetId, response, thinking) {
        var body = new URLSearchParams({
            message_id: messageId,
            widget_id: widgetId,
            response: response,
        });
        var resp = await fetch(interactUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: body,
        });
        var data = await resp.json();
        if (thinking) thinking.remove();
        return data;
    }

    function appendFollowup(data) {
        if (data.user) {
            messages.appendChild(buildMessageEl("user", data.user));
        }
        if (data.assistant) {
            messages.appendChild(buildMessageEl("assistant", data.assistant));
        } else if (data.followup_error) {
            messages.appendChild(buildMessageEl("assistant", { content: "⚠ " + data.followup_error }));
        }
        scrollDown();
    }

    async function submitWidgetAnswer(messageId, widgetId, response, w) {
        var thinking = buildMessageEl("assistant", { content: "…" });
        messages.appendChild(thinking);
        scrollDown();
        return postInteract(messageId, widgetId, response, thinking);
    }

    function disableOptions(widgetEl) {
        widgetEl.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    }

    function markChoice(widgetEl, chosenIdx, correctIdx) {
        widgetEl.querySelectorAll(".widget-opt").forEach(function (btn, i) {
            btn.disabled = true;
            var idx = parseInt(btn.dataset.idx, 10);
            if (idx === correctIdx) btn.classList.add("correct");
            else if (idx === chosenIdx) btn.classList.add("wrong");
        });
    }

    function applyChoiceResult(opts, chosenIdx, result) {
        opts.querySelectorAll(".widget-opt").forEach(function (b) {
            b.disabled = true;
            var idx = parseInt(b.dataset.idx, 10);
            if (idx === result.correct_index) b.classList.add("correct");
            else if (idx === chosenIdx) b.classList.add("wrong");
        });
    }

    function buildMcq(w, messageId, container) {
        var wrap = el("div", "widget widget-mcq");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.mcq));
        wrap.appendChild(el("div", "widget-prompt", w.prompt));
        var opts = el("div", "widget-options");
        w.options.forEach(function (opt, i) {
            var btn = el("button", "widget-opt", opt);
            btn.type = "button";
            btn.dataset.idx = String(i);
            btn.addEventListener("click", async function () {
                if (w.answered) return;
                var data = await submitWidgetAnswer(messageId, w.id, String(i), w);
                if (!data.result) return;
                applyChoiceResult(opts, i, data.result);
                showFeedback(wrap, data.result);
                w.answered = true;
                appendFollowup(data);
            });
            opts.appendChild(btn);
        });
        wrap.appendChild(opts);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildTrueFalse(w, messageId, container) {
        var wrap = el("div", "widget widget-tf");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.true_false));
        wrap.appendChild(el("div", "widget-prompt", w.statement));
        var row = el("div", "widget-row");
        ["true", "false"].forEach(function (val) {
            var label = val === "true" ? "True" : "False";
            var btn = el("button", "widget-opt", label);
            btn.type = "button";
            btn.addEventListener("click", async function () {
                if (w.answered) return;
                var data = await submitWidgetAnswer(messageId, w.id, val, w);
                if (!data.result) return;
                row.querySelectorAll(".widget-opt").forEach(function (b) {
                    b.disabled = true;
                    var isTrue = b.textContent === "True";
                    var chosen = (val === "true" && isTrue) || (val === "false" && !isTrue);
                    if (chosen) b.classList.add(data.result.correct ? "correct" : "wrong");
                    else if (data.result.correct_value === true && isTrue) b.classList.add("correct");
                    else if (data.result.correct_value === false && !isTrue) b.classList.add("correct");
                });
                showFeedback(wrap, data.result);
                w.answered = true;
                appendFollowup(data);
            });
            row.appendChild(btn);
        });
        wrap.appendChild(row);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildTranslate(w, messageId, container) {
        var wrap = el("div", "widget widget-translate");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.translate_pick));
        wrap.appendChild(el("div", "widget-georgian", w.georgian));
        if (w.translit) wrap.appendChild(el("div", "widget-translit", w.translit));
        var opts = el("div", "widget-options");
        w.options.forEach(function (opt, i) {
            var btn = el("button", "widget-opt", opt);
            btn.type = "button";
            btn.dataset.idx = String(i);
            btn.addEventListener("click", async function () {
                if (w.answered) return;
                var data = await submitWidgetAnswer(messageId, w.id, String(i), w);
                if (!data.result) return;
                applyChoiceResult(opts, i, data.result);
                if (data.result) showFeedback(wrap, data.result);
                w.answered = true;
                appendFollowup(data);
            });
            opts.appendChild(btn);
        });
        wrap.appendChild(opts);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildFillBlank(w, messageId, container) {
        var wrap = el("div", "widget widget-blank");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.fill_blank));
        var line = el("div", "widget-blank");
        line.appendChild(document.createTextNode(w.before || ""));
        line.appendChild(el("span", "widget-blank-gap", "___"));
        line.appendChild(document.createTextNode(w.after || ""));
        wrap.appendChild(line);
        var opts = el("div", "widget-options");
        w.options.forEach(function (opt, i) {
            var btn = el("button", "widget-opt", opt);
            btn.type = "button";
            btn.dataset.idx = String(i);
            btn.addEventListener("click", async function () {
                if (w.answered) return;
                var data = await submitWidgetAnswer(messageId, w.id, String(i), w);
                if (!data.result) return;
                applyChoiceResult(opts, i, data.result);
                if (data.result.correct) {
                    wrap.querySelector(".widget-blank-gap").textContent = opt;
                } else if (data.result.correct_index != null) {
                    wrap.querySelector(".widget-blank-gap").textContent = w.options[data.result.correct_index];
                }
                showFeedback(wrap, data.result);
                w.answered = true;
                appendFollowup(data);
            });
            opts.appendChild(btn);
        });
        wrap.appendChild(opts);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildConjugate(w, messageId, container) {
        var wrap = el("div", "widget widget-conjugate");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.conjugate));
        var meta = (w.verb || "") + (w.tense ? " · " + w.tense : "") + (w.subject ? " · " + w.subject : "");
        if (meta) wrap.appendChild(el("div", "widget-meta", meta));
        wrap.appendChild(el("div", "widget-prompt", "Pick the correct form:"));
        var opts = el("div", "widget-options");
        w.options.forEach(function (opt, i) {
            var btn = el("button", "widget-opt", opt);
            btn.type = "button";
            btn.dataset.idx = String(i);
            btn.addEventListener("click", async function () {
                if (w.answered) return;
                var data = await submitWidgetAnswer(messageId, w.id, String(i), w);
                if (!data.result) return;
                applyChoiceResult(opts, i, data.result);
                showFeedback(wrap, data.result);
                w.answered = true;
                appendFollowup(data);
            });
            opts.appendChild(btn);
        });
        wrap.appendChild(opts);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildFlashcard(w, messageId, container) {
        var wrap = el("div", "widget widget-flashcard");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.flashcard));
        var front = el("div", "widget-flashcard-front", w.front);
        wrap.appendChild(front);
        if (w.hint) wrap.appendChild(el("div", "widget-translit", w.hint));

        var backEl = el("div", "widget-flashcard-back");
        backEl.style.display = "none";
        wrap.appendChild(backEl);

        var actions = el("div", "widget-row");
        actions.style.marginTop = "12px";

        if (!w.answered) {
            var revealBtn = el("button", "btn btn-ghost btn-sm", "Reveal answer");
            revealBtn.type = "button";
            revealBtn.addEventListener("click", async function () {
                var data = await postInteract(messageId, w.id, "reveal", null);
                if (data.reveal) {
                    backEl.textContent = data.back;
                    backEl.style.display = "block";
                    revealBtn.remove();
                    var knew = el("button", "btn btn-sm", "Got it");
                    var practice = el("button", "btn btn-ghost btn-sm", "Need practice");
                    knew.type = "button";
                    practice.type = "button";
                    knew.addEventListener("click", async function () {
                        disableOptions(wrap);
                        var res = await submitWidgetAnswer(messageId, w.id, "knew", w);
                        if (res.result) showFeedback(wrap, res.result);
                        w.answered = true;
                        appendFollowup(res);
                    });
                    practice.addEventListener("click", async function () {
                        disableOptions(wrap);
                        var res = await submitWidgetAnswer(messageId, w.id, "practice", w);
                        if (res.result) showFeedback(wrap, res.result);
                        w.answered = true;
                        appendFollowup(res);
                    });
                    actions.appendChild(knew);
                    actions.appendChild(practice);
                }
            });
            actions.appendChild(revealBtn);
        }
        wrap.appendChild(actions);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    function buildRating(w, messageId, container) {
        var wrap = el("div", "widget widget-rating-wrap");
        wrap.appendChild(el("div", "widget-type", TYPE_LABELS.self_rating));
        wrap.appendChild(el("div", "widget-prompt", w.prompt));
        var row = el("div", "widget-rating");
        var scale = w.scale || 5;
        for (var i = 1; i <= scale; i++) {
            (function (rating) {
                var btn = el("button", null, String(rating));
                btn.type = "button";
                btn.addEventListener("click", async function () {
                    if (w.answered) return;
                    disableOptions(wrap);
                    var data = await submitWidgetAnswer(messageId, w.id, String(rating), w);
                    btn.classList.add("correct");
                    if (data.result) showFeedback(wrap, data.result);
                    w.answered = true;
                    appendFollowup(data);
                });
                row.appendChild(btn);
            })(i);
        }
        wrap.appendChild(row);
        if (w.answered && w.result) showFeedback(wrap, w.result);
        container.appendChild(wrap);
    }

    var BUILDERS = {
        mcq: buildMcq,
        true_false: buildTrueFalse,
        translate_pick: buildTranslate,
        fill_blank: buildFillBlank,
        conjugate: buildConjugate,
        flashcard: buildFlashcard,
        self_rating: buildRating,
    };

    function renderWidgets(stackEl, messageId) {
        var raw = stackEl.dataset.widgets;
        if (!raw) return;
        var widgets;
        try { widgets = JSON.parse(raw); } catch (e) { return; }
        stackEl.innerHTML = "";
        widgets.forEach(function (w) {
            var builder = BUILDERS[w.type];
            if (builder) builder(w, messageId, stackEl);
        });
    }

    function mountMessage(container) {
        var messageId = container.dataset.messageId;
        var stack = container.querySelector(".widget-stack");
        if (stack && messageId) renderWidgets(stack, messageId);
    }

    function buildMessageEl(role, data) {
        if (role === "assistant") {
            var turn = el("div", "msg-turn");
            if (data.id) turn.dataset.messageId = String(data.id);
            if (data.content) {
                var bubble = el("div", "msg assistant");
                bubble.appendChild(el("div", "msg-text", data.content));
                turn.appendChild(bubble);
            }
            if (data.widgets && data.widgets.length) {
                var stack = el("div", "widget-stack");
                stack.dataset.widgets = JSON.stringify(data.widgets);
                turn.appendChild(stack);
            }
            if (turn.children.length) {
                mountMessage(turn);
                return turn;
            }
        }

        var div = el("div", "msg " + role);
        if (data.id) div.dataset.messageId = String(data.id);
        if (data.content) {
            div.appendChild(el("div", "msg-text", data.content));
        }
        return div;
    }

    document.querySelectorAll(".msg-turn[data-message-id], .msg[data-message-id]").forEach(mountMessage);

    composer.addEventListener("submit", async function (e) {
        e.preventDefault();
        var text = input.value.trim();
        if (!text) return;

        messages.appendChild(buildMessageEl("user", { content: text }));
        input.value = "";
        resizeInput();
        input.disabled = true;
        sendBtn.disabled = true;
        var thinking = buildMessageEl("assistant", { content: "…" });
        messages.appendChild(thinking);

        try {
            var resp = await fetch(sendUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrf },
                body: new URLSearchParams({ message: text }),
            });
            var data = await resp.json();
            thinking.remove();
            if (data.error) {
                messages.appendChild(buildMessageEl("assistant", { content: "⚠ " + data.error }));
            } else if (data.assistant) {
                messages.appendChild(buildMessageEl("assistant", data.assistant));
            }
        } catch (err) {
            thinking.remove();
            messages.appendChild(buildMessageEl("assistant", { content: "⚠ Network error. Please try again." }));
        } finally {
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
            scrollDown();
        }
    });

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            composer.requestSubmit();
        }
    });

    scrollDown();
})();
