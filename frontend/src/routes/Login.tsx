/**
 * Tela de login. Um usuário só, uma senha só — sem cadastro, sem "esqueci minha senha"
 * (não há e-mail para onde mandar nada) e sem campo de usuário, que seria só mais uma
 * coisa a digitar no celular sem proteger nada.
 */

import { useState, type FormEvent } from "react";
import { FalhaApi } from "../api/client";
import { useSessao } from "../auth/Sessao";

export function Login() {
  const { entrar } = useSessao();
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!senha || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      await entrar(senha);
    } catch (falha) {
      setErro(
        falha instanceof FalhaApi ? falha.erro.mensagem : "Não consegui falar com a API.",
      );
      setSenha("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <form className="cartao caixa-login" onSubmit={aoEnviar}>
        <h1>
          <span aria-hidden="true">🧾</span> Acompanhamento de Finanças
        </h1>
        <p className="legenda">Seus gastos de mercado. Entre para continuar.</p>

        <div className="campo" style={{ marginTop: "1rem" }}>
          <label htmlFor="senha">Senha</label>
          <input
            id="senha"
            type="password"
            value={senha}
            onChange={(evento) => setSenha(evento.target.value)}
            autoComplete="current-password"
            // O teclado do celular abre já no campo certo — é a primeira e única
            // interação da tela.
            autoFocus
          />
        </div>

        {erro && (
          <div className="aviso erro" role="alert">
            <span className="icone" aria-hidden="true">
              ⚠️
            </span>
            <span>{erro}</span>
          </div>
        )}

        <button className="primario" type="submit" disabled={!senha || enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
