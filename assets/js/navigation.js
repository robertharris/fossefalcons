(() => {
  const nav = document.querySelector(".nav");
  if (!nav) return;

  document.addEventListener("click", (event) => {
    nav.querySelectorAll(".nav-group[open]").forEach((group) => {
      if (!group.contains(event.target)) group.open = false;
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    nav.querySelectorAll(".nav-group[open]").forEach((group) => {
      if (group.contains(document.activeElement)) {
        group.querySelector("summary").focus();
      }
      group.open = false;
    });
  });
})();
