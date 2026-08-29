/**
 * Estado de sessão do app inteiro.
 *
 * Fica num contexto, e não em cada tela, por dois motivos: a resposta de
 * `GET /auth/sessao` é consultada antes de desenhar qualquer coisa (senão as telas
 * disparam requisições que vão levar 401), e a perda de sessão no meio do uso precisa
 * derrubar todas elas de uma vez, não uma por vez conforme o usuário navega.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, registrarPerdaDeSessao, type EstadoSessao } from "../api/client";

interface Sessao extends EstadoSessao {
  /** Enquanto true, nada é desenhado: não sabemos ainda se há sessão. */
  carregando: boolean;
  entrar: (senha: string) => Promise<void>;
  sair: () => Promise<void>;
}

const Contexto = createContext<Sessao | null>(null);

export function SessaoProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoSessao>({
    autenticado: false,
    autenticacao_ativa: true,
  });
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    void api
      .sessao()
      .then(setEstado)
      // API fora do ar cai aqui. Tratar como "não autenticado" mostra a tela de login,
      // que é honesta: sem servidor não há como ver dado nenhum mesmo.
      .catch(() => setEstado({ autenticado: false, autenticacao_ativa: true }))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    registrarPerdaDeSessao(() =>
      setEstado((anterior) => ({ ...anterior, autenticado: false })),
    );
    return () => registrarPerdaDeSessao(null);
  }, []);

  const entrar = useCallback(async (senha: string) => {
    setEstado(await api.login(senha));
  }, []);

  const sair = useCallback(async () => {
    await api.logout();
    setEstado({ autenticado: false, autenticacao_ativa: true });
  }, []);

  return (
    <Contexto.Provider value={{ ...estado, carregando, entrar, sair }}>
      {children}
    </Contexto.Provider>
  );
}

export function useSessao(): Sessao {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useSessao precisa estar dentro de <SessaoProvider>.");
  return valor;
}
