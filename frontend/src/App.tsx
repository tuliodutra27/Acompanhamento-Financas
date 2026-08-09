import { NavLink, Route, Routes } from "react-router-dom";
import { AdicionarNota } from "./routes/AdicionarNota";
import { Dashboard } from "./routes/Dashboard";
import { Importar } from "./routes/Importar";
import { Notas } from "./routes/Notas";
import { ProdutoDetalhe } from "./routes/ProdutoDetalhe";
import { Produtos } from "./routes/Produtos";
import { RevisaoNota } from "./routes/RevisaoNota";

const abas = [
  { para: "/", icone: "📊", texto: "Painel" },
  { para: "/adicionar", icone: "📷", texto: "Nova nota" },
  { para: "/produtos", icone: "🏷️", texto: "Produtos" },
  { para: "/notas", icone: "🧾", texto: "Notas" },
];

export function App() {
  return (
    <div className="app">
      <main className="conteudo">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/adicionar" element={<AdicionarNota />} />
          <Route path="/importar" element={<Importar />} />
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
