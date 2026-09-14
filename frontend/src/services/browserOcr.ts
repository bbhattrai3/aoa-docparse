import { createWorker } from "tesseract.js";
import * as pdfjsLib from "pdfjs-dist";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const PAGE_BREAK = "\n\n--- PAGE BREAK ---\n\n";

type ProgressCallback = (progress: number) => void;

async function getEmbeddedPageText(page: pdfjsLib.PDFPageProxy): Promise<string> {
  const content = await page.getTextContent();
  return content.items
    .filter((item): item is typeof item & { str: string } => "str" in item)
    .map((item) => item.str)
    .join(" ")
    .trim();
}

export async function extractUtilityText(
  file: File,
  onProgress?: ProgressCallback,
): Promise<string> {
  const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
  const pageTexts: string[] = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    pageTexts.push(await getEmbeddedPageText(await pdf.getPage(pageNumber)));
  }

  const embeddedText = pageTexts.join(" ").trim();
  if (embeddedText.length > 50) {
    onProgress?.(100);
    return pageTexts.join(PAGE_BREAK);
  }

  const worker = await createWorker("eng", undefined, {
    logger: (message) => {
      const pageProgress = (message.progress || 0) * 100;
      onProgress?.(Math.round(((message.status === "recognizing text" ? pageProgress : 0) / pdf.numPages)));
    },
  });

  try {
    const ocrPages: string[] = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 2 });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvas, viewport }).promise;
      const result = await worker.recognize(canvas);
      ocrPages.push(result.data.text.trim());
      onProgress?.(Math.round((pageNumber / pdf.numPages) * 100));
    }
    return ocrPages.join(PAGE_BREAK);
  } finally {
    await worker.terminate();
  }
}
