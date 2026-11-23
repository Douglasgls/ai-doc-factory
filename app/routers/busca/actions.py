from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.anonimizacao import mascarar_documentos
from app.escopo import filtro_lote
from app.models import Documento, Lote, Pagina
from app.routers.auth.actions import UsuarioContexto
from app.routers.documentos.actions import campos_por_documento

_OPCOES = "StartSel=<b>, StopSel=</b>, MaxFragments=2, MaxWords=25, MinWords=8"
# Configuração como literal SQL (não parâmetro): a expressão do índice usa 'portuguese'::regconfig constante.
_PT = literal_column("'portuguese'")


# A expressão to_tsvector('portuguese', coalesce(texto, '')) precisa ser idêntica à do índice pagina_texto_fts_idx.
# A busca acontece no texto original (achar por nome ou CPF segue funcionando); o trecho devolvido é montado
# sobre o texto com CPF, RG e PIS mascarados, para a resposta não revelar o identificador.
def buscar(session: Session, q: str, limite: int, usuario: UsuarioContexto) -> list[dict]:
    """Resultados só dos lotes no escopo de `usuario` (obrigatório: sem ele não há filtro possível)."""
    consulta = func.websearch_to_tsquery(_PT, q)
    vetor = func.to_tsvector(_PT, func.coalesce(Pagina.texto, literal_column("''")))
    linhas = session.execute(
        select(Pagina.lote_id, Pagina.numero, Pagina.documento_id, Documento.tipo, Lote.nome_arquivo,
               Documento.nome_padronizado, Documento.pagina_ini, Documento.pagina_fim, func.coalesce(Pagina.texto, ""))
        .join(Lote, Lote.id == Pagina.lote_id)
        .outerjoin(Documento, Documento.id == Pagina.documento_id)
        .where(vetor.op("@@")(consulta), filtro_lote(usuario))
        .order_by(func.ts_rank(vetor, consulta).desc(), Pagina.lote_id, Pagina.numero)
        .limit(limite)).all()
    campos = campos_por_documento(session, sorted({l[2] for l in linhas if l[2] is not None}))
    saida = []
    for lote_id, numero, doc_id, tipo, arquivo, padronizado, ini, fim, texto in linhas:
        c = campos.get(doc_id, {})
        trecho = session.execute(select(func.ts_headline(_PT, mascarar_documentos(texto), consulta, _OPCOES))
                                 ).scalar_one()
        saida.append({"lote_id": lote_id, "pagina": numero, "trecho": trecho, "documento_id": doc_id,
                      "tipo": tipo, "nome_arquivo": arquivo,
                      "nome_documento": padronizado or arquivo if doc_id is not None else None,
                      "pessoa": c.get("nome_funcionario") or c.get("nome"),
                      "pagina_ini": ini, "pagina_fim": fim})
    return saida
