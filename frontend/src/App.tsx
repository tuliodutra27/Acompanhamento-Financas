import { NavLink, Route, Routes } from "react-router-dom";
import { useSessao } from "./auth/Sessao";
import { AdicionarNota } from "./routes/AdicionarNota";
import { Categorias } from "./routes/Categorias";
import { Dashboard } from "./routes/Dashboard";
import { Importar } from "./routes/Importar";
import { Insights } from "./routes/Insights";
import { Login } from "./routes/Login";
import { Notas } from "./routes/Notas";
import { ProdutoDetalhe } from "./routes/ProdutoDetalhe";
import { Produtos } from "./routes/Produtos";
import { RevisaoNota } from "./routes/RevisaoNota";

const abas = [
  { para: "/", icone: "📊", texto: "Painel" },
  { para: "/adicionar", icone: "📷", texto: "Nota" },
  { para: "/insights", icone: "💡", texto: "Insights" },
  { para: "/categorias", icone: "🗂️", texto: "Categorias" },
  { para: "/produtos", icone: "🏷️", texto: "Produtos" },
  { para: "/notas", icone: "🧾", texto: "Notas" },
];

export function App() {
  const { carregando, autenticado, autenticacao_ativa, sair } = useSessao();

  // Nada é desenhado antes de saber se há sessão. Desenhar o app "otimista" faria cada
  // tela disparar requisições que voltariam 401, e o usuário veria erros piscando antes
  // do login aparecer.
  if (carregando) return <div className="tela-login" />;

  if (autenticacao_ativa && !autenticado) return <Login />;

  return (
    <div className="app">
      {autenticacao_ativa && (
        <header className="topo">
          <h1>Acompanhamento de Finanças</h1>
          <button className="discreto" style={{ marginLeft: "auto" }} onClick={() => void sair()}>
            Sair
          </button>
        </header>
      )}

      {!autenticacao_ativa && (
        <div className="faixa-aberto" role="status">
          Sem senha configurada — este app está aberto para quem alcançar a URL.
        </div>
      )}

      <main className="conteudo">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/adicionar" element={<AdicionarNota />} />
          <Route path="/importar" element={<Importar />} />
          <Route path="/categorias" element={<Categorias />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/notas" element={<Notas />} />
          <Route path="/notas/:id" element={<RevisaoNota />} />
          <Route path="/produtos" element={<Produtos />} />
          <Route path="/produtos/:id" element={<ProdutoDetalhe />} />
        </Routes>
      </main>

      <nav className="nav">
        {abas.map((aba) => (
          <NavLink
            key={aba.para}
            to={aba.para}
            end={aba.para === "/"}
            className={({ isActive }) => (isActive ? "ativo" : "")}
          >
            <span className="icone" aria-hidden="true">
              {aba.icone}
            </span>
            {aba.texto}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
