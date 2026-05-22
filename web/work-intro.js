/* ElectrifySZU Work Intro — Slide Navigation */
(function () {
  const slidesEl = document.getElementById("slides");
  const slideCount = document.querySelectorAll(".slide").length;
  const prevButton = document.getElementById("prevSlide");
  const nextButton = document.getElementById("nextSlide");
  const counter = document.getElementById("counter");
  const dotsContainer = document.getElementById("dots");
  let currentIndex = 0;

  // Build dot indicators
  for (let i = 0; i < slideCount; i++) {
    const dot = document.createElement("span");
    dot.className = "dot";
    dotsContainer.appendChild(dot);
  }

  function goTo(idx) {
    currentIndex = Math.max(0, Math.min(slideCount - 1, idx));
    slidesEl.style.transform = `translateX(-${currentIndex * 100}vw)`;
    prevButton.disabled = currentIndex === 0;
    nextButton.disabled = currentIndex === slideCount - 1;
    counter.textContent = `${currentIndex + 1} / ${slideCount}`;
    document.querySelectorAll(".dot").forEach(function (d, i) {
      d.classList.toggle("active", i === currentIndex);
    });
  }

  prevButton.addEventListener("click", function () { goTo(currentIndex - 1); });
  nextButton.addEventListener("click", function () { goTo(currentIndex + 1); });

  window.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") goTo(currentIndex - 1);
    if (e.key === "ArrowRight" || e.key === " ") {
      e.preventDefault();
      goTo(currentIndex + 1);
    }
  });

  // Touch swipe
  let startX = 0;
  slidesEl.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; }, { passive: true });
  slidesEl.addEventListener("touchend", function (e) {
    var diff = startX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 50) {
      goTo(currentIndex + (diff > 0 ? 1 : -1));
    }
  }, { passive: true });

  goTo(0);

  /* Landscape rotation hint */
  var landscapeToggle = document.getElementById("landscapeToggle");
  var rotateHint = document.getElementById("rotateHint");
  var dismissHint = document.getElementById("dismissHint");

  landscapeToggle.addEventListener("click", function () {
    rotateHint.hidden = false;
  });

  function hideRotateHint() {
    rotateHint.hidden = true;
  }

  dismissHint.addEventListener("click", hideRotateHint);
  rotateHint.addEventListener("click", function (e) {
    if (e.target === rotateHint) hideRotateHint();
  });

  window.addEventListener("orientationchange", function () {
    if (!rotateHint.hidden && window.matchMedia("(orientation: landscape)").matches) {
      hideRotateHint();
    }
  });
})();
