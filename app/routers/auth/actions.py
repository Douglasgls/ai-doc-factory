"""Autenticação por usuário (tabela `usuario`). JWT HS256 com PyJWT.
Falha fechada: sem AUTH_SEGREDO nada é liberado. O token só identifica o usuário; nível, papel e vínculo
valem sempre os do banco, relidos a cada requisição (desativar ou mudar papel vale na hora)."""
import functools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, true, update
from sqlalchemy.orm import Session

from app import config, senhas
from app.database import get_session
from app.models import Prestador, Tomador, Usuario

ALGORITMO = "HS256"
bearer = HTTPBearer(auto_error=False, description="Token obtido em POST /auth/login")
ID_MAX = 2 ** 63 - 1  # BIGINT



def _consulta_usuario():
    """Usuário e o estado da organização (sem organização, conta como ativa)."""
    return (select(Usuario, func.coalesce(Tomador.ativo, Prestador.ativo, true()).label("organizacao_ativa"))
            .outerjoin(Tomador, Tomador.id == Usuario.tomador_id)
            .outerjoin(Prestador, Prestador.id == Usuario.prestador_id))


@dataclass(frozen=True)
class UsuarioContexto:
    id: int
    email: str
    nome: str
    nivel: str
    papel: str
    tomador_id: int | None
    prestador_id: int | None


def _exigir_configuracao() -> None:
    if not config.AUTH_SEGREDO:
        raise HTTPException(503, "autenticação não configurada: defina AUTH_SEGREDO")


def _nao_autorizado(mensagem: str) -> HTTPException:
    return HTTPException(401, mensagem, headers={"WWW-Authenticate": "Bearer"})


@functools.lru_cache(maxsize=1)
def _hash_ficticio() -> str:
    """Hash de uma senha que ninguém usa, com o custo atual: dá o mesmo trabalho quando o usuário não existe."""
    return senhas.gerar_hash("senha-ficticia-sem-uso")


def _contexto(u: Usuario) -> UsuarioContexto:
    return UsuarioContexto(id=u.id, email=u.email, nome=u.nome, nivel=u.nivel, papel=u.papel,
                           tomador_id=u.tomador_id, prestador_id=u.prestador_id)


def login(session: Session, identificador: str, senha: str) -> dict:
    _exigir_configuracao()
    email = identificador.strip().lower()
    linha = session.execute(_consulta_usuario().where(func.lower(Usuario.email) == email)).first()
    usuario = linha[0] if linha else None
    # Sempre roda uma verificação de hash (a real ou a fictícia): o tempo não revela se o e-mail existe.
    hash_gravado = usuario.senha_hash if usuario else None
    senha_ok = senhas.verificar(senha, hash_gravado or _hash_ficticio())
    if not (usuario and hash_gravado and senha_ok and usuario.ativo and linha[1]):
        raise _nao_autorizado("usuário ou senha inválidos")
    if senhas.precisa_rehash(hash_gravado):
        # Condição no hash antigo: não sobrescreve uma troca de senha feita no meio do caminho.
        session.execute(update(Usuario).where(Usuario.id == usuario.id, Usuario.senha_hash == hash_gravado)
                        .values(senha_hash=senhas.gerar_hash(senha)).execution_options(synchronize_session=False))
        session.commit()
    return emitir_token(_contexto(usuario))


def emitir_token(usuario: UsuarioContexto) -> dict:
    """JWT no formato de /auth/login para um usuário já autenticado (login e aceite de convite)."""
    _exigir_configuracao()
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=config.AUTH_EXPIRA_MIN)
    claims = {"sub": str(usuario.id), "nivel": usuario.nivel, "papel": usuario.papel,
              "tomador_id": usuario.tomador_id, "prestador_id": usuario.prestador_id,
              "iat": int(agora.timestamp()), "exp": int(expira.timestamp())}
    token = jwt.encode(claims, config.AUTH_SEGREDO, algorithm=ALGORITMO)
    return {"access_token": token, "token_type": "bearer", "expira_em": expira.isoformat()}


def exigir_usuario(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
                   session: Session = Depends(get_session)) -> UsuarioContexto:
    """Valida o token e devolve o usuário como está AGORA no banco; recusa se sumiu ou foi desativado."""
    _exigir_configuracao()
    negado = _nao_autorizado("não autenticado")
    if credenciais is None:
        raise negado
    try:
        dados = jwt.decode(credenciais.credentials, config.AUTH_SEGREDO, algorithms=[ALGORITMO],
                           options={"require": ["sub", "iat", "exp"]})
    except jwt.PyJWTError:
        raise negado
    sub = dados.get("sub")
    # Formato antigo (sub = nome do admin) e qualquer sub que não seja um id numérico caem aqui.
    if not isinstance(sub, str) or not sub.isascii() or not sub.isdigit() or int(sub) > ID_MAX:
        raise negado
    linha = session.execute(_consulta_usuario().where(Usuario.id == int(sub))).first()
    # Libera a conexão já aqui: a leitura do usuário é uma transação própria, como antes, e nenhuma conexão
    # fica presa (por exemplo, durante um stream SSE) até o fim da requisição.
    session.commit()
    if linha is None or not linha[0].ativo or not linha[1]:
        raise negado
    return _contexto(linha[0])


def exigir_plataforma(usuario: UsuarioContexto = Depends(exigir_usuario)) -> UsuarioContexto:
    """Rotas só da equipe da plataforma (criação de organizações, conformidade por empresa)."""
    if usuario.nivel != "plataforma":
        raise HTTPException(403, "acesso restrito à plataforma")
    return usuario
