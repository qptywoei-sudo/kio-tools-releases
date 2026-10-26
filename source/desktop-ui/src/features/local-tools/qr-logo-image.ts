export type QrLogoAsset = { dataUrl: string; name: string; width: number; height: number };

const MAX_LOGO_BYTES = 5 * 1024 * 1024, MAX_LOGO_PIXELS = 16_000_000;
const svgTags = new Set(["svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "clipPath", "linearGradient", "radialGradient", "stop", "use", "title", "desc"]);
const svgAttributes = new Set(["xmlns", "xmlns:xlink", "version", "viewBox", "width", "height", "x", "y", "cx", "cy", "r", "rx", "ry", "x1", "x2", "y1", "y2", "dx", "dy", "d", "points", "id", "fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity", "transform", "gradientTransform", "gradientUnits", "spreadMethod", "offset", "stop-color", "stop-opacity", "clip-path", "clip-rule", "clipPathUnits", "preserveAspectRatio", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "href", "xlink:href", "style", "color", "vector-effect"]);
const svgStyleProperties = new Set(["fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity", "stop-color", "stop-opacity", "clip-path", "clip-rule", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "color", "vector-effect"]);

// Do not inject user SVG markup into the page. Parse an allowlisted subset,
// reject active/external content, then rasterize it as an isolated image.
export function sanitizeQrLogoSvg(source: string): string {
  if (/<!DOCTYPE|<!ENTITY|<\?/i.test(source.replace(/^\s*<\?xml[^>]*\?>/i, ""))) throw Error("로고 SVG에 외부 참조 또는 실행 코드가 포함되어 있습니다. PNG로 저장해 다시 선택하세요.");
  const document = new DOMParser().parseFromString(source, "image/svg+xml");
  const root = document.documentElement;
  if (document.querySelector("parsererror") || root.localName !== "svg" || root.namespaceURI !== "http://www.w3.org/2000/svg") throw Error("SVG 로고 파일을 읽을 수 없습니다.");
  const elements = [root, ...root.querySelectorAll("*")];
  if (elements.length > 10_000) throw Error("SVG 로고가 너무 복잡합니다. PNG로 저장해 다시 선택하세요.");
  for (const element of elements) {
    if (element.namespaceURI !== root.namespaceURI || !svgTags.has(element.localName)) throw Error("지원하지 않는 SVG 요소가 있습니다. PNG로 저장해 다시 선택하세요.");
    for (const attribute of [...element.attributes]) {
      const { name, value } = attribute;
      if (name.startsWith("data-") || name.startsWith("aria-") || name === "role" || name === "class") { element.removeAttribute(name); continue; }
      if (!svgAttributes.has(name) || /^on/i.test(name) || /[\\\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value) || /@|\/\*/.test(value)) throw Error("로고 SVG에 안전하지 않은 속성이 있습니다. PNG로 저장해 다시 선택하세요.");
      if (name === "xmlns" && value !== root.namespaceURI || name === "xmlns:xlink" && value !== "http://www.w3.org/1999/xlink") throw Error("SVG 로고 파일 형식이 올바르지 않습니다.");
      if (name === "xmlns" || name === "xmlns:xlink") continue;
      if (name === "style") for (const declaration of value.split(";").filter(part => part.trim())) {
        const colon = declaration.indexOf(":");
        if (colon < 1 || !svgStyleProperties.has(declaration.slice(0, colon).trim().toLowerCase())) throw Error("SVG 로고의 스타일을 지원하지 않습니다. PNG로 저장해 다시 선택하세요.");
      }
      if (name === "href" || name === "xlink:href") {
        if (!/^#[A-Za-z_][\w:.-]*$/.test(value)) throw Error("SVG 로고의 외부 이미지와 링크는 사용할 수 없습니다.");
      }
      const withoutLocalUrls = value.replace(/url\(\s*['"]?#[A-Za-z_][\w:.-]*['"]?\s*\)/gi, "");
      if (/url\s*\(|(?:https?|file|data|javascript):|expression\s*\(/i.test(withoutLocalUrls)) throw Error("SVG 로고의 외부 이미지와 링크는 사용할 수 없습니다.");
    }
  }
  return new XMLSerializer().serializeToString(root);
}
export function loadImage(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob), image = new Image();
    const finish = () => { clearTimeout(timer); URL.revokeObjectURL(url); image.onload = null; image.onerror = null; };
    const timer = setTimeout(() => { finish(); reject(Error("이미지를 읽는 데 시간이 초과되었습니다.")); }, 15_000);
    image.onload = () => { finish(); resolve(image); };
    image.onerror = () => { finish(); reject(Error("이미지 파일을 읽을 수 없습니다.")); };
    image.src = url;
  });
}
export function canvasFor(width: number, height = width): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw Error("canvas_unavailable");
  return [canvas, context];
}
export async function loadQrLogo(file: File): Promise<QrLogoAsset> {
  if (!file.size || file.size > MAX_LOGO_BYTES) throw Error("로고는 5MB 이하의 PNG, JPG, SVG 파일을 선택하세요.");
  const bytes = new Uint8Array(await file.arrayBuffer()), start = bytes.subarray(0, 16);
  const png = start[0] === 137 && start[1] === 80 && start[2] === 78 && start[3] === 71 && start[4] === 13 && start[5] === 10 && start[6] === 26 && start[7] === 10;
  const jpeg = start[0] === 255 && start[1] === 216 && start[2] === 255;
  let blob: Blob;
  if (png || jpeg) blob = new Blob([bytes], { type: png ? "image/png" : "image/jpeg" });
  else if (file.type === "image/svg+xml" || /\.svg$/i.test(file.name)) blob = new Blob([sanitizeQrLogoSvg(new TextDecoder().decode(bytes))], { type: "image/svg+xml" });
  else throw Error("로고는 PNG, JPG, SVG 파일만 사용할 수 있습니다.");
  const image = await loadImage(blob), { naturalWidth: width, naturalHeight: height } = image;
  if (!width || !height || width > 8192 || height > 8192 || width * height > MAX_LOGO_PIXELS) throw Error("로고 이미지가 너무 큽니다. 1600만 화소 이하로 줄여 주세요.");
  const scale = Math.min(1, 1024 / Math.max(width, height));
  const [canvas, context] = canvasFor(Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale)));
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return { dataUrl: canvas.toDataURL("image/png"), name: file.name, width: canvas.width, height: canvas.height };
}
