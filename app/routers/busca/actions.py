import psycopg

from app import config
from app.anonimizacao import mascarar_documentos

_OPCOES = "StartSel=<b>, StopSel=</b>, MaxFragments=2, MaxWords=25, MinWords=8"


# A expressão to_tsvector('portuguese', coalesce(texto, '')) precisa ser idêntica à do índice pagina_texto_fts_idx.
# A busca acontece no texto original (achar por nome ou CPF segue funcionando); o trecho devolvido é montado
# sobre o texto com CPF, RG e PIS mascarados, para a resposta não revelar o identificador.
def buscar(q: str, limite: int) -> list[dict]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        linhas = conn.execute(
            """
            SELECT p.lote_id, p.numero, p.documento_id, d.tipo, l.nome_arquivo, coalesce(p.texto, '')
              FROM pagina p
              JOIN lote l ON l.id = p.lote_id
              LEFT JOIN documento d ON d.id = p.documento_id,
                   websearch_to_tsquery('portuguese', %s) AS query
             WHERE to_tsvector('portuguese', coalesce(p.texto, '')) @@ query
             ORDER BY ts_rank(to_tsvector('portuguese', coalesce(p.texto, '')), query) DESC, p.lote_id, p.numero
             LIMIT %s
            """,
            (q, limite),
        ).fetchall()
        saida = []
        for lote_id, numero, doc_id, tipo, arquivo, texto in linhas:
            trecho = conn.execute(
                "SELECT ts_headline('portuguese', %s, websearch_to_tsquery('portuguese', %s), %s)",
                (mascarar_documentos(texto), q, _OPCOES)).fetchone()[0]
            saida.append({"lote_id": lote_id, "pagina": numero, "trecho": trecho, "documento_id": doc_id,
                          "tipo": tipo, "nome_arquivo": arquivo})
    return saida
