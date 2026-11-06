from datetime import date

import psycopg
from fastapi import HTTPException

from app import conformidade, config
from app.anonimizacao import mascarar_estrutura


def _carregar_conformidade(conn):
    """Todos os documentos e campos: a empresa reúne documentos de vários lotes."""
    docs = [{"id": i, "lote_id": l, "tipo": t, "estado": e} for i, l, t, e in conn.execute(
        "SELECT id, lote_id, tipo, estado FROM documento ORDER BY lote_id, ordem")]
    campos: dict[int, dict[str, str]] = {}
    for doc, campo, valor in conn.execute("SELECT documento_id, campo, valor FROM documento_campos"):
        campos.setdefault(doc, {})[campo] = valor
    return docs, campos


def _resumo(cnpj: str, res: dict) -> dict:
    g = res["geral"]
    return {"cnpj": cnpj, "razao_social": res["razao_social"], "documentos_por_tipo": res["documentos_por_tipo"], "score": g["score"],
            "classificacao": g["classificacao"], "provisorio": g["provisorio"]}


def _empresas():
    with psycopg.connect(config.DATABASE_URL) as conn:
        docs, campos = _carregar_conformidade(conn)
    empresas, sem = conformidade.agrupar_empresas(docs, campos)
    hoje = date.today()
    resultados = {c: conformidade.calcular_empresa(ds, campos, hoje) for c, ds in empresas.items()}
    return resultados, sem, empresas


def listar_empresas() -> list[dict]:
    resultados, _, _ = _empresas()
    return mascarar_estrutura([_resumo(c, res) for c, res in sorted(resultados.items())])


def conformidade_empresa(cnpj: str) -> dict:
    chave = conformidade.validar_cnpj(cnpj)
    resultados, _, _ = _empresas()
    if chave is None or chave not in resultados:
        raise HTTPException(404, "empresa não encontrada")
    # o cálculo usa o CPF real (chave dos grupos de consistência); só a resposta sai mascarada
    return mascarar_estrutura({"cnpj": chave, **resultados[chave]})


def conformidade_lote(lote_id: int) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM lote WHERE id = %s", (lote_id,)).fetchone() is None:
            raise HTTPException(404, "lote não encontrado")
    resultados, sem, grupos = _empresas()
    empresas = []
    for cnpj, res in sorted(resultados.items()):
        nesse_lote = sorted(d["id"] for d in grupos[cnpj] if d["lote_id"] == lote_id)
        if nesse_lote:
            empresas.append({**_resumo(cnpj, res), "documentos": nesse_lote})
    return mascarar_estrutura({
        "lote_id": lote_id, "empresas": empresas,
        "sem_empresa": [{"documento": s["id"], "tipo": s["tipo"], "estado": s["estado"], "motivo": s["motivo"]}
                        for s in sem if s["lote_id"] == lote_id]})
