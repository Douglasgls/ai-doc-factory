from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

# datetime serializado com isoformat() ("...+00:00"), como o FastAPI fazia sem response_model;
# o padrão do Pydantic v2 trocaria o sufixo por "Z" e mudaria o contrato com o frontend.
DataHora = Annotated[datetime, PlainSerializer(lambda d: d.isoformat(), return_type=str, when_used="json")]
