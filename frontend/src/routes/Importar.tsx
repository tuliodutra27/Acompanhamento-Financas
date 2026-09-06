/**
 * Tela do atalho de importação (bookmarklet).
 *
 * O portal da SEFAZ recusa a consulta feita pelo servidor, mas abre normalmente no
 * navegador do usuário. Então a extração automática acontece lá: o atalho lê o HTML da
 * nota já aberta e o envia para a API. Nenhum contorno de proteção — é o navegador que
 * já tem acesso legítimo à página fazendo a leitura.
 *
 * O atalho carrega um **token** na URL porque roda a partir do domínio da SEFAZ, e o
 * cookie de sessão (`SameSite=Lax`) não é enviado num POST entre sites. O token vale só
 * para a rota de importação — ver backend/app/core/auth.py.
 */

import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

function montarBookmarklet(base: string, token: string): string {
  // Envia por <form target="_blank">, não por fetch. Um `fetch` para outro domínio
  // exige que a resposta traga Access-Control-Allow-Origin, senão a promessa rejeita
  // com "Failed to fetch" — mesmo tendo a requisição chegado e sido processada
  // (aconteceu na primeira versão). O envio por formulário é uma **navegação**: CORS
  // não se aplica, e o resultado aparece numa aba nova.
  const codigo = `
    (function(){
      try {
        var html = document.documentElement.outerHTML;
        var f = document.createElement('form');
        f.method = 'POST';
        f.action = '${base}/api/v1/notas/importar-html?token=${token}&url=' + encodeURIComponent(location.href);
        f.target = '_blank';
        f.style.display = 'none';
        var t = document.createElement('textarea');
        t.name = 'html';
        t.value = html;
        f.appendChild(t);
        document.body.appendChild(f);
        f.submit();
        setTimeout(function(){ f.remove(); }, 2000);
      } catch (e) { alert('Erro no atalho: ' + e); }
    })();
  `;
  return "javascript:" + encodeURIComponent(codigo.replace(/\s+/g, " ").trim());
}

export function Importar() {
  const [copiado, setCopiado] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const base = window.location.origin;

  useEffect(() => {
    void api
      .tokenImportacao()
      .then(({ token }) => setToken(token))
      // App aberto (sem senha) devolve o token do mesmo jeito; se algo falhar, o atalho
      // sem token ainda funciona nesse caso, e é melhor que travar a tela.
      .catch(() => setToken(""));
  }, []);

  const bookmarklet = useMemo(
    () => (token === null ? "" : montarBookmarklet(base, token)),
    [base, token],
  );

  return (
    <>
      <h1 style={{ fontSize: "1.25rem", margin: "0.25rem 0 1rem" }}>
        Importar do portal da SEFAZ
      </h1>

      <div className="aviso atencao">
        <span className="icone" aria-hidden="true">
          ⚠️
        </span>
        <span>
          <strong>Tem um atalho antigo instalado? Substitua.</strong> Desde o login, o
          atalho precisa levar uma credencial na URL — e a versão anterior, além de não
          ter essa credencial, mandava os dados por <span className="mono">fetch</span> e
          descartava a resposta: ela falha <em>em silêncio</em>, sem alerta e sem
          importar a nota. Apague o favorito antigo e instale este.
        </span>
      </div>

      <div className="aviso">
        <span className="icone" aria-hidden="true">
          ℹ️
        </span>
        <span>
          O servidor não consegue abrir o portal da SEFAZ, mas o <strong>seu
          navegador</strong> consegue. Este atalho lê a nota que você já abriu e manda os
          itens para o app — sem digitar nada.
        </span>
      </div>

      <section className="cartao">
        <h2>1. Instalar o atalho</h2>
        <p className="legenda">
          <strong>No computador:</strong> mostre a barra de favoritos
          (<span className="mono">Ctrl+Shift+B</span>) e arraste o botão abaixo para
          ela.
        </p>
        <p style={{ margin: "0.5rem 0 0.9rem" }}>
          {/* Um <a> com href javascript: é o formato que o navegador aceita arrastar
              para a barra de favoritos. */}
          <a
            className="botao primario"
            href={bookmarklet || "#"}
            aria-disabled={!bookmarklet}
            style={bookmarklet ? undefined : { opacity: 0.55, pointerEvents: "none" }}
            onClick={(evento) => {
              evento.preventDefault();
              alert(
                "Não clique aqui: arraste este botão para a barra de favoritos. " +
                  "Depois, abra a nota no portal da SEFAZ e clique no favorito.",
              );
            }}
          >
            {bookmarklet ? "⬇️ Importar nota (arraste para os favoritos)" : "Carregando…"}
          </a>
        </p>
        <p className="legenda">
          <strong>No celular:</strong> arrastar não funciona. Copie o código abaixo,
          crie um favorito novo no Chrome com qualquer nome (ex.:{" "}
          <span className="mono">importar nota</span>) e cole isto no campo de endereço
          do favorito. Para usar, digite o nome do favorito na barra de endereços com a
          nota aberta.
        </p>
        <div className="acoes">
          <button
            disabled={!bookmarklet}
            onClick={() => {
              void navigator.clipboard.writeText(bookmarklet).then(() => {
                setCopiado(true);
                setTimeout(() => setCopiado(false), 2500);
              });
            }}
          >
            {copiado ? "✅ Copiado" : "📋 Copiar código do atalho"}
          </button>
        </div>
      </section>

      <section className="cartao">
        <h2>2. Usar</h2>
        <ol className="legenda" style={{ paddingLeft: "1.2rem", lineHeight: 1.7 }}>
          <li>Abra a nota no portal da SEFAZ (pelo QR Code do cupom ou pela chave).</li>
          <li>
            Espere a página mostrar a <strong>lista de produtos</strong> — é dela que os
            itens são lidos.
          </li>
          <li>Clique no favorito. O app abre numa aba nova com a nota importada.</li>
        </ol>
      </section>

      <section className="cartao">
        <h2>Não funcionou?</h2>
        <p className="legenda">
          A aba que abrir vai dizer exatamente o que faltou — se a chave de acesso não
          apareceu na página, ou se a lista de itens não foi reconhecida — junto com o
          tamanho recebido e quantos candidatos de chave foram encontrados. Com essa
          informação dá para ajustar o parser.
        </p>
        <p className="legenda">
          Duas causas comuns: estar na tela de <em>resumo</em> da nota em vez da que lista
          os produtos; ou a página não exibir a chave de acesso — nesse caso a aba{" "}
          <strong>Consulta completa</strong> do portal costuma mostrá-la.
        </p>
        <p className="legenda">
          Se a aba disser <strong>“Atalho não autorizado”</strong>, o atalho é anterior
          ao login (ou a chave secreta do servidor mudou). Instale-o de novo por esta
          tela: ele carrega uma credencial que vale só para importar notas.
        </p>
      </section>
    </>
  );
}
