from pydantic import BaseModel


class TipoOut(BaseModel):
    slug: str
    nome: str
    icone: str
