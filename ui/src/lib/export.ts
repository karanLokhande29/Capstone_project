// PNG / SVG export for charts (slides) and Markdown export for lists. CSS variables are resolved to the current theme's colours.

function inlineVars(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const cs = getComputedStyle(document.documentElement);
  const bg = cs.getPropertyValue("--panel").trim() || "#ffffff";
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  let text = new XMLSerializer().serializeToString(clone);
  text = text.replace(/var\((--[a-z0-9-]+)\)/gi, (_, v: string) => cs.getPropertyValue(v).trim() || "#888");
  const vb = svg.viewBox.baseVal;
  const w = vb && vb.width ? vb.width : svg.clientWidth;
  const h = vb && vb.height ? vb.height : svg.clientHeight;
  return text.replace(/^<svg([^>]*)>/, `<svg$1><rect width="${w}" height="${h}" fill="${bg}"/>`);
}

function save(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function exportSvg(svg: SVGSVGElement | null, name: string) {
  if (!svg) return;
  if (import.meta.env.VITE_ARTIFACT === "1") {
    navigator.clipboard?.writeText(inlineVars(svg)).catch(() => undefined); // hosted viewers block downloads
    return;
  }
  save(new Blob([inlineVars(svg)], { type: "image/svg+xml" }), `${name}.svg`);
}

export function exportPng(svg: SVGSVGElement | null, name: string, scale = 2) {
  if (!svg) return;
  const src = inlineVars(svg);
  const vb = svg.viewBox.baseVal;
  const w = (vb && vb.width) || svg.clientWidth;
  const h = (vb && vb.height) || svg.clientHeight;
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = w * scale;
    c.height = h * scale;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    c.toBlob((b) => b && save(b, `${name}.png`), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(src);
}
