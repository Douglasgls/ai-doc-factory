from pydantic import BaseModel


class SaudeOut(BaseModel):
    status: str
