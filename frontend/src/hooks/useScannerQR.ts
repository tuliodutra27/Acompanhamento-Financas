/**
 * Scanner de QR Code pela câmera do navegador.
 *
 * Usa a `BarcodeDetector` nativa quando existe (Chrome/Edge/Android) e o ponyfill
 * `barcode-detector` (WASM/ZXing) quando não existe — o caso do Safari/iOS. O código
 * do app chama uma interface só.
 *
 * Escanear é o caminho que importa: só a URL do QR Code carrega o hash assinado que
 * abre a nota direto no portal da SEFAZ. Chave digitada não permite consulta
 * automática (o formulário por chave tem reCAPTCHA).
 */

import { useCallback, useEffect, useRef, useState } from "react";

type EstadoScanner = "inativo" | "iniciando" | "lendo" | "erro";

interface DetectorDeCodigo {
  detect(fonte: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

async function criarDetector(): Promise<DetectorDeCodigo> {
  const nativo = (
    window as unknown as {
      BarcodeDetector?: new (opcoes: { formats: string[] }) => DetectorDeCodigo;
    }
  ).BarcodeDetector;

  if (nativo) return new nativo({ formats: ["qr_code"] });

  const { BarcodeDetector } = await import("barcode-detector/ponyfill");
  return new BarcodeDetector({ formats: ["qr_code"] }) as DetectorDeCodigo;
}

export function useScannerQR(onLeitura: (conteudo: string) => void) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const loopRef = useRef<number | null>(null);
  const [estado, setEstado] = useState<EstadoScanner>("inativo");
  const [erro, setErro] = useState<string | null>(null);

  const parar = useCallback(() => {
    if (loopRef.current !== null) {
      cancelAnimationFrame(loopRef.current);
      loopRef.current = null;
    }
    streamRef.current?.getTracks().forEach((trilha) => trilha.stop());
    streamRef.current = null;
    setEstado("inativo");
  }, []);

  const iniciar = useCallback(async () => {
    setErro(null);
    setEstado("iniciando");

    try {
      const detector = await criarDetector();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;

      const video = videoRef.current;
      if (!video) throw new Error("Elemento de vídeo não montado.");

      video.srcObject = stream;
      await video.play();
      setEstado("lendo");

      let encerrado = false;
      const procurar = async () => {
        if (encerrado || !videoRef.current) return;
        try {
          const codigos = await detector.detect(videoRef.current);
          if (codigos.length > 0 && codigos[0].rawValue) {
            encerrado = true;
            onLeitura(codigos[0].rawValue);
            parar();
            return;
          }
        } catch {
          // Um frame ilegível é normal (desfoque, movimento) — só tenta o próximo.
        }
        loopRef.current = requestAnimationFrame(() => void procurar());
      };
      loopRef.current = requestAnimationFrame(() => void procurar());
    } catch (causa) {
      setEstado("erro");
      const mensagem =
        causa instanceof DOMException && causa.name === "NotAllowedError"
          ? "Permissão de câmera negada. Você ainda pode digitar a chave abaixo."
          : !window.isSecureContext
            ? "A câmera exige HTTPS. Acesse pelo endereço seguro do app."
            : "Não foi possível abrir a câmera. Use a chave digitada abaixo.";
      setErro(mensagem);
    }
  }, [onLeitura, parar]);

  useEffect(() => parar, [parar]);

  return { videoRef, estado, erro, iniciar, parar };
}
