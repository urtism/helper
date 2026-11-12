// One floating surface for native title hints and rich evidence tooltips.
export function installVariantTooltips(root) {
  const controller = new AbortController();
  const options = {signal: controller.signal, capture: true};
  const tooltip = document.createElement("div");
  tooltip.className = "variant-tooltip";
  tooltip.id = "variant-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.setAttribute("popover", "manual");
  tooltip.hidden = true;
  root.append(tooltip);
  let active, showTimer, hideTimer, describedBy;
  let titles = [];

  const hide = () => {
    clearTimeout(showTimer);
    clearTimeout(hideTimer);
    if (tooltip.hidePopover && tooltip.matches(":popover-open")) tooltip.hidePopover();
    tooltip.hidden = true;
    if (active) {
      if (describedBy === null) active.removeAttribute("aria-describedby");
      else active.setAttribute("aria-describedby", describedBy);
    }
    for (const [element, title] of titles) {
      if (!element.hasAttribute("title")) element.setAttribute("title", title);
    }
    titles = [];
    active = null;
  };
  const position = () => {
    const anchor = active.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    const margin = 10, gap = 6;
    const left = Math.max(margin, Math.min(anchor.left, innerWidth - box.width - margin));
    const below = anchor.bottom + gap;
    const top = below + box.height <= innerHeight - margin ? below : anchor.top - gap - box.height;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(margin, Math.min(top, innerHeight - box.height - margin))}px`;
  };
  const find = target => {
    for (let element = target; element && element !== root; element = element.parentElement) {
      if (!(element instanceof Element)) break;
      const source = element.querySelector(':scope > [role="tooltip"]');
      if (source) return {trigger: element.querySelector("button, [tabindex]") || element, source};
      if (element.getAttribute("title")?.trim() && !element.matches("iframe, option")) return {trigger: element};
    }
    return null;
  };
  const enter = event => {
    if (tooltip.contains(event.target)) { clearTimeout(hideTimer); return; }
    if (active?.contains(event.target)) { clearTimeout(hideTimer); return; }
    const match = find(event.target);
    if (match?.trigger === active) { clearTimeout(hideTimer); return; }
    if (!match) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(hide, 120);
      return;
    }
    hide();
    active = match.trigger;
    describedBy = active.getAttribute("aria-describedby");
    const text = active.getAttribute("title");
    // Suppress inherited native hints too, so only one tooltip appears.
    for (let element = active; element; element = element.parentElement) {
      if (element.hasAttribute("title")) {
        titles.push([element, element.getAttribute("title")]);
        element.removeAttribute("title");
      }
    }
    if (match.source) {
      tooltip.replaceChildren(...[...match.source.childNodes].map(child => child.cloneNode(true)));
      tooltip.querySelectorAll("[id]").forEach(element => element.removeAttribute("id"));
    } else tooltip.textContent = text;
    const show = () => {
      if (!active?.isConnected) { hide(); return; }
      active.setAttribute("aria-describedby", tooltip.id);
      tooltip.hidden = false;
      if (tooltip.showPopover) tooltip.showPopover();
      position();
    };
    if (event.type === "focusin") show();
    else showTimer = setTimeout(show, 180);
  };
  const leave = event => {
    const next = event.relatedTarget;
    if (next instanceof Node && (active?.contains(next) || tooltip.contains(next))) return;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 120);
  };
  root.addEventListener("pointerover", enter, options);
  root.addEventListener("focusin", enter, options);
  root.addEventListener("pointerout", leave, options);
  root.addEventListener("focusout", leave, options);
  root.addEventListener("keydown", event => {
    if (event.key === "Escape" && active) {
      hide();
      event.preventDefault();
      event.stopPropagation();
    }
  }, options);
  root.addEventListener("click", hide, options);
  root.addEventListener("scroll", event => { if (!tooltip.contains(event.target)) hide(); }, options);
  window.addEventListener("resize", hide, options);
  window.addEventListener("scroll", event => { if (!event.composedPath().includes(tooltip)) hide(); }, options);
  const observer = new MutationObserver(() => { if (active && !active.isConnected) hide(); });
  observer.observe(root, {childList: true, subtree: true});
  return () => { hide(); controller.abort(); observer.disconnect(); tooltip.remove(); };
}
