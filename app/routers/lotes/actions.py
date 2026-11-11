import hashlib
from pathlib import Path

import psycopg
from fastapi import HTTPException

from app import config
from app.filas import enfileirar
from app.routers import r


def validar_empresa(empresa_id: int | None) -> None:
    if empresa_id is None:
        return
    with psycopg.connect(config.DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM empresa WHERE id = %s", (empresa_id,)).fetchone() is None:
            raise HTTPException(404, f"empresa {empresa_id} não encontrada")


def _reenvio(conn, sha: str, pdf: bytes, empresa_id: int | None) -> tuple[dict, bool]:
    """Mesmo arquivo já enviado: devolve o lote existente e diz se precisa enfileirar a segmentação.
    Lote em 'erro' volta para 'recebido' (reprocessa); 'ocr', 'classificando' e 'concluido' ficam como estão."""
    id_, estado, atual = conn.execute(
        "SELECT id, estado, empresa_id FROM lote WHERE sha256 = %s", (sha,)).fetchone()
    if empresa_id is not None and atual is not None and atual != empresa_id:
        raise HTTPException(409, f"lote {id_} já pertence à empresa {atual}")
    if empresa_id is not None and atual is None:
        conn.execute("UPDATE lote SET empresa_id = %s WHERE id = %s", (empresa_id, id_))
        atual = empresa_id
    reprocessando = False
    if estado == "erro":
        # atômico: de dois reenvios simultâneos, só um enxerga 'erro' e enfileira
        reprocessando = conn.execute(
            "UPDATE lote SET estado = 'recebido' WHERE id = %s AND estado = 'erro' RETURNING id",
            (id_,)).fetchone() is not None
        if reprocessando:
            estado = "recebido"
    # em 'recebido' o enfileirar original pode ter falhado; job duplicado é aceitável (handlers idempotentes)
    reenfileirar = estado == "recebido"
    if reenfileirar:
        original = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
        if not original.is_file():  # a gravação pode ter falhado antes
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(pdf)
    resposta = {"lote_id": id_, "estado": estado, "existente": True, "empresa_id": atual}
    if reprocessando:
        resposta["reprocessando"] = True
    return resposta, reenfileirar


def criar_lote(dados: bytes, pdf: bytes, nome_arquivo: str | None, empresa_id: int | None = None) -> dict:
    sha = hashlib.sha256(dados).hexdigest()  # dos bytes originais enviados, PDF ou imagem
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, empresa_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (sha256) DO NOTHING RETURNING id, estado",
            (sha, nome_arquivo or "lote.pdf", empresa_id),
        ).fetchone()
        if row is None:  # mesmo arquivo já enviado
            resposta, reenfileirar = _reenvio(conn, sha, pdf, empresa_id)
        else:
            pasta = Path(config.DATA_DIR) / f"lote_{row[0]}"
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "original.pdf").write_bytes(pdf)
            resposta = {"lote_id": row[0], "estado": row[1], "existente": False, "empresa_id": empresa_id}
            reenfileirar = True
    if reenfileirar:  # só depois do commit, para o worker enxergar o estado novo
        enfileirar(r, config.FILA_SEGMENTAR, {"lote_id": resposta["lote_id"]})
    return resposta


def obter_lote(lote_id: int) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute(
            "SELECT id, nome_arquivo, estado, docs_pendentes, empresa_id FROM lote WHERE id = %s", (lote_id,)
        ).fetchone()
        if lote is None:
            raise HTTPException(404, "lote não encontrado")
        docs = conn.execute(
            "SELECT id, ordem, pagina_ini, pagina_fim, estado, tipo, confianca, segmentacao_ambigua, "
            "probabilidades, tipo_original FROM documento WHERE lote_id = %s ORDER BY ordem", (lote_id,)
        ).fetchall()
    return {
        "id": lote[0], "nome_arquivo": lote[1], "estado": lote[2], "docs_pendentes": lote[3], "empresa_id": lote[4],
        "documentos": [
            {"id": d[0], "ordem": d[1], "pagina_ini": d[2], "pagina_fim": d[3], "estado": d[4],
             "tipo": d[5], "confianca": d[6], "segmentacao_ambigua": d[7],
             "probabilidades": d[8], "tipo_original": d[9]}
            for d in docs
        ],
    }


def caminho_imagem_pagina(lote_id: int, numero: int) -> Path:
    png = Path(config.DATA_DIR) / f"lote_{lote_id}" / f"pag_{numero:04d}.png"
    if not png.is_file():
        raise HTTPException(404, "imagem não encontrada")
    return png
