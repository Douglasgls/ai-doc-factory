from pydantic import BaseModel


class ResultadoBuscaOut(BaseModel):
    lote_id: int
    pagina: int
    trecho: str  # com <b>...</b> nos termos achados; CPF, RG e PIS mascarados
    documento_id: int | None  # NULL se a página não pertence a nenhum documento
    tipo: str | None
    nome_arquivo: str
    nome_documento: str | None = None  # nome padronizado do documento (ou o do lote); NULL sem documento
    pessoa: str | None = None
    pagina_ini: int | None = None  # intervalo do documento no lote: a página dentro dele é pagina - pagina_ini + 1
    pagina_fim: int | None = None
