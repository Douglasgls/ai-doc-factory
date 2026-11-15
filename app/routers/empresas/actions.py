from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import conformidade
from app.anonimizacao import mascarar_estrutura
from app.models import Documento, DocumentoCampo, Lote


def _carregar_conformidade(session: Session):
    """Todos os documentos e campos: a empresa reúne documentos de vários lotes."""
    docs = [{"id": i, "lote_id": l, "tipo": t, "estado": e} for i, l, t, e in session.execute(
        select(Documento.id, Documento.lote_id, Documento.tipo, Documento.estado)
        .order_by(Documento.lote_id, Documento.ordem))]
    campos: dict[int, dict[str, str]] = {}
    for doc, campo, valor in session.execute(
            select(DocumentoCampo.documento_id, DocumentoCampo.campo, DocumentoCampo.valor)):
        campos.setdefault(doc, {})[campo] = valor
    return docs, campos


def _resumo(cnpj: str, res: dict) -> dict:
    g = res["geral"]
    return {"cnpj": cnpj, "razao_social": res["razao_social"], "documentos_por_tipo": res["documentos_por_tipo"], "score": g["score"],
            "classificacao": g["classificacao"], "provisorio": g["provisorio"]}


def _empresas(session: Session):
    docs, campos = _carregar_conformidade(session)
    empresas, sem = conformidade.agrupar_empresas(docs, campos)
    hoje = date.today()
    resultados = {c: conformidade.calcular_empresa(ds, campos, hoje) for c, ds in empresas.items()}
    return resultados, sem, empresas


def listar_empresas(session: Session) -> list[dict]:
    resultados, _, _ = _empresas(session)
    return mascarar_estrutura([_resumo(c, res) for c, res in sorted(resultados.items())])


def conformidade_empresa(session: Session, cnpj: str) -> dict:
    chave = conformidade.validar_cnpj(cnpj)
    resultados, _, _ = _empresas(session)
    if chave is None or chave not in resultados:
        raise HTTPException(404, "empresa não encontrada")
    # o cálculo usa o CPF real (chave dos grupos de consistência); só a resposta sai mascarada
    return mascarar_estrutura({"cnpj": chave, **resultados[chave]})


def conformidade_lote(session: Session, lote_id: int) -> dict:
    if session.execute(select(Lote.id).where(Lote.id == lote_id)).first() is None:
        raise HTTPException(404, "lote não encontrado")
    resultados, sem, grupos = _empresas(session)
    empresas = []
    for cnpj, res in sorted(resultados.items()):
        nesse_lote = sorted(d["id"] for d in grupos[cnpj] if d["lote_id"] == lote_id)
        if nesse_lote:
            empresas.append({**_resumo(cnpj, res), "documentos": nesse_lote})
    return mascarar_estrutura({
        "lote_id": lote_id, "empresas": empresas,
        "sem_empresa": [{"documento": s["id"], "tipo": s["tipo"], "estado": s["estado"], "motivo": s["motivo"]}
                        for s in sem if s["lote_id"] == lote_id]})
