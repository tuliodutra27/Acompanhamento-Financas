/**
 * Scanner de QR Code pela câmera, com ZXing (a biblioteca de leitura de códigos do
 * Google, na porta JS `@zxing/browser`).
 *
 * **Por que ZXing e não a `BarcodeDetector` do navegador.** A primeira versão usava a
 * API nativa com o ponyfill `barcode-detector` como reserva — e falhava em silêncio: o
 * ponyfill baixa o decodificador WASM de um CDN em tempo de execução, e quando esse
 * download não acontece, cada frame lança exceção. A câmera abria e nada era lido.
 * ZXing é JavaScript puro, entra no bundle e não depende de rede nenhuma depois que o
 * app carregou — o que importa num app que roda atrás de Tailscale e é usado dentro de
 * supermercado, onde o sinal é ruim.
 *
 * Duas lições daquela falha estão codificadas aqui:
 *
 * - **Erro de frame e erro fatal são coisas diferentes.** "Não achei código neste
 *   frame" acontece 20 vezes por segundo e é normal; "o decodificador não carregou" ou
 *   "a câmera foi negada" precisa aparecer na tela. Por isso o erro fatal vem da
 *   rejeição da promessa, e os erros por frame são ignorados no callback.
 * - **QR Code de cupom fiscal é um caso difícil**: impresso pequeno, em papel térmico,
 *   com pouco contraste e às vezes já apagando. Daí `TRY_HARDER` ligado e a lanterna
 *   exposta na interface.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserQRCodeReader, type IScannerControls } from "@zxing/browser";
import { DecodeHintType } from "@zxing/library";

type EstadoScanner = "inativo" | "iniciando" | "lendo" | "erro";

export function useScannerQR(onLeitura: (conteudo: string) => void) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const controlesRef = useRef<IScannerControls | null>(null);
  const jaLeuRef = useRef(false);
  const [estado, setEstado] = useState<EstadoScanner>("inativo");
  const [erro, setErro] = useState<string | null>(null);
  const [temLanterna, setTemLanterna] = useState(false);
  const [lanternaLigada, setLanternaLigada] = useState(false);

  const parar = useCallback(() => {
    controlesRef.current?.stop();
    controlesRef.current = null;
    setLanternaLigada(false);
    setTemLanterna(false);
    setEstado("inativo");
  }, []);

  const iniciar = useCallback(async () => {
    setErro(null);
    setEstado("iniciando");
    jaLeuRef.current = false;

    if (!window.isSecureContext) {
      setEstado("erro");
      setErro(
        "A câmera exige HTTPS. Acesse o app pelo endereço seguro — ou use a chave " +
          "digitada abaixo.",
      );
      return;
    }

    try {
      const hints = new Map();
      // Papel térmico com QR pequeno e desbotado: vale o custo extra de CPU.
      hints.set(DecodeHintType.TRY_HARDER, true);

      const leitor = new BrowserQRCodeReader(hints, {
        // ~7 tentativas por segundo. Mais que isso só esquenta o telefone: a mão
        // demora mais que isso para estabilizar o enquadramento.
        delayBetweenScanAttempts: 140,
        delayBetweenScanSuccess: 500,
      });

      const video = videoRef.current;
      if (!video) throw new Error("elemento de vídeo não montado");

      const controles = await leitor.decodeFromConstraints(
        {
          video: {
            facingMode: { ideal: "environment" },
            // Resolução maior ajuda o decodificador a resolver os módulos do QR;
            // `ideal` deixa o navegador cair para o que o aparelho tiver.
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        },
        video,
        (resultado) => {
          // Erros aqui são por frame ("nada encontrado") e não interessam.
          if (!resultado || jaLeuRef.current) return;
          jaLeuRef.current = true;
          onLeitura(resultado.getText());
          parar();
        },
      );

      controlesRef.current = controles;
      setTemLanterna(typeof controles.switchTorch === "function");
      setEstado("lendo");
    } catch (causa) {
      // Só chega aqui o que é fatal: permissão negada, sem câmera, decodificador
      // não carregou. Isso precisa ser visível — foi justamente o que a versão
      // anterior escondia.
      setEstado("erro");
      const nome = causa instanceof DOMException ? causa.name : "";
      setErro(
        nome === "NotAllowedError"
          ? "Permissão de câmera negada. Autorize nas configurações do navegador, ou use a chave digitada abaixo."
          : nome === "NotFoundError" || nome === "OverconstrainedError"
            ? "Nenhuma câmera compatível foi encontrada neste aparelho."
            : `Não foi possível iniciar a câmera${
                causa instanceof Error ? `: ${causa.message}` : ""
              }. Use a chave digitada abaixo.`,
      );
    }
  }, [onLeitura, parar]);

  const alternarLanterna = useCallback(async () => {
    const controles = controlesRef.current;
    if (!controles?.switchTorch) return;
    try {
      await controles.switchTorch(!lanternaLigada);
      setLanternaLigada((ligada) => !ligada);
    } catch {
      // Alguns aparelhos anunciam a lanterna e recusam ligá-la; não é fatal.
      setTemLanterna(false);
    }
  }, [lanternaLigada]);

  useEffect(() => parar, [parar]);

  return {
    videoRef,
    estado,
    erro,
    iniciar,
    parar,
    temLanterna,
    lanternaLigada,
    alternarLanterna,
  };
}
