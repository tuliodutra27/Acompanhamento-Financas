/**
 * Entrada de uma nota: escanear o QR Code ou colar a chave.
 *
 * A tela é explícita sobre a diferença entre os dois caminhos, porque ela é real e
 * afeta o esforço do usuário: escaneando o QR Code, o app tenta buscar os itens
 * sozinho (a URL do QR carrega o hash assinado da nota); com a chave digitada, a
 * consulta passaria pelo formulário da SEFAZ, que tem reCAPTCHA — então vai direto
 * para o preenchimento manual. Melhor dizer isso antes do que decepcionar depois.
 */

import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FalhaApi, api } from "../api/client";
import { useScannerQR } from "../hooks/useScannerQR";
import { lerQrDeImagem } from "../lib/lerQrDeImagem";
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
  const [lendoFoto, setLendoFoto] = useState(false);
  const [avisoFoto, setAvisoFoto] = useState<string | null>(null);
  const inputFotoRef = useRef<HTMLInputElement | null>(null);

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

  const aoEscolherFoto = useCallback(
    async (arquivo: File | undefined) => {
      if (!arquivo) return;
      setLendoFoto(true);
      setErro(null);
      setAvisoFoto(null);
      try {
        const { texto, tentativa, resolucao } = await lerQrDeImagem(arquivo);
        setAvisoFoto(`QR Code lido da foto (${resolucao}, ${tentativa}).`);
        await enviar(texto, "qrcode");
      } catch (causa) {
        setErro(
          causa instanceof Error
            ? causa.message
            : "Não foi possível ler o QR Code desta foto.",
        );
      } finally {
        setLendoFoto(false);
        if (inputFotoRef.current) inputFotoRef.current.value = "";
      }
    },
    [enviar],
  );

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

      {avisoFoto && (
        <div className="aviso ok">
          <span className="icone" aria-hidden="true">
            ✅
          </span>
          <span>{avisoFoto}</span>
        </div>
      )}

      {/* Caminho por foto primeiro: quem tira a foto é o app de câmera do telefone,
          com autofoco e todo o processamento do fabricante. Para um QR pequeno em
          papel térmico isso lê muito melhor que o vídeo ao vivo no navegador. */}
      <section className="cartao">
        <h2>Fotografar o QR Code</h2>
        <p className="legenda">
          Abre a câmera do seu celular. Tire a foto com o QR Code preenchendo boa parte
          do quadro — é a forma mais confiável de leitura.
        </p>
        <input
          ref={inputFotoRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          onChange={(evento) => void aoEscolherFoto(evento.target.files?.[0])}
        />
        <button
          className="primario"
          disabled={lendoFoto || enviando}
          onClick={() => inputFotoRef.current?.click()}
        >
          {lendoFoto ? "Lendo a foto…" : "📸 Tirar foto do QR Code"}
        </button>
      </section>

      <section className="cartao">
        <h2>Ou escanear ao vivo pela câmera</h2>
        <p className="legenda">
          Leitura contínua pelo navegador. Mais rápida quando funciona, porém mais
          sensível a foco e iluminação que a foto.
        </p>

        {/* O <video> fica SEMPRE montado, apenas oculto quando a câmera está parada.
            Isto não é detalhe de estilo: renderizá-lo condicionalmente fazia
            `videoRef.current` ser nulo no momento de anexar o stream, porque o React
            só re-renderiza depois que o handler do clique termina. Era a causa real de
            o scanner ao vivo nunca iniciar. */}
        <div
          className="visor"
          hidden={scanner.estado !== "lendo" && scanner.estado !== "iniciando"}
        >
          <video ref={scanner.videoRef} muted playsInline autoPlay />
          <div className="mira" />
          <div className="botoes-camera">
            {scanner.temLanterna && (
              <button
                onClick={() => void scanner.alternarLanterna()}
                aria-pressed={scanner.lanternaLigada}
                title="Lanterna"
              >
                {scanner.lanternaLigada ? "🔆" : "🔅"}
              </button>
            )}
            <button onClick={scanner.parar} title="Fechar a câmera">
              ✕
            </button>
          </div>
          <div className="dica">
            {scanner.estado === "iniciando"
              ? "Abrindo a câmera…"
              : "Encaixe o QR Code do cupom dentro do quadro"}
          </div>
        </div>

        {scanner.estado === "lendo" || scanner.estado === "iniciando" ? (
          <>
            {enviando && (
              <p className="secundario" style={{ marginTop: "0.6rem" }}>
                Lido! Registrando a nota…
              </p>
            )}

            {/* Diagnóstico à vista: se "tentativas" sobe, a câmera entrega frames e o
                decodificador roda — o problema é enquadramento/foco. Se fica em 0, o
                problema é a captura. Sem isso, "não lê" não diz qual dos dois é. */}
            <p
              className="secundario"
              style={{ marginTop: "0.6rem", fontSize: "0.75rem" }}
            >
              leituras tentadas: {scanner.diagnostico.tentativas}
              {scanner.diagnostico.resolucao
                ? ` · câmera ${scanner.diagnostico.resolucao}`
                : " · aguardando resolução"}
              {scanner.diagnostico.ultimoErroFrame
                ? ` · último erro: ${scanner.diagnostico.ultimoErroFrame}`
                : ""}
            </p>
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

      {/* O caminho que de fato traz os itens preenchidos. Fica em destaque porque a
          consulta feita pelo servidor é recusada pelo portal, enquanto o navegador do
          usuário abre a nota normalmente. */}
      <section className="cartao">
        <h2>Importar os itens automaticamente</h2>
        <p className="legenda">
          O servidor não consegue abrir o portal da SEFAZ, mas o seu navegador consegue.
          Com um atalho instalado uma vez, você abre a nota no portal e os itens vêm
          preenchidos — sem digitar produto por produto.
        </p>
        <Link className="botao" to="/importar">
          ⚙️ Configurar o atalho de importação
        </Link>
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

      {/* Selo de build: responde na hora se o celular está com a versão nova ou se o
          service worker ainda serve a antiga — dúvida que já custou diagnóstico. */}
      <p
        className="secundario"
        style={{ textAlign: "center", fontSize: "0.72rem", marginTop: "-0.4rem" }}
      >
        versão {__BUILD_ID__} · leitor ZXing
      </p>
    </>
  );
}
