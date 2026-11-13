import psycopg
from fastapi import HTTPException

from app import config
from app.analise import enfileirar_analise
from app.eventos import limpar_cancelado
from app.extracao import enfileirar_extracao
from app.renomeacao import atualizar_nome_padronizado
from app.routers import r
from app.routers.documentos.actions import campos_por_documento, extras_documento
from app.routers.revisao.schemas import Revisao


def fila_revisao() -> list[dict]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        docs = conn.execute(
            "SELECT d.id, d.lote_id, d.tipo, d.confianca, d.motivo_revisao, d.pagina_ini, d.pagina_fim, "
            "l.nome_arquivo, l.criado_em FROM documento d JOIN lote l ON l.id = d.lote_id "
            "WHERE d.estado = 'em_revisao' ORDER BY d.lote_id, d.ordem"
        ).fetchall()
        campos = campos_por_documento(conn, [d[0] for d in docs])
    return [
        {"id": i, "lote_id": l, "tipo_sugerido": t, "confianca": c, "motivo": m,
         "imagem_url": f"/lotes/{l}/paginas/{p}/imagem", "pagina_ini": p, "pagina_fim": pf,
         **extras_documento(campos.get(i, {}), nome, p, pf, criado)}
        for i, l, t, c, m, p, pf, nome, criado in docs
    ]


def revisar_documento(documento_id: int, revisao: Revisao) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        # um único UPDATE condicional; no lado direito, tipo e tipo_original ainda são os valores antigos,
        # então tipo_original guarda o tipo sugerido na primeira revisão e não muda nas seguintes
        row = conn.execute(
            "UPDATE documento SET estado = 'revisado', tipo_original = COALESCE(tipo_original, tipo), "
            "tipo = %s, revisor = %s, revisado_em = now() "
            "WHERE id = %s AND estado IN ('em_revisao', 'revisado') "
            "RETURNING id, estado, tipo, tipo_original, revisor, revisado_em, lote_id",
            (revisao.tipo, revisao.revisor, documento_id),
        ).fetchone()
        if row is None:
            estado = conn.execute("SELECT estado FROM documento WHERE id = %s", (documento_id,)).fetchone()
            if estado is None:
                raise HTTPException(404, "documento não encontrado")
            raise HTTPException(409, f"documento em estado '{estado[0]}' não aceita revisão")
        atualizar_nome_padronizado(conn, documento_id)
    limpar_cancelado(row[6], r)  # revisão humana vale mesmo após um cancelamento do lote; nunca levanta
    if revisao.tipo == "folha_ponto":
        enfileirar_analise(documento_id, r)  # nunca levanta: não derruba a revisão
    enfileirar_extracao(documento_id, r)  # depois do commit; nunca levanta
    return {"id": row[0], "estado": row[1], "tipo": row[2], "tipo_original": row[3],
            "revisor": row[4], "revisado_em": row[5]}
