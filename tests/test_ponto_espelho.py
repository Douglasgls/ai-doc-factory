"""espelho_incompleto (Portaria MTP 671/2021, art. 84): o Gemini (mockado) só diz o que aparece; o código decide."""
import pytest

from app import analise, ponto, prompts
from app.ponto import BASE_LEGAL_ESPELHO, CAMPOS_ESPELHO, apurar_folha, conferir_espelho
from tests.test_analise import REGULAR, _gemini, _jev, client, doc, rede  # noqa: F401
from tests.test_ponto import PERFIL, regular

TODOS = {c: True for c in CAMPOS_ESPELHO}


def _com(**mudancas):
    return {**TODOS, **mudancas}


def test_campos_sao_so_os_do_art_84():
    assert list(CAMPOS_ESPELHO) == [
        "empregador_nome", "empregador_cnpj_cpf",                                                      # inciso I
        "trabalhador_nome", "trabalhador_cpf", "trabalhador_data_admissao", "trabalhador_cargo_funcao",  # II
        "data_emissao", "periodo",                                                                     # III
        "horario_jornada_contratual",                                                                  # IV
        "marcacoes",                                                                                   # V
        "duracao_jornadas"]                                                                            # VI
    assert {i for i, _ in CAMPOS_ESPELHO.values()} == {"I", "II", "III", "IV", "V", "VI"}
    assert "espelho_incompleto" in ponto.TIPOS_DIVERGENCIA


@pytest.mark.parametrize("tipo,campos,situacao,ausentes", [
    ("espelho_eletronico", TODOS, "completo", []),
    ("espelho_eletronico", _com(trabalhador_cpf=False, data_emissao=False), "incompleto", ["trabalhador_cpf", "data_emissao"]),
    ("espelho_eletronico", _com(trabalhador_cpf=None), "nao_verificado", []),          # ilegível não é ausente
    ("espelho_eletronico", _com(trabalhador_cpf=None, periodo=False), "incompleto", ["periodo"]),
    ("espelho_eletronico", {}, "nao_verificado", []),
    ("registro_manual_ou_mecanico", _com(trabalhador_cpf=False), "nao_aplicavel", ["trabalhador_cpf"]),  # art. 84 é do eletrônico
    ("indeterminado", _com(trabalhador_cpf=False), "nao_verificado", ["trabalhador_cpf"]),
    ("valor_inventado", _com(trabalhador_cpf=False), "nao_verificado", ["trabalhador_cpf"]),
    ("espelho_eletronico", "lixo", "nao_verificado", []),
    ("espelho_eletronico", _com(trabalhador_cpf="nao"), "nao_verificado", []),          # só False explícito conta
])
def test_conferir_espelho(tipo, campos, situacao, ausentes):
    r = conferir_espelho(tipo, campos)
    assert (r["situacao"], r["campos_ausentes"]) == (situacao, ausentes)
    assert r["tipo_registro"] in ponto.TIPOS_REGISTRO


def test_apuracao_gera_uma_divergencia_com_os_campos_e_a_base_legal():
    r = apurar_folha([regular("2025-11-04")], PERFIL, espelho={
        "tipo_registro": "espelho_eletronico", "campos": _com(trabalhador_cpf=False, duracao_jornadas=False)})
    assert r["divergencias"] == [{
        "tipo": "espelho_incompleto", "data": None, "minutos": None, "base_legal": BASE_LEGAL_ESPELHO,
        "detalhe": "campos ausentes no espelho: trabalhador_cpf (inciso II), duracao_jornadas (inciso VI)",
        "campos_ausentes": ["trabalhador_cpf", "duracao_jornadas"]}]
    assert r["espelho"]["situacao"] == "incompleto"


def test_apuracao_sem_divergencia_quando_completo_manual_ou_nao_informado():
    completo = apurar_folha([regular("2025-11-04")], PERFIL, espelho={"tipo_registro": "espelho_eletronico", "campos": TODOS})
    assert completo["divergencias"] == [] and completo["espelho"]["situacao"] == "completo"
    manual = apurar_folha([regular("2025-11-04")], PERFIL, espelho={
        "tipo_registro": "registro_manual_ou_mecanico", "campos": _com(trabalhador_cpf=False)})
    assert manual["divergencias"] == [] and manual["espelho"]["situacao"] == "nao_aplicavel"
    sem = apurar_folha([regular("2025-11-04")], PERFIL)
    assert sem["divergencias"] == [] and sem["espelho"] is None


# ---------- pipeline com o Gemini mockado ----------

def _rodar(doc, rede, **extra):  # noqa: F811
    rede["gemini"].append(_gemini(REGULAR, **extra))
    rede["jev"].append(lambda corpo: _jev(corpo, {}))
    analise.analisar_documento({"documento_id": doc})
    return client.get(f"/documentos/{doc}/analise-ponto").json()


def test_pipeline_espelho_incompleto_presente(doc, rede):  # noqa: F811
    corpo = _rodar(doc, rede, tipo_registro="espelho_eletronico",
                   campos_espelho=_com(trabalhador_data_admissao=False, horario_jornada_contratual=False))
    (d,) = [x for x in corpo["divergencias"] if x["tipo"] == "espelho_incompleto"]
    assert d["campos_ausentes"] == ["trabalhador_data_admissao", "horario_jornada_contratual"]
    assert d["base_legal"] == BASE_LEGAL_ESPELHO and d["data"] is None and d["minutos"] is None
    assert corpo["totais"]["espelho"] == {
        "tipo_registro": "espelho_eletronico", "situacao": "incompleto",
        "campos_ausentes": ["trabalhador_data_admissao", "horario_jornada_contratual"], "campos_nao_lidos": []}
    assert corpo["versao_prompt_gemini"] == prompts.VERSAO_PROMPT_PONTO_GEMINI == "gemini-ponto-v4"
    # o Gemini é perguntado pelos campos (booleanos) e instruído a não decidir a divergência
    pedido = rede["corpos"]["gemini"][0]
    props = pedido["generationConfig"]["responseSchema"]["properties"]
    assert set(props["campos_espelho"]["properties"]) == set(CAMPOS_ESPELHO)
    assert all(p == {"type": "BOOLEAN", "nullable": True} for p in props["campos_espelho"]["properties"].values())
    assert props["tipo_registro"]["enum"] == list(ponto.TIPOS_REGISTRO)
    texto = pedido["contents"][0]["parts"][0]["text"]
    assert "nem espelho_incompleto" in texto and all(f"`{c}`" in texto for c in CAMPOS_ESPELHO)
    # a divergência não muda as contagens enviadas ao Jev (o score não considera o espelho)
    assert "espelho" not in str(rede["corpos"]["jev"][0]["state"]["contagens"])


# Um caso por teste: a resposta do Gemini fica em cache por prompt, e o prompt é o mesmo nos três.
@pytest.mark.parametrize("extra,situacao,tipo", [
    ({"tipo_registro": "espelho_eletronico", "campos_espelho": TODOS}, "completo", "espelho_eletronico"),
    ({}, "nao_verificado", "indeterminado"),  # resposta sem os campos novos
    ({"tipo_registro": "espelho_eletronico", "campos_espelho": {"trabalhador_cpf": "false"}}, "nao_verificado",
     "espelho_eletronico"),  # fora do formato (texto em vez de booleano): não lido, nunca ausente
    ({"tipo_registro": "registro_manual_ou_mecanico", "campos_espelho": _com(trabalhador_cpf=False)}, "nao_aplicavel",
     "registro_manual_ou_mecanico"),
])
def test_pipeline_sem_divergencia_de_espelho(doc, rede, extra, situacao, tipo):  # noqa: F811
    corpo = _rodar(doc, rede, **extra)
    assert corpo["divergencias"] == []
    assert (corpo["totais"]["espelho"]["situacao"], corpo["totais"]["espelho"]["tipo_registro"]) == (situacao, tipo)
