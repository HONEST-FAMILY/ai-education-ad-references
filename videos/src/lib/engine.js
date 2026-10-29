(() => {
  const query = new URLSearchParams(location.search);
  const format = query.get("fmt") === "v" ? "v" : "h";
  document.documentElement.classList.add(format);
  const stageWidth = format === "v" ? 1080 : 1920;
  const stageHeight = format === "v" ? 1920 : 1080;

  const easings = {
    linear: (p) => p,
    in: (p) => p * p * p,
    out: (p) => 1 - Math.pow(1 - p, 3),
    inOut: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    expo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    back: (p) => 1 + 2.70158 * Math.pow(p - 1, 3) + 1.70158 * Math.pow(p - 1, 2),
    quart: (p) => 1 - Math.pow(1 - p, 4),
    smooth: (p) => (p < 0.5 ? 8 * Math.pow(p, 4) : 1 - Math.pow(-2 * p + 2, 4) / 2),
  };

  const tracks = new Map();
  const hooks = [];
  const transformKeys = ["x", "y", "xp", "yp", "scale", "sx", "sy", "rot", "rx", "ry"];
  const transformDefaults = { x: 0, y: 0, xp: 0, yp: 0, scale: 1, sx: 1, sy: 1, rot: 0, rx: 0, ry: 0 };

  const elementsOf = (target) => {
    if (typeof target === "string") return [...document.querySelectorAll(target)];
    if (target instanceof Element) return [target];
    return [...target];
  };

  const round = (value) => Math.round(value * 1e6) / 1e6;

  const tween = (target, start, duration, props, easing = "out") => {
    start = round(start);
    duration = round(duration);
    const elements = elementsOf(target);
    if (elements.length === 0) throw new Error(`no element for ${target}`);
    for (const element of elements) {
      let track = tracks.get(element);
      if (!track) {
        track = {};
        tracks.set(element, track);
      }
      for (const [key, [from, to]] of Object.entries(props)) {
        (track[key] ||= []).push({ start, duration, from, to, easing });
        track[key].sort((a, b) => a.start - b.start);
      }
    }
  };

  const stagger = (target, start, gap, duration, props, easing) => {
    elementsOf(target).forEach((element, index) => tween(element, start + index * gap, duration, props, easing));
  };

  const valueAt = (steps, time) => {
    let current = null;
    for (const step of steps) if (time >= step.start) current = step;
    if (!current) return steps[0].from;
    const progress = current.duration <= 0 ? 1 : Math.min(1, Math.max(0, (time - current.start) / current.duration));
    return current.from + (current.to - current.from) * easings[current.easing](progress);
  };

  const seek = (time) => {
    time = round(time);
    for (const [element, track] of tracks) {
      const values = {};
      for (const key in track) values[key] = valueAt(track[key], time);
      if (transformKeys.some((key) => key in values)) {
        const get = (key) => (key in values ? values[key] : transformDefaults[key]);
        element.style.transform = `translate(${get("xp")}%, ${get("yp")}%) translate(${get("x")}px, ${get("y")}px) rotateX(${get("rx")}deg) rotateY(${get("ry")}deg) rotate(${get("rot")}deg) scale(${get("scale") * get("sx")}, ${get("scale") * get("sy")})`;
      }
      if ("opacity" in values) element.style.opacity = values.opacity;
      if ("blur" in values) element.style.filter = values.blur > 0.05 ? `blur(${values.blur}px)` : "none";
      if (["clipT", "clipR", "clipB", "clipL"].some((key) => key in values)) {
        element.style.clipPath = `inset(${values.clipT || 0}% ${values.clipR || 0}% ${values.clipB || 0}% ${values.clipL || 0}%)`;
      }
      if ("draw" in values) {
        element.style.strokeDasharray = "1 2";
        element.style.strokeDashoffset = String(1 - values.draw);
        element.style.visibility = values.draw <= 0.002 ? "hidden" : "visible";
      }
      if ("mark" in values) element.style.backgroundSize = `${values.mark}% var(--mark-h, 34%)`;
      if ("type" in values) {
        if (element.dataset.full === undefined) element.dataset.full = element.textContent;
        const characters = Array.from(element.dataset.full);
        element.textContent = characters.slice(0, Math.round(values.type * characters.length)).join("");
      }
      if ("count" in values) {
        element.textContent = `${element.dataset.pre || ""}${Math.round(values.count).toLocaleString("ko-KR")}${element.dataset.suf || ""}`;
      }
      if ("w" in values) element.style.width = `${values.w}%`;
    }
    for (const hook of hooks) hook(time);
  };

  const fitText = () => {
    for (const element of document.querySelectorAll("[data-fit]")) {
      const maxWidth = parseFloat(element.dataset.fit) * stageWidth;
      let size = parseFloat(getComputedStyle(element).fontSize);
      while (element.scrollWidth > maxWidth && size > 12) {
        size -= 2;
        element.style.fontSize = `${size}px`;
      }
    }
  };

  window.motion = { format, stageWidth, stageHeight, tween, stagger, hooks, easings };
  window.seek = seek;
  window.__ready = (async () => {
    await Promise.all([
      document.fonts.load('600 40px "SCD"', "가"),
      document.fonts.load('800 40px "SCD"', "가"),
      document.fonts.load('900 40px "SCD"', "가"),
      document.fonts.load('500 40px "Pretendard"', "가"),
      document.fonts.load('700 40px "Pretendard"', "가"),
    ]);
    await document.fonts.ready;
    await Promise.all([...document.images].map((image) => image.decode()));
    fitText();
    window.build(motion);
    seek(0);
    return window.DURATION;
  })();
})();
