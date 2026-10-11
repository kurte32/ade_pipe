/** Client-side photo compression (TDD 9.1): resize and re-encode to JPEG under the size cap. */

export const PHOTO_MAX_BYTES = 1_500_000;
const MAX_EDGE = 1600;

async function loadImage(blob: Blob): Promise<ImageBitmap | HTMLImageElement> {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(blob);
    } catch {
      /* fall through */
    }
  }
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("No se pudo leer la imagen"));
    };
    img.src = url;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("No se pudo codificar la imagen"))), "image/jpeg", quality);
  });
}

export async function compressPhoto(file: Blob, maxBytes = PHOTO_MAX_BYTES): Promise<Blob> {
  if (file.type === "image/jpeg" && file.size <= maxBytes) return file;
  const img = await loadImage(file);
  const w = "width" in img ? img.width : 0;
  const h = "height" in img ? img.height : 0;
  let scale = Math.min(1, MAX_EDGE / Math.max(w, h));
  for (let attempt = 0; attempt < 6; attempt++) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas no disponible");
    ctx.drawImage(img as CanvasImageSource, 0, 0, canvas.width, canvas.height);
    const quality = Math.max(0.5, 0.85 - attempt * 0.1);
    const blob = await canvasToBlob(canvas, quality);
    if (blob.size <= maxBytes) return blob;
    scale *= 0.75;
  }
  throw new Error("La foto es demasiado grande incluso después de comprimirla");
}
