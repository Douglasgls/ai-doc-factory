"""Autenticação por usuário (tabela `usuario`). JWT HS256 com PyJWT.
Falha fechada: sem AUTH_SEGREDO nada é liberado. O token só identifica o usuário; nível, papel e vínculo
valem sempre os do banco, relidos a cada requisição (desativar ou mudar papel vale na hora)."""
import functools
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config, senhas

ALGORITMO = "HS256"
bearer = HTTPBearer(auto_error=False, description="Token obtido em POST /auth/login")
ID_MAX = 2 ** 63 - 1  # BIGINT

# Colunas lidas do usuário e do estado da organização (sem organização, conta como ativa).
_SELECT_USUARIO = """
    SELECT u.id, u.email, u.nome, u.senha_hash, u.nivel, u.papel, u.tomador_id, u.prestador_id, u.ativo,
           COALESCE(t.ativo, p.ativo, true) AS organizacao_ativa
      FROM usuario u
      LEFT JOIN tomador t ON t.id = u.tomador_id
      LEFT JOIN prestador p ON p.id = u.prestador_id
"""


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


def _contexto(linha) -> UsuarioContexto:
    return UsuarioContexto(id=linha[0], email=linha[1], nome=linha[2], nivel=linha[4], papel=linha[5],
                           tomador_id=linha[6], prestador_id=linha[7])


def login(identificador: str, senha: str) -> dict:
    _exigir_configuracao()
    email = identificador.strip().lower()
    with psycopg.connect(config.DATABASE_URL) as conn:
        linha = conn.execute(_SELECT_USUARIO + " WHERE lower(u.email) = %s", (email,)).fetchone()
        # Sempre roda uma verificação de hash (a real ou a fictícia): o tempo não revela se o e-mail existe.
        hash_gravado = linha[3] if linha else None
        senha_ok = senhas.verificar(senha, hash_gravado or _hash_ficticio())
        if not (linha and hash_gravado and senha_ok and linha[8] and linha[9]):
            raise _nao_autorizado("usuário ou senha inválidos")
        if senhas.precisa_rehash(hash_gravado):
            # Condição no hash antigo: não sobrescreve uma troca de senha feita no meio do caminho.
            conn.execute("UPDATE usuario SET senha_hash = %s WHERE id = %s AND senha_hash = %s",
                         (senhas.gerar_hash(senha), linha[0], hash_gravado))
    usuario = _contexto(linha)
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=config.AUTH_EXPIRA_MIN)
    claims = {"sub": str(usuario.id), "nivel": usuario.nivel, "papel": usuario.papel,
              "tomador_id": usuario.tomador_id, "prestador_id": usuario.prestador_id,
              "iat": int(agora.timestamp()), "exp": int(expira.timestamp())}
    token = jwt.encode(claims, config.AUTH_SEGREDO, algorithm=ALGORITMO)
    return {"access_token": token, "token_type": "bearer", "expira_em": expira.isoformat()}


def exigir_usuario(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UsuarioContexto:
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
    with psycopg.connect(config.DATABASE_URL) as conn:
        linha = conn.execute(_SELECT_USUARIO + " WHERE u.id = %s", (int(sub),)).fetchone()
    if linha is None or not linha[8] or not linha[9]:
        raise negado
    return _contexto(linha)


def exigir_plataforma(usuario: UsuarioContexto = Depends(exigir_usuario)) -> UsuarioContexto:
    """Falha fechada até existir o filtro de dados por organização: só a equipe da plataforma acessa os dados."""
    if usuario.nivel != "plataforma":
        raise HTTPException(403, "acesso indisponível para este nível de usuário: o acesso de tomadores e "
                                 "prestadores aos dados ainda não está disponível")
    return usuario
