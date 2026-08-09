/**
 * Lê o QR Code de uma **foto**, em vez do vídeo ao vivo.
 *
 * Por que este caminho existe e por que ele tende a funcionar melhor: com
 * `<input type="file" capture="environment">` quem tira a foto é o **app de câmera do
 * próprio telefone** — com autofoco, estabilização, HDR e todo o processamento que o
 * fabricante embutiu. O navegador só recebe um JPEG nítido e o ZXing decodifica uma
 * imagem parada, sem pressa. O vídeo ao vivo dentro do navegador não tem nada disso: o
 * frame chega cru, muitas vezes desfocado, e o decodificador tem milissegundos.
 *
 * Para QR Code de cupom fiscal — pequeno, em papel térmico, com pouco contraste — a
 * diferença é grande.
 */

import { BrowserQRCodeReader } from "@zxing/browser";
import { DecodeHintType } from "@zxing/library";

function leitor(): BrowserQRCodeReader {
  const hints = new Map();
  hints.set(DecodeHintType.TRY_HARDER, true);
  return new BrowserQRCodeReader(hints);
}

function carregarImagem(url: string): Promise<HTMLImageElement> {
  return new Promise((resolver, rejeitar) => {
    const imagem = new Image();
    imagem.onload = () => resolver(imagem);
    imagem.onerror = () => rejeitar(new Error("não foi possível abrir a imagem"));
    imagem.src = url;
  });
}

/** Recorta o centro da imagem e reescala — cobre a foto tirada de longe. */
function recortarCentro(
  imagem: HTMLImageElement,
  proporcao: number,
  larguraMaxima = 1400,
): HTMLCanvasElement {
  const larguraFonte = imagem.naturalWidth * proporcao;
  const alturaFonte = imagem.naturalHeight * proporcao;
  const x = (imagem.naturalWidth - larguraFonte) / 2;
  const y = (imagem.naturalHeight - alturaFonte) / 2;

  const escala = Math.min(1, larguraMaxima / larguraFonte);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(larguraFonte * escala);
  canvas.height = Math.round(alturaFonte * escala);

  const contexto = canvas.getContext("2d");
  if (!contexto) throw new Error("canvas indisponível");
  contexto.drawImage(
    imagem,
    x, y, larguraFonte, alturaFonte,
    0, 0, canvas.width, canvas.height,
  );
  return canvas;
}

export interface ResultadoLeituraImagem {
  texto: string;
  /** Qual tentativa funcionou — útil para saber se vale orientar o enquadramento. */
  tentativa: string;
  resolucao: string;
}

/**
 * Tenta decodificar em três passadas, da mais provável para a mais agressiva.
 *
 * Uma passada só não basta na prática: a foto inteira falha quando o QR ficou pequeno
 * no enquadramento, e o recorte falha quando o QR está deslocado do centro. Três
 * tentativas ainda são instantâneas numa imagem já em memória.
 */
export async function lerQrDeImagem(
  arquivo: File,
): Promise<ResultadoLeituraImagem> {
  const url = URL.createObjectURL(arquivo);

  try {
    const imagem = await carregarImagem(url);
    const resolucao = `${imagem.naturalWidth}×${imagem.naturalHeight}`;

    // 1. Imagem inteira, como veio da câmera.
    try {
      const resultado = await leitor().decodeFromImageElement(imagem);
      return { texto: resultado.getText(), tentativa: "imagem inteira", resolucao };
    } catch {
      /* segue para o recorte */
    }

    // 2. Centro a 60% — o caso de ter fotografado o cupom todo, de longe.
    for (const proporcao of [0.6, 0.35]) {
      try {
        const canvas = recortarCentro(imagem, proporcao);
        const resultado = await leitor().decodeFromCanvas(canvas);
        return {
          texto: resultado.getText(),
          tentativa: `recorte central ${Math.round(proporcao * 100)}%`,
          resolucao,
        };
      } catch {
        /* tenta o próximo recorte */
      }
    }

    throw new Error(
      `Não encontrei um QR Code legível nesta foto (${resolucao}). ` +
        "Tente de novo mais perto, com o QR Code preenchendo boa parte do quadro, " +
        "e com boa luz.",
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}
