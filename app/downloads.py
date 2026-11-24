"""Cabeçalho Content-Disposition seguro (RFC 6266 / RFC 5987) para qualquer download da API."""
import re
import unicodedata
from urllib.parse import quote


def content_disposition(nome: str, tipo: str = "attachment") -> str:
    """`attachment; filename="<ASCII seguro>"; filename*=UTF-8''<percent-encoded>`.

    O `filename` ASCII serve de reserva para clientes antigos: acentos viram a letra base, e aspas,
    barras, caracteres de controle e demais símbolos viram `_`. O `filename*` leva o nome original
    (sem separadores de caminho nem controles), percent-encoded em UTF-8."""
    limpo = re.sub(r"[\x00-\x1f\x7f]", "", nome).replace("\\", "/").rsplit("/", 1)[-1].strip() or "arquivo"
    ascii_nome = unicodedata.normalize("NFKD", limpo).encode("ascii", "ignore").decode("ascii")
    ascii_nome = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_nome).strip() or "arquivo"
    return f"{tipo}; filename=\"{ascii_nome}\"; filename*=UTF-8''{quote(limpo, safe='')}"
