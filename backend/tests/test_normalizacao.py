"""Testes da normalização de descrição (a base do vínculo item -> produto)."""

from __future__ import annotations

import pytest

from app.services.normalizacao import normalizar_descricao


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Arroz Tio João 5kg", "ARROZ TIO JOAO 5KG"),
        ("  feijão   carioca  ", "FEIJAO CARIOCA"),
        ("AÇÚCAR REFINADO", "ACUCAR REFINADO"),
        ("PÃO FRANCÊS", "PAO FRANCES"),
        ("", ""),
    ],
)
def test_normalizar_descricao(entrada: str, esperado: str):
    assert normalizar_descricao(entrada) == esperado


def test_mesma_descricao_com_grafias_diferentes_normaliza_igual():
    """É o que faz o mesmo item de duas notas cair no mesmo alias."""
    assert normalizar_descricao("Açúcar  Cristal") == normalizar_descricao(
        "ACUCAR CRISTAL"
    )
