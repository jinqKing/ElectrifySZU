/* ElectrifySZU Work Intro — Slide Navigation */
var WorkIntro = {};
(function (ns) {
  var slidesEl = document.getElementById("slides");
  var slideCount = document.querySelectorAll(".slide").length;
  var prevBtn = document.getElementById("prevSlide");
  var nextBtn = document.getElementById("nextSlide");
  var counter = document.getElementById("counter");
  var dotsBox = document.getElementById("dots");
  var cur = 0;

  // build dot indicators
  for (var i = 0; i < slideCount; i++) {
    var d = document.createElement("span");
    d.className = "dot";
    d.addEventListener("click", (function(idx) {
      return function() { navigate(idx); };
    })(i));
    dotsBox.appendChild(d);
  }

  /** Navigate to slide *idx*, update all UI, persist to history */
  function navigate(newCur) {
    cur = Math.max(0, Math.min(slideCount - 1, newCur));
    slidesEl.style.transform = "translateX(-" + (cur * 100) + "dvw)";
    prevBtn.disabled = cur === 0;
    nextBtn.disabled = cur === slideCount - 1;
    counter.textContent = (cur + 1) + " / " + slideCount;
    document.querySelectorAll(".dot").forEach(function (el, j) {
      el.classList.toggle("active", j === cur);
    });
    try { history.replaceState({ slide: cur }, "", "#" + (cur + 1)); } catch (_) {}
  }

  // Button clicks
  prevBtn.addEventListener("click", function () { navigate(cur - 1); });
  nextBtn.addEventListener("click", function () { navigate(cur + 1); });

  // Keyboard — scoped to .deck element
  var deck = document.querySelector(".deck");
  deck.setAttribute("tabindex", "-1");
  deck.focus();
  deck._kbActive = true;
  deck.addEventListener("focusin", function () { deck._kbActive = true; });
  deck.addEventListener("focusout", function (e) {
    if (!deck.contains(e.relatedTarget)) deck._kbActive = false;
  });
  deck.addEventListener("click", function () { deck.focus(); });
  deck.addEventListener("keydown", function (e) {
    if (!deck._kbActive) return;
    switch (e.key) {
      case "ArrowLeft": navigate(cur - 1); break;
      case "ArrowRight":
      case " ":
        e.preventDefault();
        navigate(cur + 1);
        break;
    }
  });

  // Touch swipe
  var txStart = 0;
  slidesEl.addEventListener("touchstart", function (e) { txStart = e.touches[0].clientX; }, { passive: true });
  slidesEl.addEventListener("touchend", function (e) {
    var delta = txStart - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 50) navigate(cur + (delta > 0 ? 1 : -1));
  }, { passive: true });

  // Browser back/forward
  window.addEventListener("popstate", function (e) {
    if (e.state != null && typeof e.state.slide === "number") {
      navigate(e.state.slide);
    } else {
      var n = parseInt(location.hash.slice(1), 10);
      navigate(n ? n - 1 : 0);
    }
  });

  // Initial: honour hash fragment (#2 means go to slide index 1)
  var seed = parseInt(location.hash.slice(1), 10) - 1;
  navigate((isNaN(seed) || seed < 0) ? 0 : seed);
  // Trigger fade-in
  slidesEl.classList.add("is-ready");

  // ===================== Landscape Hint =====================
  var btnLand = document.getElementById("landscapeToggle");
  var hintEl  = document.getElementById("rotateHint");
  var btnDismiss = document.getElementById("dismissHint");

  function hideHint() { if (hintEl) hintEl.hidden = true; }

  var mq = window.matchMedia("(max-width: 860px) and (pointer: coarse)");
  function bootLandscape(ok) {
    if (!ok) {
      hideHint();
      if (btnLand) btnLand.hidden = true;
      return;
    }
    if (!(btnLand && hintEl && btnDismiss)) return;
    btnLand.hidden = false;

    // 去重注册：clone 替换清除旧监听器
    var newBtn = btnLand.cloneNode(true);
    btnLand.parentNode.replaceChild(newBtn, btnLand);
    btnLand = newBtn;

    btnLand.addEventListener("click", function () {
      // ① 优先尝试 Screen Orientation API（Android Chrome 原生支持）
      if (typeof screen !== 'undefined' && screen.orientation && screen.orientation.lock) {
        screen.orientation.lock('landscape').catch(function () {
          // ② 回退：先全屏再锁（部分 Chrome 需要）
          var el = document.documentElement;
          if (el.requestFullscreen) {
            el.requestFullscreen().then(function () {
              screen.orientation.lock('landscape').catch(function () {});
            }).catch(function () {
              hintEl.hidden = false;   // ③ 都失败 → 显示横幅
            });
          } else {
            hintEl.hidden = false;      // ③ 无全屏 API → 显示横幅
          }
        });
        return;
      }
      // ④ 无 orientation API（iOS Safari）→ 直接显示横幅
      hintEl.hidden = false;
    });

    btnDismiss.addEventListener("click", hideHint);
    hintEl.addEventListener("click", function (e) {
      if (e.target === hintEl) hideHint();
    });
    window.addEventListener("orientationchange", function () {
      if (!hintEl.hidden && window.matchMedia("(orientation: landscape)").matches) hideHint();
    });
  }
  bootLandscape(mq.matches);
  mq.addEventListener("change", function (ev) { bootLandscape(ev.matches); });

  // ===================== Sponsor Modal =====================
  var sponsorBtn = document.getElementById("sponsorButton");
  var modal = document.getElementById("supportModal");
  var closeBtn = document.getElementById("supportClose");
  var backdrop = document.querySelector("[data-support-close]");

  function openSponsor() {
    if (!modal || !sponsorBtn) return;
    modal.hidden = false;
    sponsorBtn.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    var dialog = document.getElementById("supportDialog");
    if (dialog) dialog.focus();
  }

  function closeSponsor() {
    if (!modal || !sponsorBtn) return;
    modal.hidden = true;
    sponsorBtn.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
    sponsorBtn.focus();
  }

  if (sponsorBtn && modal) {
    sponsorBtn.addEventListener("click", openSponsor);
    if (closeBtn) closeBtn.addEventListener("click", closeSponsor);
    if (backdrop) backdrop.addEventListener("click", closeSponsor);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) closeSponsor();
    });
  }

  // Public debug surface
  ns.el = slidesEl;
  ns.total = slideCount;
  ns.index = function () { return cur; };
  ns.navigate = navigate;
})(WorkIntro);
window.WorkIntro = WorkIntro;
