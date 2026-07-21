(() => {
  "use strict";

  const TAG = "deck-stage";

  class DeckStage extends HTMLElement {
    static get observedAttributes() {
      return ["noscale"];
    }

    connectedCallback() {
      this.width = Number(this.getAttribute("width")) || 1920;
      this.height = Number(this.getAttribute("height")) || 1080;
      this.tabIndex = 0;
      this.style.cssText += [
        "display:block",
        "position:fixed",
        "left:0",
        "top:0",
        `width:${this.width}px`,
        `height:${this.height}px`,
        "transform-origin:top left",
        "overflow:hidden",
      ].join(";") + ";";

      this.slides = Array.from(this.children).filter((node) => node.nodeType === Node.ELEMENT_NODE);
      this.slides.forEach((slide) => {
        slide.style.position = "absolute";
        slide.style.inset = "0";
        slide.style.margin = "0";
      });
      this.index = 0;
      this.goTo(0);

      this.onResize = () => this.fit();
      this.onKeydown = (event) => {
        if (event.key === "ArrowRight" || event.key === "PageDown") this.goTo(this.index + 1);
        if (event.key === "ArrowLeft" || event.key === "PageUp") this.goTo(this.index - 1);
      };
      window.addEventListener("resize", this.onResize);
      this.addEventListener("keydown", this.onKeydown);
      this.fit();
    }

    disconnectedCallback() {
      window.removeEventListener("resize", this.onResize);
      this.removeEventListener("keydown", this.onKeydown);
    }

    attributeChangedCallback() {
      this.fit();
    }

    goTo(index) {
      if (!this.slides?.length) return;
      this.index = Math.max(0, Math.min(index, this.slides.length - 1));
      this.slides.forEach((slide, position) => {
        const active = position === this.index;
        slide.hidden = !active;
        slide.toggleAttribute("data-deck-active", active);
      });
      this.dispatchEvent(new CustomEvent("deck-slide-change", {
        detail: { index: this.index, total: this.slides.length },
      }));
    }

    fit() {
      if (!this.isConnected) return;
      const scale = this.hasAttribute("noscale")
        ? 1
        : Math.min(window.innerWidth / this.width, window.innerHeight / this.height);
      const left = this.hasAttribute("noscale") ? 0 : (window.innerWidth - this.width * scale) / 2;
      const top = this.hasAttribute("noscale") ? 0 : (window.innerHeight - this.height * scale) / 2;
      this.style.transform = `translate(${Math.max(0, left)}px, ${Math.max(0, top)}px) scale(${scale})`;
    }
  }

  if (!customElements.get(TAG)) customElements.define(TAG, DeckStage);
})();
