/**
 * Entrada de uma nota: escanear o QR Code ou colar a chave.
 *
 * A tela é explícita sobre a diferença entre os dois caminhos, porque ela é real e
 * afeta o esforço do usuário: escaneando o QR Code, o app tenta buscar os itens
 * sozinho (a URL do QR carrega o hash assinado da nota); com a chave digitada, a
 * consulta passaria pelo formulário da SEFAZ, que tem reCAPTCHA — então vai direto
 * para o preenchimento manual. Melhor dizer isso antes do que decepcionar depois.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FalhaApi, api } from "../api/client";
import { useScannerQR } from "../hooks/useScannerQR";
import {
  MENSAGEM_MOTIVO,
  anoMesLegivel,
  extrairChaveDoQrCode,
  lerChave,
  limparChave,
} from "../lib/chaveNfce";

export function AdicionarNota() {
  const navegar = useNavigate();
  const [chaveDigitada, setChaveDigitada] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const enviar = useCallback(
    async (conteudo: string, origem: "qrcode" | "chave_manual") => {
      setEnviando(true);
      setErro(null);
      try {
        const nota = await api.criarNota(conteudo, origem);
        navegar(`/notas/${nota.id}`);
      } catch (causa) {
        setErro(
          causa instanceof FalhaApi
            ? causa.erro.mensagem
            : "Não foi possível registrar a nota. Verifique a conexão.",
        );
      } finally {
        setEnviando(false);
      }
    },
    [navegar],
  );

  const aoLerQrCode = useCallback(
    (conteudo: string) => {
      const chave = extrairChaveDoQrCode(conteudo);
      if (!chave) {
        setErro("O QR Code lido não parece ser de uma nota fiscal.");
        return;
      }
      // Envia o conteúdo completo, não só a chave: é a URL que habilita a consulta.
      void enviar(conteudo, "qrcode");
    },
    [enviar],
  );

  const scanner = useScannerQR(aoLerQrCode);

  const digitada = limparChave(chaveDigitada);
  const analise = digitada.length === 44 ? lerChave(digitada) : null;

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>Nova nota</h1>

      {erro && (
        <div className="aviso erro">
          <span className="icone" aria-hidden="true">
            ⚠️
          </span>
          <span>{erro}</span>
        </div>
      )}

      <section className="cartao">
        <h2>Escanear o QR Code do cupom</h2>
        <p className="legenda">
          É o caminho que permite preencher os itens automaticamente — a URL do QR Code
          abre a nota direto no portal da SEFAZ.
        </p>

        {scanner.estado === "lendo" || scanner.estado === "iniciando" ? (
          <>
            <div className="visor">
              <video ref={scanner.videoRef} muted playsInline />
              <div className="mira" />
            </div>
            <div className="acoes">
              <button onClick={scanner.parar}>Parar câmera</button>
              <span className="secundario" style={{ alignSelf: "center" }}>
                {scanner.estado === "iniciando"
                  ? "Abrindo a câmera…"
                  : "Aponte para o QR Code do cupom."}
              </span>
            </div>
          </>
        ) : (
          <button className="primario" onClick={() => void scanner.iniciar()} disabled={enviando}>
            📷 Abrir a câmera
          </button>
        )}

        {scanner.erro && (
          <div className="aviso atencao" style={{ marginTop: "0.8rem" }}>
            <span className="icone" aria-hidden="true">
              ℹ️
            </span>
            <span>{scanner.erro}</span>
          </div>
        )}
      </section>

      <section className="cartao">
        <h2>Ou digitar a chave de acesso</h2>
        <p className="legenda">
          Os 44 dígitos impressos no cupom. Por aqui os itens são preenchidos à mão: a
          consulta por chave no site da SEFAZ é protegida por reCAPTCHA.
        </p>

        <div className="campo">
          <label htmlFor="chave">Chave de acesso</label>
          <input
            id="chave"
            inputMode="numeric"
            autoComplete="off"
            placeholder="0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000"
            value={chaveDigitada}
            onChange={(evento) => setChaveDigitada(evento.target.value)}
          />
          <p className="secundario" style={{ margin: "0.35rem 0 0" }}>
            {digitada.length}/44 dígitos
          </p>
        </div>

        {/* Validação local, antes de qualquer requisição: erro de digitação aparece
            na hora, e a UF/mês da compra já saem da própria chave. */}
        {analise?.valida && (
          <div className="aviso ok">
            <span className="icone" aria-hidden="true">
              ✅
            </span>
            <span>
              Chave válida — <strong>{analise.dados.uf}</strong>, compra de{" "}
              {anoMesLegivel(analise.dados.anoMes)}.
            </span>
          </div>
        )}
        {analise && !analise.valida && (
          <div className="aviso erro">
            <span className="icone" aria-hidden="true">
              ⚠️
            </span>
            <span>{MENSAGEM_MOTIVO[analise.motivo]}</span>
          </div>
        )}

        <button
          className="primario"
          disabled={!analise?.valida || enviando}
          onClick={() => void enviar(digitada, "chave_manual")}
        >
          {enviando ? "Registrando…" : "Registrar nota"}
        </button>
      </section>
    </>
  );
}
