from pydantic import BaseModel


class ResultadoBuscaOut(BaseModel):
    lote_id: int
    pagina: int
    trecho: str  # com <b>...</b> nos termos achados; CPF, RG e PIS mascarados
    documento_id: int | None  # NULL se a página não pertence a nenhum documento
    tipo: str | None
    nome_arquivo: str
