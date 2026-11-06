import re

from app.anonimizacao import CAMPOS_IDENTIFICADORES, e_mascarado
from app.routers.revisao.validations import validar_revisor  # noqa: F401  (reaproveitada)

_NOME_CAMPO = re.compile(r"^[a-z0-9_]{1,40}$")
VALOR_MAX = 500


def validar_campos(campos: dict) -> dict:
    if not campos:
        raise ValueError("campos não pode ser vazio")
    for nome, valor in campos.items():
        if not _NOME_CAMPO.match(nome):
            raise ValueError(f"nome de campo inválido: {nome!r} (use ^[a-z0-9_]{{1,40}}$)")
        if valor is not None:
            if not valor.strip():
                raise ValueError(f"valor do campo {nome!r} vazio; use null para remover")
            if nome in CAMPOS_IDENTIFICADORES and e_mascarado(valor):
                # a API devolve CPF/RG/PIS mascarados; o cliente não pode gravar a máscara por cima do valor real
                raise ValueError(f"campo {nome!r} veio mascarado ('*'): omita o campo para mantê-lo "
                                 "ou envie o valor completo para substituí-lo")
            if len(valor) > VALOR_MAX:
                raise ValueError(f"valor do campo {nome!r} excede {VALOR_MAX} caracteres")
    return campos
