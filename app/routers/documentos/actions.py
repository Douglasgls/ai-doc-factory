from pathlib import Path
import subprocess
import tempfile

import psycopg
from fastapi import HTTPException

from app import config
from app.anonimizacao import mascarar_campos, mascarar_documentos, mascarar_estrutura
from app.analise import enfileirar_analise
from app.eventos import limpar_cancelado
from app.extracao import enfileirar_extracao
from app.renomeacao import atualizar_nome_padronizado, gerar_nome_padronizado
from app.routers import r
from app.routers.documentos.schemas import AtualizacaoCampos
from app.routers.revisao.schemas import Revisao

_COLUNAS_ANALISE = ("estado", "erro", "perfil", "marcacoes", "intervalo_pre_assinalado", "totais", "divergencias",
                    "diferencas_gemini", "ponto_britanico", "analise", "contagens", "scores_dimensao", "score_geral",
                    "requer_revisao", "modelo_gemini", "modelo_jev", "versao_prompt_gemini", "versao_prompt_jev",
                    "custo", "atualizado_em")


def campos_por_documento(conn, ids: list[int]) -> dict[int, dict]:
    """documento_id -> {campo: valor}, em uma consulta só."""
    if not ids:
        return {}
    out: dict[int, dict] = {}
    for doc_id, campo, valor in conn.execute(
            "SELECT documento_id, campo, valor FROM documento_campos WHERE documento_id = ANY(%s) ORDER BY campo",
            (ids,)):
        out.setdefault(doc_id, {})[campo] = valor
    return out


def extras_documento(
    campos: dict,
    nome_arquivo: str,
    ini: int,
    fim: int,
    criado_em,
    nome_padronizado: str | None = None,
) -> dict:
    """Campos aditivos expostos pelas respostas de documento."""
    # CPF, RG e PIS saem mascarados; o nome segue visível (decisão: a tela de revisão precisa dele)
    return {
        "campos": mascarar_campos(campos),
        "pessoa": campos.get("nome_funcionario") or campos.get("nome"),
        "nome_arquivo": nome_padronizado or nome_arquivo,
        "nome_original": nome_arquivo,
        "n_paginas": fim - ini + 1,
        "processado_em": criado_em,
    }


def obter_documento(documento_id: int) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        d = conn.execute(
            "SELECT d.id, d.lote_id, d.ordem, d.pagina_ini, d.pagina_fim, d.estado, d.tipo, d.confianca, "
            "d.segmentacao_ambigua, d.tipo_original, d.revisor, d.revisado_em, d.motivo_revisao, d.probabilidades, "
            "l.nome_arquivo, l.criado_em, d.nome_padronizado "
            "FROM documento d JOIN lote l ON l.id = d.lote_id WHERE d.id = %s", (documento_id,)
        ).fetchone()
        if d is None:
            raise HTTPException(404, "documento não encontrado")
        paginas = conn.execute(
            "SELECT numero, texto FROM pagina WHERE documento_id = %s ORDER BY numero", (documento_id,)
        ).fetchall()
        campos = campos_por_documento(conn, [documento_id]).get(documento_id, {})
    return {
        "id": d[0], "lote_id": d[1], "ordem": d[2], "pagina_ini": d[3], "pagina_fim": d[4], "estado": d[5],
        "tipo": d[6], "confianca": d[7], "segmentacao_ambigua": d[8],
        "tipo_original": d[9], "revisor": d[10], "revisado_em": d[11], "motivo_revisao": d[12],
        "probabilidades": d[13],
        **extras_documento(campos, d[14], d[3], d[4], d[15], d[16]),
        "paginas": [
            {"numero": n, "imagem_url": f"/lotes/{d[1]}/paginas/{n}/imagem", "texto": mascarar_documentos(t)}
            for n, t in paginas
        ],
    }


def obter_analise_ponto(documento_id: int) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute("SELECT tipo FROM documento WHERE id = %s", (documento_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "documento não encontrado")
        row = conn.execute(f"SELECT {', '.join(_COLUNAS_ANALISE)} FROM analise_ponto WHERE documento_id = %s",
                           (documento_id,)).fetchone()
    if row is None:
        if doc[0] == "folha_ponto":
            return {"documento_id": documento_id, "estado": "pendente"}
        raise HTTPException(404, "documento não é uma folha de ponto analisada")
    return mascarar_estrutura({"documento_id": documento_id, **dict(zip(_COLUNAS_ANALISE, row))})


SEM_TIPO = "sem_tipo"


def listar_documentos(empresa_id: int | None = None, falhou: bool | None = None) -> dict:
    """Documentos agrupados pelo campo `tipo` (uma consulta só). Falha = estado 'erro'."""
    condicoes, args = [], []
    if empresa_id is not None:
        condicoes.append("l.empresa_id = %s")
        args.append(empresa_id)
    if falhou is True:
        condicoes.append("d.estado = 'erro'")
    elif falhou is False:
        condicoes.append("d.estado <> 'erro'")
    where = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    with psycopg.connect(config.DATABASE_URL) as conn:
        if empresa_id is not None and conn.execute(
                "SELECT 1 FROM empresa WHERE id = %s", (empresa_id,)).fetchone() is None:
            raise HTTPException(404, "empresa não encontrada")
        rows = conn.execute(
            "SELECT d.id, d.lote_id, d.ordem, d.pagina_ini, d.pagina_fim, d.estado, d.tipo, d.confianca, "
            f"l.empresa_id, l.nome_arquivo, l.criado_em, d.nome_padronizado FROM documento d JOIN lote l ON l.id = d.lote_id {where} "
            "ORDER BY d.lote_id, d.ordem",
            args,
        ).fetchall()
        campos = campos_por_documento(conn, [r_[0] for r_ in rows])
    grupos: dict[str, list] = {}
    for id_, lote_id, ordem, ini, fim, estado, tipo, conf, emp, nome_arq, criado, nome_pad in rows:
        grupos.setdefault(tipo or SEM_TIPO, []).append(
            {"id": id_, "lote_id": lote_id, "ordem": ordem, "pagina_ini": ini, "pagina_fim": fim,
             "estado": estado, "tipo": tipo, "confianca": conf, "empresa_id": emp,
             **extras_documento(campos.get(id_, {}), nome_arq, ini, fim, criado, nome_pad)})
    ordem_tipos = [*config.TIPOS, config.TIPO_DESCONHECIDO, SEM_TIPO]
    # tipo fora da lista (não esperado) vai depois dos conhecidos, antes de sem_tipo
    chaves = sorted(grupos, key=lambda t: (ordem_tipos.index(t) if t in ordem_tipos else len(config.TIPOS) + 1, t))
    return {"grupos": [{"tipo": t, "total": len(grupos[t]), "documentos": grupos[t]} for t in chaves]}


def atualizar_tipo(documento_id: int, revisao: Revisao) -> dict:
    """Corrige o tipo em qualquer estado, exceto 'segmentado' e 'erro'. tipo_original só é gravado se ainda NULL."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        atual = conn.execute(
            "SELECT estado, tipo, lote_id FROM documento WHERE id = %s FOR UPDATE", (documento_id,)).fetchone()
        if atual is None:
            raise HTTPException(404, "documento não encontrado")
        if atual[0] in ("segmentado", "erro"):
            raise HTTPException(409, f"documento em estado '{atual[0]}' não aceita alteração de tipo")
        conn.execute(
            "UPDATE documento SET estado = 'revisado', tipo_original = COALESCE(tipo_original, tipo), "
            "tipo = %s, revisor = %s, revisado_em = now() WHERE id = %s",
            (revisao.tipo, revisao.revisor, documento_id))
        atualizar_nome_padronizado(conn, documento_id)
    limpar_cancelado(atual[2], r)  # revisão humana vale mesmo após um cancelamento do lote; nunca levanta
    if revisao.tipo == "folha_ponto" and atual[1] != "folha_ponto":
        enfileirar_analise(documento_id, r)  # nunca levanta
    enfileirar_extracao(documento_id, r)  # depois do commit; nunca levanta
    return obter_documento(documento_id)


def excluir_documento(documento_id: int) -> None:
    """Apaga só a linha de `documento`. analise_ponto e documento_campos caem por ON DELETE CASCADE;
    `pagina.documento_id` vira NULL (páginas e texto permanecem). Arquivos em disco e `lote.docs_pendentes`
    não são tocados; por isso lote em andamento (fan-in e filas em uso) recusa com 409."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT l.estado FROM documento d JOIN lote l ON l.id = d.lote_id WHERE d.id = %s FOR UPDATE OF d",
            (documento_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "documento não encontrado")
        if row[0] not in ("concluido", "erro"):
            raise HTTPException(409, f"lote em andamento (estado '{row[0]}'); aguarde a conclusão para excluir")
        conn.execute("DELETE FROM documento WHERE id = %s", (documento_id,))


def atualizar_campos(documento_id: int, corpo: AtualizacaoCampos) -> dict:
    """String não vazia -> upsert com origem 'humano'; null -> remove o campo. Qualquer estado de documento."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM documento WHERE id = %s FOR UPDATE", (documento_id,)).fetchone() is None:
            raise HTTPException(404, "documento não encontrado")
        for nome, valor in corpo.campos.items():
            if valor is None:
                conn.execute("DELETE FROM documento_campos WHERE documento_id = %s AND campo = %s",
                             (documento_id, nome))
            else:
                conn.execute(
                    "INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, %s, %s, 'humano') "
                    "ON CONFLICT (documento_id, campo) DO UPDATE SET valor = EXCLUDED.valor, "
                    "origem = EXCLUDED.origem, atualizado_em = now()",
                    (documento_id, nome, valor.strip()))
        atualizar_nome_padronizado(conn, documento_id)
    return obter_documento(documento_id)


def _recortar_paginas_pdf(pdf_origem: Path, pagina_ini: int, pagina_fim: int) -> bytes:
    """Extrai o intervalo [pagina_ini, pagina_fim] (1-based) de um PDF usando poppler-utils."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        padrao = str(tmp / "page_%d.pdf")
        try:
            subprocess.run(
                ["pdfseparate", "-f", str(pagina_ini), "-l", str(pagina_fim), str(pdf_origem), padrao],
                check=True,
                capture_output=True,
            )
            paginas = sorted(tmp.glob("page_*.pdf"), key=lambda p: int(p.stem.split("_")[1]))
            if not paginas:
                raise HTTPException(500, "falha ao extrair páginas do documento")
            if len(paginas) == 1:
                return paginas[0].read_bytes()
            destino = tmp / "saida.pdf"
            subprocess.run(
                ["pdfunite", *[str(p) for p in paginas], str(destino)],
                check=True,
                capture_output=True,
            )
            return destino.read_bytes()
        except subprocess.CalledProcessError as exc:
            raise HTTPException(500, f"erro ao gerar PDF do documento: {exc}") from exc


def download_documento(documento_id: int) -> tuple[bytes, str]:
    """Retorna (bytes_pdf, nome_padronizado) recortando apenas as páginas do documento."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT d.lote_id, d.pagina_ini, d.pagina_fim, d.tipo, d.nome_padronizado, l.nome_arquivo, e.nome "
            "FROM documento d "
            "JOIN lote l ON l.id = d.lote_id "
            "LEFT JOIN empresa e ON e.id = l.empresa_id "
            "WHERE d.id = %s",
            (documento_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "documento não encontrado")
        campos = campos_por_documento(conn, [documento_id]).get(documento_id, {})

    lote_id, ini, fim, tipo, nome_pad, nome_orig, nome_emp = row
    nome_final = nome_pad or gerar_nome_padronizado(
        tipo,
        campos,
        documento_id=documento_id,
        nome_empresa_lote=nome_emp,
        nome_original=nome_orig,
    )
    pdf_origem = Path(config.DATA_DIR) / f"lote_{lote_id}" / "original.pdf"
    if not pdf_origem.exists():
        raise HTTPException(404, "arquivo PDF original do lote não encontrado")
    return _recortar_paginas_pdf(pdf_origem, ini, fim), nome_final
