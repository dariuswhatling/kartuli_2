(function () {
    var input = document.getElementById("pdf-input");
    var label = document.getElementById("upload-filename");
    if (!input || !label) return;

    input.addEventListener("change", function () {
        if (!input.files || !input.files.length) {
            label.hidden = true;
            return;
        }
        var names = Array.from(input.files).map(function (f) { return f.name; });
        label.textContent = names.length === 1
            ? names[0]
            : names.length + " files selected";
        label.hidden = false;
    });
})();
