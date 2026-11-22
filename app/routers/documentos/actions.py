from pathlib import Path
import subprocess
import tempfile

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import config
from app.anonimizacao import mascarar_campos, mascarar_documentos, mascarar_estrutura
from app.analise import enfileirar_analise
from app.escopo import filtro_contrato, filtro_lote
from app.extracao import enfileirar_extracao
from app.models import AnalisePonto, Contrato, Documento, DocumentoCampo, Lote, Pagina, Prestador, Tomador
from app.renomeacao import atualizar_nome_padronizado_sessao, gerar_nome_padronizado
from app.routers import r
from app.routers.auth.actions import UsuarioContexto
from app.routers.documentos.schemas import AtualizacaoCampos
from app.routers.revisao.schemas import Revisao

_COLUNAS_ANALISE = ("estado", "erro", "perfil_nome", "perfil", "marcacoes", "intervalo_pre_assinalado", "totais", "divergencias",
                    "diferencas_gemini", "ponto_britanico", "analise", "contagens", "scores_dimensao", "score_geral",
                    "requer_revisao", "modelo_gemini", "modelo_jev", "versao_prompt_gemini", "versao_prompt_jev",
                    "custo", "atualizado_em")


def campos_por_documento(session: Session, ids: list[int]) -> dict[int, dict]:
    """documento_id -> {campo: valor}, em uma consulta só."""
    if not ids:
        return {}
    out: dict[int, dict] = {}
    for doc_id, campo, valor in session.execute(
            select(DocumentoCampo.documento_id, DocumentoCampo.campo, DocumentoCampo.valor)
            .where(DocumentoCampo.documento_id.in_(ids)).order_by(DocumentoCampo.campo)):
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


def obter_documento(session: Session, documento_id: int) -> dict:
    d = session.execute(
        select(Documento.id, Documento.lote_id, Documento.ordem, Documento.pagina_ini, Documento.pagina_fim,
               Documento.estado, Documento.tipo, Documento.confianca, Documento.segmentacao_ambigua,
               Documento.tipo_original, Documento.revisor, Documento.revisado_em, Documento.motivo_revisao,
               Documento.probabilidades, Lote.nome_arquivo, Lote.criado_em, Documento.nome_padronizado)
        .join(Lote, Lote.id == Documento.lote_id).where(Documento.id == documento_id)).first()
    if d is None:
        raise HTTPException(404, "documento não encontrado")
    paginas = session.execute(
        select(Pagina.numero, Pagina.texto).where(Pagina.documento_id == documento_id).order_by(Pagina.numero)).all()
    campos = campos_por_documento(session, [documento_id]).get(documento_id, {})
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


def obter_analise_ponto(session: Session, documento_id: int) -> dict:
    doc = session.execute(select(Documento.tipo).where(Documento.id == documento_id)).first()
    if doc is None:
        raise HTTPException(404, "documento não encontrado")
    row = session.execute(select(*(getattr(AnalisePonto, c) for c in _COLUNAS_ANALISE))
                          .where(AnalisePonto.documento_id == documento_id)).first()
    if doc[0] != "folha_ponto":  # mesmo que sobre uma linha antiga, o tipo atual manda
        raise HTTPException(404, "documento não é uma folha de ponto analisada")
    if row is None:
        return {"documento_id": documento_id, "estado": "pendente"}
    return mascarar_estrutura({"documento_id": documento_id, **dict(zip(_COLUNAS_ANALISE, row))})


SEM_TIPO = "sem_tipo"


def listar_documentos(session: Session, contrato_id: int | None = None, falhou: bool | None = None, *,
                      usuario: UsuarioContexto) -> dict:
    """Documentos agrupados pelo campo `tipo` (uma consulta só). Falha = estado 'erro'.
    `usuario` é obrigatório: o filtro de escopo vai no SQL; contrato_id fora do escopo é 404, como o inexistente."""
    consulta = (select(Documento.id, Documento.lote_id, Documento.ordem, Documento.pagina_ini, Documento.pagina_fim,
                       Documento.estado, Documento.tipo, Documento.confianca, Lote.contrato_id, Lote.nome_arquivo,
                       Lote.criado_em, Documento.nome_padronizado)
                .join(Lote, Lote.id == Documento.lote_id).where(filtro_lote(usuario)))
    if contrato_id is not None:
        consulta = consulta.where(Lote.contrato_id == contrato_id)
    if falhou is True:
        consulta = consulta.where(Documento.estado == "erro")
    elif falhou is False:
        consulta = consulta.where(Documento.estado != "erro")
    if contrato_id is not None:
        if session.execute(
                select(Contrato.id).join(Tomador, Tomador.id == Contrato.tomador_id)
                .join(Prestador, Prestador.id == Contrato.prestador_id)
                .where(Contrato.id == contrato_id, filtro_contrato(usuario))).first() is None:
            raise HTTPException(404, "contrato não encontrado")
    rows = session.execute(consulta.order_by(Documento.lote_id, Documento.ordem)).all()
    campos = campos_por_documento(session, [r_[0] for r_ in rows])
    grupos: dict[str, list] = {}
    for id_, lote_id, ordem, ini, fim, estado, tipo, conf, contrato, nome_arq, criado, nome_pad in rows:
        grupos.setdefault(tipo or SEM_TIPO, []).append(
            {"id": id_, "lote_id": lote_id, "ordem": ordem, "pagina_ini": ini, "pagina_fim": fim,
             "estado": estado, "tipo": tipo, "confianca": conf, "contrato_id": contrato,
             **extras_documento(campos.get(id_, {}), nome_arq, ini, fim, criado, nome_pad)})
    ordem_tipos = [*config.TIPOS, config.TIPO_DESCONHECIDO, SEM_TIPO]
    # tipo fora da lista (não esperado) vai depois dos conhecidos, antes de sem_tipo
    chaves = sorted(grupos, key=lambda t: (ordem_tipos.index(t) if t in ordem_tipos else len(config.TIPOS) + 1, t))
    return {"grupos": [{"tipo": t, "total": len(grupos[t]), "documentos": grupos[t]} for t in chaves]}


def atualizar_tipo(session: Session, documento_id: int, revisao: Revisao, revisor: str) -> dict:
    """Corrige o tipo em qualquer estado, exceto 'segmentado' e 'erro'. tipo_original só é gravado se ainda NULL."""
    atual = session.execute(select(Documento.estado, Documento.tipo, Documento.lote_id)
                            .where(Documento.id == documento_id).with_for_update()).first()
    if atual is None:
        raise HTTPException(404, "documento não encontrado")
    if atual[0] in ("segmentado", "erro"):
        raise HTTPException(409, f"documento em estado '{atual[0]}' não aceita alteração de tipo")
    session.execute(update(Documento).where(Documento.id == documento_id).values(
        estado="revisado", tipo_original=func.coalesce(Documento.tipo_original, Documento.tipo),
        tipo=revisao.tipo, revisor=revisor, revisado_em=func.now()
    ).execution_options(synchronize_session=False))
    atualizar_nome_padronizado_sessao(session, documento_id)
    analisar = False
    if revisao.tipo != "folha_ponto":  # análise de ponto obsoleta: o documento deixou de ser folha de ponto
        session.execute(delete(AnalisePonto).where(AnalisePonto.documento_id == documento_id)
                        .execution_options(synchronize_session=False))
    else:  # enfileira se ainda não há análise concluída (ex.: em_revisao com sugestão folha_ponto)
        analisar = session.execute(
            select(AnalisePonto.documento_id).where(AnalisePonto.documento_id == documento_id,
                                                    AnalisePonto.estado == "concluida")).first() is None
    session.commit()  # antes de enfileirar: o worker precisa enxergar o estado novo
    # forcar=True: a revisão humana vale mesmo com o lote cancelado (a marca de cancelamento continua)
    if analisar:
        enfileirar_analise(documento_id, r, forcar=True)  # nunca levanta
    enfileirar_extracao(documento_id, r, forcar=True)  # depois do commit; nunca levanta
    return obter_documento(session, documento_id)


def excluir_documento(session: Session, documento_id: int) -> None:
    """Apaga só a linha de `documento`. analise_ponto e documento_campos caem por ON DELETE CASCADE;
    `pagina.documento_id` vira NULL (páginas e texto permanecem). Arquivos em disco e `lote.docs_pendentes`
    não são tocados; por isso lote em andamento (fan-in e filas em uso) recusa com 409."""
    row = session.execute(
        select(Lote.estado).select_from(Documento).join(Lote, Lote.id == Documento.lote_id)
        .where(Documento.id == documento_id).with_for_update(of=Documento)).first()
    if row is None:
        raise HTTPException(404, "documento não encontrado")
    if row[0] not in ("concluido", "erro"):
        raise HTTPException(409, f"lote em andamento (estado '{row[0]}'); aguarde a conclusão para excluir")
    session.execute(delete(Documento).where(Documento.id == documento_id)
                    .execution_options(synchronize_session=False))
    session.commit()


def atualizar_campos(session: Session, documento_id: int, corpo: AtualizacaoCampos, autor: str) -> dict:
    """String não vazia -> upsert com origem 'humano' e `autor` (e-mail do usuário autenticado); null -> remove o campo. Qualquer estado de documento."""
    if session.execute(select(Documento.id).where(Documento.id == documento_id).with_for_update()).first() is None:
        raise HTTPException(404, "documento não encontrado")
    for nome, valor in corpo.campos.items():
        if valor is None:
            session.execute(delete(DocumentoCampo).where(DocumentoCampo.documento_id == documento_id,
                                                         DocumentoCampo.campo == nome)
                            .execution_options(synchronize_session=False))
        else:
            novo = pg_insert(DocumentoCampo).values(documento_id=documento_id, campo=nome, valor=valor.strip(),
                                                    origem="humano", autor=autor)
            session.execute(novo.on_conflict_do_update(
                index_elements=[DocumentoCampo.documento_id, DocumentoCampo.campo],
                set_={"valor": novo.excluded.valor, "origem": novo.excluded.origem, "autor": novo.excluded.autor,
                      "atualizado_em": func.now()}))
    atualizar_nome_padronizado_sessao(session, documento_id)
    session.commit()
    return obter_documento(session, documento_id)


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


def download_documento(session: Session, documento_id: int) -> tuple[bytes, str]:
    """Retorna (bytes_pdf, nome_padronizado) recortando apenas as páginas do documento."""
    row = session.execute(
        select(Documento.lote_id, Documento.pagina_ini, Documento.pagina_fim, Documento.tipo,
               Documento.nome_padronizado, Lote.nome_arquivo, Prestador.razao_social)
        .join(Lote, Lote.id == Documento.lote_id)
        .outerjoin(Contrato, Contrato.id == Lote.contrato_id)
        .outerjoin(Prestador, Prestador.id == Contrato.prestador_id)
        .where(Documento.id == documento_id)).first()
    if row is None:
        raise HTTPException(404, "documento não encontrado")
    campos = campos_por_documento(session, [documento_id]).get(documento_id, {})
    session.commit()  # libera a conexão antes do pdfseparate/pdfunite

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
