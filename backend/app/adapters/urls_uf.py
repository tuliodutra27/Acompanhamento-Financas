"""URL do portal de consulta de NFC-e de cada UF.

**Para que isso serve, e para que não serve.** Estas URLs *não* são usadas pelo parse
automático: automatizar a consulta por chave digitada não funciona, porque essas
páginas protegem o formulário com reCAPTCHA. O parse automático usa a URL completa
lida do QR Code (que já vem com o hash assinado da nota).

O uso real desta tabela é a interface: quando a nota foi digitada e caiu no
preenchimento manual, o app oferece um link "abrir a nota no portal da SEFAZ" para o
usuário abrir no próprio navegador (onde o reCAPTCHA é um clique, não um obstáculo) e
conferir os itens enquanto preenche.

Fonte: lista pública de URLs de consulta de NFC-e por UF. São o endereço da página de
consulta — não endpoints de API. Podem mudar sem aviso; quando isso acontecer, o
impacto é só um link quebrado na tela de preenchimento manual.
"""

from __future__ import annotations

URL_CONSULTA_POR_UF: dict[str, str] = {
    "AC": "https://www.sefaznet.ac.gov.br/nfce/consulta",
    "AL": "https://www.sefaz.al.gov.br/nfce/consulta",
    "AM": "https://www.sefaz.am.gov.br/nfce/consulta",
    "AP": "https://www.sefaz.ap.gov.br/nfce/consulta",
    "BA": "https://www.sefaz.ba.gov.br/nfce/consulta",
    "CE": "https://www.sefaz.ce.gov.br/nfce/consulta",
    "DF": "https://www.fazenda.df.gov.br/nfce/consulta",
    "ES": "https://www.sefaz.es.gov.br/nfce/consulta",
    "GO": "https://www.sefaz.go.gov.br/nfce/consulta",
    "MA": "https://www.sefaz.ma.gov.br/nfce/consulta",
    "MG": "https://nfce.fazenda.mg.gov.br/portalnfce",
    "MS": "https://www.dfe.ms.gov.br/nfce/consulta",
    "MT": "https://www.sefaz.mt.gov.br/nfce/consultanfce",
    "PA": "https://www.sefa.pa.gov.br/nfce/consulta",
    "PB": "https://www.receita.pb.gov.br/nfce/consulta",
    "PE": "https://nfce.sefaz.pe.gov.br/nfce/consulta",
    "PI": "https://www.sefaz.pi.gov.br/nfce/consulta",
    "PR": "https://www.fazenda.pr.gov.br/nfce/consulta",
    "RJ": "https://www.fazenda.rj.gov.br/nfce/consulta",
    "RN": "https://www.set.rn.gov.br/nfce/consulta",
    "RO": "https://www.sefin.ro.gov.br/nfce/consulta",
    "RR": "https://www.sefaz.rr.gov.br/nfce/consulta",
    "RS": "https://www.sefaz.rs.gov.br/nfce/consulta",
    "SC": "https://sat.sef.sc.gov.br/nfce/consulta",
    "SE": "https://www.nfce.se.gov.br/nfce/consulta",
    "SP": "https://nfce.fazenda.sp.gov.br/consulta",
    "TO": "https://www.sefaz.to.gov.br/nfce/consulta",
}


def url_consulta_manual(uf: str) -> str | None:
    """Link do portal da UF para o usuário abrir a nota no próprio navegador."""
    return URL_CONSULTA_POR_UF.get((uf or "").upper())
