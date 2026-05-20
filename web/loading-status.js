(function () {
  const DEFAULTS = {
    dotIntervalMs: 360,
    phraseIntervalMs: 1000,
    timeoutAfterMs: 9000,
  };

  const COPY = {
    "zh-CN": {
      lines: [
        "电费正在快速消耗，请求也在一路狂奔。",
        "校园网可能在绕路，但我们已经追上去了。",
        "电费账单正在飞速发送中。",
        "正在敲门叫醒宿舍电表。",
      ],
      timeoutLines: [
        "这次有点久，校园网可能断了又连上了。",
        "还没回来，服务器也许正在翻旧账单。",
        "如果继续转圈，稍后再试一次会更稳。",
      ],
    },
    "en-US": {
      lines: [
        "Power is draining fast, and the request is sprinting after it.",
        "The campus network may be taking the scenic route.",
        "Your power bill is being dispatched at top speed.",
        "Knocking on the meter room door right now.",
      ],
      timeoutLines: [
        "This is taking a while. The campus network may have blinked.",
        "Still waiting. The server might be digging through old bills.",
        "If it keeps spinning, trying again in a moment may help.",
      ],
    },
  };

  function localeCopy(locale) {
    return COPY[locale] || COPY["zh-CN"];
  }

  function normalizeMainText(text) {
    return String(text || "").replace(/[\s.。…]+$/u, "");
  }

  function createController(element, initialConfig = {}) {
    let active = false;
    let config = normalizeConfig(initialConfig);
    let startedAt = 0;
    let dotTick = 0;
    let phraseIndex = 0;
    let timeoutIndex = 0;
    let dotsTimer = null;
    let phraseTimer = null;
    let mainTextNode = null;
    let dotsNode = null;
    let detailNode = null;

    function normalizeConfig(nextConfig) {
      const locale = nextConfig.locale || config?.locale || "zh-CN";
      const copy = localeCopy(locale);
      return {
        ...DEFAULTS,
        ...copy,
        ...nextConfig,
        locale,
        mainText: normalizeMainText(nextConfig.mainText || config?.mainText || "正在查询电费余额"),
      };
    }

    function ensureMarkup() {
      if (mainTextNode && dotsNode && detailNode) {
        return;
      }

      element.innerHTML = [
        '<span class="message-main">',
        '<span class="message-label"></span>',
        '<span class="message-dots" aria-hidden="true"></span>',
        "</span>",
        '<span class="message-detail is-visible"></span>',
      ].join("");
      mainTextNode = element.querySelector(".message-label");
      dotsNode = element.querySelector(".message-dots");
      detailNode = element.querySelector(".message-detail");
    }

    function detailPool() {
      if (Date.now() - startedAt >= config.timeoutAfterMs && config.timeoutLines.length > 0) {
        return { lines: config.timeoutLines, isTimeout: true };
      }
      return { lines: config.lines, isTimeout: false };
    }

    function renderMain() {
      ensureMarkup();
      mainTextNode.textContent = config.mainText;
      dotsNode.textContent = ".".repeat((dotTick % 3) + 1);
    }

    function renderDetail(nextText) {
      ensureMarkup();
      if (detailNode.textContent === nextText) {
        return;
      }
      detailNode.classList.remove("is-visible");
      requestAnimationFrame(() => {
        detailNode.textContent = nextText;
        detailNode.classList.add("is-visible");
      });
    }

    function updateDetail() {
      const pool = detailPool();
      const lines = pool.lines.length > 0 ? pool.lines : [""];
      const index = pool.isTimeout ? timeoutIndex++ : phraseIndex++;
      renderDetail(lines[index % lines.length]);
    }

    function startTimers() {
      dotsTimer = window.setInterval(() => {
        dotTick += 1;
        renderMain();
      }, config.dotIntervalMs);
      phraseTimer = window.setInterval(updateDetail, config.phraseIntervalMs);
    }

    function clearTimers() {
      window.clearInterval(dotsTimer);
      window.clearInterval(phraseTimer);
      dotsTimer = null;
      phraseTimer = null;
    }

    return {
      start(nextConfig = {}) {
        config = normalizeConfig(nextConfig);
        clearTimers();
        active = true;
        startedAt = Date.now();
        dotTick = 0;
        phraseIndex = 0;
        timeoutIndex = 0;
        element.classList.add("loading");
        element.classList.remove("error");
        renderMain();
        updateDetail();
        startTimers();
      },

      stop() {
        if (!active) {
          return;
        }
        active = false;
        clearTimers();
        element.classList.remove("loading");
      },

      isActive() {
        return active;
      },

      updateConfig(nextConfig = {}) {
        config = normalizeConfig({ ...config, ...nextConfig });
        if (!active) {
          return;
        }
        renderMain();
        updateDetail();
      },
    };
  }

  window.ElectrifySZULoadingStatus = {
    createController,
  };
})();
