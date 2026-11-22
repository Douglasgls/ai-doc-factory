from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.analise import enfileirar_analise
from app.escopo import filtro_lote
from app.extracao import enfileirar_extracao
from app.models import AnalisePonto, Documento, Lote
from app.renomeacao import atualizar_nome_padronizado_sessao
from app.routers import r
from app.routers.auth.actions import UsuarioContexto
from app.routers.documentos.actions import campos_por_documento, extras_documento
from app.routers.revisao.schemas import Revisao


def fila_revisao(session: Session, usuario: UsuarioContexto) -> list[dict]:
    """Fila só dos lotes no escopo de `usuario` (obrigatório)."""
    docs = session.execute(
        select(Documento.id, Documento.lote_id, Documento.tipo, Documento.confianca, Documento.motivo_revisao,
               Documento.pagina_ini, Documento.pagina_fim, Lote.nome_arquivo, Lote.criado_em)
        .join(Lote, Lote.id == Documento.lote_id)
        .where(Documento.estado == "em_revisao", filtro_lote(usuario))
        .order_by(Documento.lote_id, Documento.ordem)).all()
    campos = campos_por_documento(session, [d[0] for d in docs])
    return [
        {"id": i, "lote_id": l, "tipo_sugerido": t, "confianca": c, "motivo": m,
         "imagem_url": f"/lotes/{l}/paginas/{p}/imagem", "pagina_ini": p, "pagina_fim": pf,
         **extras_documento(campos.get(i, {}), nome, p, pf, criado)}
        for i, l, t, c, m, p, pf, nome, criado in docs
    ]


def revisar_documento(session: Session, documento_id: int, revisao: Revisao, revisor: str) -> dict:
    """`revisor`: e-mail do usuário autenticado; o `revisao.revisor` do corpo é ignorado."""
    # um único UPDATE condicional; no lado direito, tipo e tipo_original ainda são os valores antigos,
    # então tipo_original guarda o tipo sugerido na primeira revisão e não muda nas seguintes
    row = session.execute(
        update(Documento)
        .where(Documento.id == documento_id, Documento.estado.in_(("em_revisao", "revisado")))
        .values(estado="revisado", tipo_original=func.coalesce(Documento.tipo_original, Documento.tipo),
                tipo=revisao.tipo, revisor=revisor, revisado_em=func.now())
        .returning(Documento.id, Documento.estado, Documento.tipo, Documento.tipo_original, Documento.revisor,
                   Documento.revisado_em, Documento.lote_id)
        .execution_options(synchronize_session=False)).first()
    if row is None:
        estado = session.execute(select(Documento.estado).where(Documento.id == documento_id)).first()
        if estado is None:
            raise HTTPException(404, "documento não encontrado")
        raise HTTPException(409, f"documento em estado '{estado[0]}' não aceita revisão")
    atualizar_nome_padronizado_sessao(session, documento_id)
    analisar = False
    if revisao.tipo != "folha_ponto":  # análise de ponto obsoleta: o documento deixou de ser folha de ponto
        session.execute(delete(AnalisePonto).where(AnalisePonto.documento_id == documento_id)
                        .execution_options(synchronize_session=False))
    else:  # não gasta Gemini de novo se já há análise concluída
        analisar = session.execute(
            select(AnalisePonto.documento_id).where(AnalisePonto.documento_id == documento_id,
                                                    AnalisePonto.estado == "concluida")).first() is None
    session.commit()  # antes de enfileirar: o worker precisa enxergar o estado novo
    # forcar=True: a revisão humana vale mesmo com o lote cancelado (a marca de cancelamento continua)
    if analisar:
        enfileirar_analise(documento_id, r, forcar=True)  # nunca levanta: não derruba a revisão
    enfileirar_extracao(documento_id, r, forcar=True)  # depois do commit; nunca levanta
    return {"id": row[0], "estado": row[1], "tipo": row[2], "tipo_original": row[3],
            "revisor": row[4], "revisado_em": row[5]}
