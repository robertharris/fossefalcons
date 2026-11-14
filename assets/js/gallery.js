(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll("[data-gallery] a"));
  if (!links.length) return;

  var index = 0, opener = null, startX = null;
  var box = document.createElement("div");
  box.className = "lightbox";
  box.hidden = true;
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-modal", "true");
  box.setAttribute("aria-label", "Photo viewer");
  box.innerHTML =
    '<button class="lb-close" type="button" aria-label="Close">&times;</button>' +
    '<button class="lb-prev" type="button" aria-label="Previous photo">&#8249;</button>' +
    '<figure><img alt=""><figcaption></figcaption></figure>' +
    '<button class="lb-next" type="button" aria-label="Next photo">&#8250;</button>';
  document.body.appendChild(box);

  var img = box.querySelector("img");
  var cap = box.querySelector("figcaption");
  var buttons = box.querySelectorAll("button");

  function show(i) {
    index = (i + links.length) % links.length;
    var a = links[index], t = a.querySelector("img");
    img.src = a.href;
    img.alt = t.alt;
    cap.textContent = "";
    var text = a.dataset.caption;
    if (text) cap.appendChild(document.createTextNode(text));
    if (a.dataset.credit) {
      var c = document.createElement("span");
      c.className = "lb-credit";
      c.appendChild(document.createTextNode("Photo: "));
      if (/^https?:\/\//.test(a.dataset.creditUrl || "")) {
        var l = document.createElement("a");
        l.href = a.dataset.creditUrl;
        l.target = "_blank";
        l.rel = "noopener noreferrer";
        l.textContent = a.dataset.credit;
        c.appendChild(l);
      } else {
        c.appendChild(document.createTextNode(a.dataset.credit));
      }
      cap.appendChild(c);
    }
    var n = links[(index + 1) % links.length].href, p = links[(index - 1 + links.length) % links.length].href;
    new Image().src = n;
    new Image().src = p;
  }

  function open(i) {
    opener = document.activeElement;
    show(i);
    box.hidden = false;
    document.body.style.overflow = "hidden";
    box.querySelector(".lb-close").focus();
  }

  function close() {
    box.hidden = true;
    img.removeAttribute("src");
    document.body.style.overflow = "";
    if (opener) opener.focus();
  }

  links.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
      open(i);
    });
  });

  box.querySelector(".lb-close").addEventListener("click", close);
  box.querySelector(".lb-prev").addEventListener("click", function () { show(index - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(index + 1); });
  box.addEventListener("click", function (e) { if (e.target === box || e.target.tagName === "FIGURE") close(); });

  box.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") show(index - 1);
    else if (e.key === "ArrowRight") show(index + 1);
    else if (e.key === "Tab") {
      var first = buttons[0], last = buttons[buttons.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  box.addEventListener("touchstart", function (e) { startX = e.changedTouches[0].clientX; }, { passive: true });
  box.addEventListener("touchend", function (e) {
    if (startX === null) return;
    var dx = e.changedTouches[0].clientX - startX;
    startX = null;
    if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
  });
})();
