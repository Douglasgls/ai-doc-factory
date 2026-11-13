"""Handler de classificar_documento: classifica, roteia por confiança e faz o fan-in do lote.

O classificador é trocável (ver app/classificador_regras.py). A leitura e a classificação (que pode virar
chamada de rede) ficam fora da transação; só a gravação e o fan-in rodam dentro dela.
"""
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from app import config
from app.analise import enfileirar_analise
from app.eventos import (
    concluir_tarefa_pos,
    limpar_tarefas_pos,
    lote_cancelado,
    publicar_evento,
    registrar_tarefas_pos,
    tarefas_pos_pendentes,
)
from app.roteamento import decidir

TEXTO_MAX = 6000  # caracteres das primeiras páginas enviados ao classificador


def montar_texto(textos: list[str], limite: int = TEXTO_MAX) -> str:
    return "\n".join(t or "" for t in textos)[:limite]


def _classificar(texto: str, imagem: bytes | None):
    """Escolha do classificador (CLASSIFICADOR=regras roda sem rede)."""
    if config.CLASSIFICADOR == "regras":
        from app.classificador_regras import classificar
    else:
        from app.classificador_llm import classificar
    return classificar(texto, imagem)


def _imagem_primeira_pagina(lote_id: int, pagina: int) -> bytes | None:
    png = Path(config.DATA_DIR) / f"lote_{lote_id}" / f"pag_{pagina:04d}.png"
    try:
        return png.read_bytes()
    except OSError:
        return None


def _fan_in(conn, lote_id: int) -> int:
    restantes = conn.execute(
        "UPDATE lote SET docs_pendentes = docs_pendentes - 1 WHERE id = %s RETURNING docs_pendentes",
        (lote_id,),
    ).fetchone()[0]
    if restantes == 0:
        conn.execute("UPDATE lote SET estado = 'concluido' WHERE id = %s", (lote_id,))
    return restantes


def _abortar_se_cancelado(conn, lote_id: int) -> None:
    conn.execute(
        "UPDATE documento SET estado = 'erro' WHERE lote_id = %s AND estado = 'segmentado'",
        (lote_id,),
    )
    conn.execute(
        "UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s AND estado != 'concluido'",
        (lote_id,),
    )


def marcar_erro(payload: dict) -> None:
    """ao_esgotar: job foi para a dlq. Marca o documento como 'erro' (só a partir de 'segmentado') e faz o
    fan-in, para o lote poder concluir. Reentrância segura: se já saiu de 'segmentado', não decrementa."""
    doc_id = payload["documento_id"]
    lote_id = None
    restantes = 0
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "UPDATE documento SET estado = 'erro' WHERE id = %s AND estado = 'segmentado' RETURNING lote_id",
            (doc_id,),
        ).fetchone()
        if row is not None:
            lote_id = row[0]
            restantes = _fan_in(conn, lote_id)
    if lote_id is not None:
        restantes_pos = concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
        etapa = "classificando" if restantes > 0 else ("extracao" if restantes_pos else "concluido")
        publicar_evento(
            lote_id,
            etapa,
            f"Falha ao classificar documento #{doc_id}.",
            documento_id=doc_id,
            docs_pendentes=restantes,
        )


def classificar_documento(payload: dict) -> None:
    doc_id = payload["documento_id"]
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute(
            "SELECT estado, segmentacao_ambigua, lote_id, pagina_ini FROM documento WHERE id = %s", (doc_id,)
        ).fetchone()
        if doc is None or doc[0] != "segmentado":
            return  # já decidido ou revisado: job repetido não faz nada
        if lote_cancelado(doc[2]):
            _abortar_se_cancelado(conn, doc[2])
            limpar_tarefas_pos(doc[2])
            return
        textos = [t for (t,) in conn.execute(
            "SELECT texto FROM pagina WHERE documento_id = %s ORDER BY numero", (doc_id,))]
    publicar_evento(
        doc[2],
        "classificando",
        f"Classificando documento #{doc_id} (pág. {doc[3]})...",
        documento_id=doc_id,
    )
    resultado = _classificar(montar_texto(textos), _imagem_primeira_pagina(doc[2], doc[3]))
    decisao = decidir(resultado.confianca, resultado.tipo, desacordo=resultado.desacordo,
                      segmentacao_ambigua=doc[1])
    vai_analisar_ponto = decisao.estado == "classificado" and decisao.tipo == "folha_ponto"
    tarefas = [f"extracao:{doc_id}"]
    if vai_analisar_ponto:
        tarefas.append(f"analise:{doc_id}")
    # A tarefa pós é registrada ANTES do commit: se fosse depois, haveria uma janela com o lote já 'concluido' no
    # banco e nenhuma tarefa pendente, e o stream SSE encerraria cedo. Se a transação falhar, a tarefa é removida.
    registradas = False
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:  # transação única: gravação + fan-in
            if lote_cancelado(doc[2]):
                _abortar_se_cancelado(conn, doc[2])
                limpar_tarefas_pos(doc[2])
                return
            # só a transição segmentado -> (classificado | em_revisao) conta: não sobrescreve nem decrementa de novo
            row = conn.execute(
                "UPDATE documento SET estado = %s, tipo = %s, confianca = %s, modelo = %s, versao_prompt = %s, "
                "probabilidades = %s, motivo_revisao = %s, segunda_opiniao = %s WHERE id = %s AND estado = 'segmentado' RETURNING lote_id",
                (decisao.estado, decisao.tipo, resultado.confianca, resultado.modelo, resultado.versao_prompt,
                 Jsonb(resultado.probabilidades), decisao.motivo,
                 Jsonb(resultado.segunda_opiniao) if resultado.segunda_opiniao else None, doc_id),
            ).fetchone()
            if row is None:
                return
            registrar_tarefas_pos(row[0], tarefas)
            registradas = True
            restantes = _fan_in(conn, row[0])
    except Exception:
        if registradas:  # rollback ou falha no commit: não deixa tarefa órfã
            for tarefa in tarefas:
                concluir_tarefa_pos(doc[2], tarefa)
        raise
    lote_id = row[0]
    rotulo_tipo = config.TIPOS_INFO.get(decisao.tipo or "", {}).get("nome", decisao.tipo or "Desconhecido")
    if restantes > 0:
        publicar_evento(
            lote_id,
            "classificando",
            f"Documento #{doc_id}: {rotulo_tipo} ({restantes} pendente(s))",
            documento_id=doc_id,
            tipo=decisao.tipo,
            estado_documento=decisao.estado,
            docs_pendentes=restantes,
        )
    else:
        publicar_evento(
            lote_id,
            "extracao",
            f"Classificação concluída ({rotulo_tipo}) · extraindo campos com IA...",
            documento_id=doc_id,
            tipo=decisao.tipo,
            estado_documento=decisao.estado,
            docs_pendentes=0,
        )
    if vai_analisar_ponto:
        enfileirar_analise(doc_id)  # fora do fan-in e da transação; nunca levanta
    # classificado e em_revisao: CNPJ e demais campos não dependem do tipo confirmado
    from app.extracao import enfileirar_extracao  # import tardio: extracao importa este módulo
    enfileirar_extracao(doc_id)
    if restantes == 0 and not tarefas_pos_pendentes(lote_id):
        publicar_evento(
            lote_id,
            "concluido",
            f"Classificação concluída ({rotulo_tipo}).",
            documento_id=doc_id,
            tipo=decisao.tipo,
            estado_documento=decisao.estado,
            docs_pendentes=0,
        )
