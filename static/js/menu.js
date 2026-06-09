(function () {
    var toggle = document.getElementById("menu-toggle");
    var drawer = document.getElementById("menu-drawer");
    var backdrop = document.getElementById("menu-backdrop");
    if (!toggle || !drawer || !backdrop) return;

    function closeMenu() {
        drawer.classList.remove("open");
        backdrop.classList.remove("open");
        document.body.style.overflow = "";
    }

    function openMenu() {
        drawer.classList.add("open");
        backdrop.classList.add("open");
        document.body.style.overflow = "hidden";
    }

    toggle.addEventListener("click", function () {
        if (drawer.classList.contains("open")) closeMenu();
        else openMenu();
    });
    backdrop.addEventListener("click", closeMenu);
})();
