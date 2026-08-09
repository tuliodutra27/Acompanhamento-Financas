/**
 * Leitura da chave de acesso no cliente — espelho de `backend/app/core/chave_nfce.py`.
 *
 * Existe duplicado de propósito: assim que o usuário termina de colar a chave (ou de
 * escanear o QR Code), a tela já mostra "UF: RJ" e avisa se o dígito verificador não
 * fecha, antes de qualquer requisição. Erro de digitação é pego na hora, e o usuário
 * já sabe se vai poder contar com o preenchimento automático.
 *
 * Se algo mudar aqui, o mesmo tem que mudar no Python (e vice-versa).
 */

export const UF_POR_CODIGO_IBGE: Record<string, string> = {
  "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
  "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
  "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
  "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
  "51": "MT", "52": "GO", "53": "DF",
};

export type MotivoChaveInvalida =
  | "formato"
  | "digito_verificador"
  | "uf_desconhecida"
  | "modelo_nao_suportado";

export interface DadosChave {
  chave: string;
  uf: string;
  cnpjEmitente: string;
  anoMes: string;
  modelo: string;
  numero: string;
}

export type ResultadoChave =
  | { valida: true; dados: DadosChave }
  | { valida: false; motivo: MotivoChaveInvalida };

export function limparChave(entrada: string): string {
  return (entrada ?? "").replace(/\D/g, "");
}

/** Dígito verificador: módulo 11 com pesos 2..9 da direita para a esquerda. */
export function calcularDigitoVerificador(chaveSemDv: string): string | null {
  if (chaveSemDv.length !== 43 || !/^\d+$/.test(chaveSemDv)) return null;

  let soma = 0;
  let peso = 2;
  for (let i = chaveSemDv.length - 1; i >= 0; i -= 1) {
    soma += Number(chaveSemDv[i]) * peso;
    peso = peso === 9 ? 2 : peso + 1;
  }

  const resto = soma % 11;
  return resto === 0 || resto === 1 ? "0" : String(11 - resto);
}

export function lerChave(entrada: string): ResultadoChave {
  const chave = limparChave(entrada);

  if (chave.length !== 44) return { valida: false, motivo: "formato" };

  const codigoUf = chave.slice(0, 2);
  if (!UF_POR_CODIGO_IBGE[codigoUf]) {
    return { valida: false, motivo: "uf_desconhecida" };
  }

  const modelo = chave.slice(20, 22);
  if (modelo !== "65" && modelo !== "55") {
    return { valida: false, motivo: "modelo_nao_suportado" };
  }

  if (chave[43] !== calcularDigitoVerificador(chave.slice(0, 43))) {
    return { valida: false, motivo: "digito_verificador" };
  }

  return {
    valida: true,
    dados: {
      chave,
      uf: UF_POR_CODIGO_IBGE[codigoUf],
      cnpjEmitente: chave.slice(6, 20),
      anoMes: chave.slice(2, 6),
      modelo,
      numero: chave.slice(25, 34),
    },
  };
}

/** Extrai a chave do conteúdo de um QR Code (ou de uma chave crua colada). */
export function extrairChaveDoQrCode(conteudo: string): string | null {
  const texto = (conteudo ?? "").trim();
  if (!texto) return null;

  // QR Code 2.0: ?p=<chave>|<versao>|<ambiente>|<hash>
  const porP = texto.match(/[?&]p=([^&#]+)/i);
  if (porP) {
    const candidato = limparChave(porP[1].split("|")[0]);
    if (candidato.length === 44) return candidato;
  }

  // QR Code 1.0: ?chNFe=<chave>
  const porChNFe = texto.match(/chNFe=(\d{44})/i);
  if (porChNFe) return porChNFe[1];

  const digitos = limparChave(texto);
  if (digitos.length === 44) return digitos;

  const corrida = digitos.match(/\d{44}/);
  return corrida ? corrida[0] : null;
}

/** Formata a chave em blocos de 4, como os portais mostram. */
export function formatarChave(chave: string): string {
  return (limparChave(chave).match(/.{1,4}/g) ?? []).join(" ");
}

/** "2608" -> "ago/2026", para mostrar o mês da compra antes de ter a data completa. */
export function anoMesLegivel(anoMes: string): string {
  if (!/^\d{4}$/.test(anoMes)) return anoMes;
  const meses = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
  ];
  const ano = 2000 + Number(anoMes.slice(0, 2));
  const mes = Number(anoMes.slice(2, 4));
  if (mes < 1 || mes > 12) return anoMes;
  return `${meses[mes - 1]}/${ano}`;
}

export const MENSAGEM_MOTIVO: Record<MotivoChaveInvalida, string> = {
  formato: "A chave precisa ter 44 dígitos.",
  digito_verificador:
    "São 44 dígitos, mas o verificador não fecha — confira se algum número está trocado.",
  uf_desconhecida: "Os dois primeiros dígitos não correspondem a um estado.",
  modelo_nao_suportado: "Esta chave não é de nota fiscal eletrônica.",
};
