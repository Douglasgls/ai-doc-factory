"""Cálculo determinístico da análise de folha de ponto (Goal 6). Sem LLM, sem banco nas contas.

Tudo aqui é APOIO À AUDITORIA, não parecer jurídico. Convenção coletiva e acordo de compensação
podem alterar os limites do perfil padrão. Escalas especiais (12x36 etc.) não são tratadas.

Formato de entrada (o que o Gemini extrai), uma lista com um item por dia:
    {"data": "2025-11-03", "pares": [["08:00", "12:00"], ["12:30", "20:30"]]}
Cada marcação é "HH:MM" (mesmo dia da data), "HH:MM+1" (dia seguinte, para saída após a meia-noite)
ou um datetime ISO completo. Dia sem pares é folga. "HH:MM" de saída menor ou igual à entrada NÃO é
interpretado como virada de dia: vira marcacao_invalida (ambíguo); a virada precisa vir como "+1".

Perfil: dict {parametro: {"valor": número, "base_legal": texto, "vigencias"?: [{"desde": "AAAA-MM-DD", "valor",
"base_legal"}]}}, como devolvido por carregar_perfil. "valor" é o de base; cada item de "vigencias" (em ordem de
data) vale a partir de "desde". As datas vêm do banco (perfil_jornada.vigente_desde), nunca do código.

Vigência por data (função `vigente`):
- regras do dia (jornada diária, tolerância, horas extras, intervalo, noturno): vale o valor vigente NA DATA do dia;
- interjornada: o vigente no dia em que a segunda jornada começa (a data da divergência);
- regras da semana (duração semanal e repouso semanal): a semana é de segunda a domingo e vale, para a semana
  INTEIRA, o valor vigente no seu ÚLTIMO dia (o domingo). Uma semana que atravessa uma mudança (por exemplo
  14 a 20/12/2026) é avaliada pela regra nova: o total só se completa, e o limite só é ultrapassado, com a regra
  nova já em vigor. DECISÃO DE PROJETO, não está no texto da EC 141 (que não diz como tratar a semana de transição).

Base legal conferida em 15/11/2026 no texto compilado do Planalto (CF e CLT) e na Portaria MTP 671/2021
compilada em 21/07/2026 (gov.br/trabalho-e-emprego). Regra por regra:
- 8h diárias: CLT art. 58, caput; CF art. 7º, XIII.
- 44h semanais: NÃO está na CLT; vinha da CF art. 7º, XIII. A EC 141, de 16/10/2026 (DOU de 16/10/2026, edição
  extra; conferida em 15/11/2026), mudou o inciso para 40h com redução progressiva (art. 6º: "2 (dois) meses após
  a publicação", 42h; "1 (um) ano após o decurso do prazo" anterior, 40h). No perfil clt_padrao: 2640 min até
  15/12/2026, 2520 a partir de 16/12/2026 e 2400 a partir de 16/12/2027 (migração 0006).
- Repouso semanal: CLT art. 67 (24h consecutivas) e, a partir de 16/12/2026, CF art. 7º, XV, na redação da EC 141:
  "repouso semanal remunerado de 2 (dois) dias, um dos quais preferencialmente aos domingos" (em vigor "após
  decorridos 2 (dois) meses" da publicação, art. 10, I). Ver a leitura adotada em `_dias_de_repouso`.
- Contratos com a administração pública (EC 141, art. 9º): sem regra automática; usam perfil próprio.
- Tolerância: CLT art. 58, § 1º (variações de até 5 min, limite de 10 min diários).
- Até 2h extras por dia: CLT art. 59, caput. Adicional de 50%: CF art. 7º, XVI; CLT art. 59, § 1º (não usado
  nas contas: o código não calcula valores em dinheiro; idem o adicional noturno de 20%, CLT art. 73, caput).
- Interjornada de 11h consecutivas: CLT art. 66. Descanso semanal de 24h consecutivas: CLT art. 67.
- Intrajornada: CLT art. 71, caput (mais de 6h: um intervalo de no mínimo 1h) e § 1º (mais de 4h até 6h: 15 min).
- Noturno: CLT art. 73, § 2º (22h às 5h), § 1º (hora de 52min30s), § 4º (horário misto: só as horas noturnas) e
  § 5º (prorrogação do trabalho noturno; ver `_prorrogacao_noturna`).
- Registro: CLT art. 74, § 2º (anotação de entrada e saída; pré-assinalação do repouso permitida);
  Portaria MTP 671/2021, art. 74 (registro fiel; vedada marcação automática com horário predeterminado),
  art. 84 (conteúdo mínimo do espelho) e art. 93 (registro manual: vedada a mera assinalação do horário contratual).
"""
from collections import Counter
from statistics import median
from datetime import date, datetime, time, timedelta

# --- Configuração única dos limites que NÃO vêm do perfil legal. Valores iniciais, NÃO calibrados. ---
CONFIG_PONTO = {
    "britanico_variacao_max_min": 5,   # variação máxima (máx - mín) por marcação para considerar "uniforme"
    "britanico_min_dias": 10,          # abaixo disso, não conclui
    "britanico_fracao_min_dias": 0.9,  # fração de dias "uniformes" a partir da qual há sinal (não calibrado)
    "falta_intervalo_pequena_max_min": 10,  # faltas de intervalo até este valor contam como "pequenas" para o Jev
    "total_declarado_tolerancia_min": 0,  # diferença aceita entre o total declarado na folha e o recalculado
    "conf_min_dimensao": 0.5,          # confiança mínima do Jev por dimensão no score
}

# Vocabulário único de tipos de divergência (o Gemini é instruído a usar exatamente estes nomes).
TIPOS_DIVERGENCIA = (
    "horas_extras_acima_limite", "semana_acima_limite", "intervalo_intrajornada_insuficiente",
    "interjornada_insuficiente", "descanso_semanal_ausente", "marcacao_invalida", "total_declarado_divergente",
)

BASE_LEGAL_REGISTRO = "CLT art. 74; Portaria MTP 671/2021"


def montar_perfil(linhas):
    """Linhas (parametro, valor, base_legal, vigente_desde) -> {parametro: {valor, base_legal, vigencias?}}.

    A linha com vigente_desde NULL é o valor de base e é obrigatória para cada parâmetro (ValueError sem ela);
    as demais viram "vigencias", em ordem de data.
    """
    perfil, datadas = {}, {}
    for parametro, valor, base_legal, desde in linhas:
        if desde is None:
            perfil[parametro] = {"valor": float(valor), "base_legal": base_legal}
        else:
            datadas.setdefault(parametro, []).append(
                {"desde": desde.isoformat(), "valor": float(valor), "base_legal": base_legal})
    for parametro, itens in datadas.items():
        if parametro not in perfil:
            raise ValueError(f"parâmetro '{parametro}' sem valor de base (vigente_desde nulo)")
        perfil[parametro]["vigencias"] = sorted(itens, key=lambda v: v["desde"])
    return perfil


def carregar_perfil(conn, perfil="clt_padrao"):
    """Lê o perfil da tabela perfil_jornada (conn psycopg). Devolve o formato de `montar_perfil`."""
    rows = conn.execute(
        "SELECT parametro, valor, base_legal, vigente_desde FROM perfil_jornada WHERE perfil = %s", (perfil,)
    ).fetchall()
    if not rows:
        raise ValueError(f"perfil '{perfil}' não encontrado")
    return montar_perfil(rows)


def vigente(perfil, parametro, dia):
    """(valor, base_legal) do parâmetro na data `dia`: a última vigência com `desde` <= dia, ou o valor de base."""
    item = perfil[parametro]
    valor, base_legal = item["valor"], item["base_legal"]
    for v in item.get("vigencias") or ():  # em ordem de data
        if date.fromisoformat(v["desde"]) <= dia:
            valor, base_legal = v["valor"], v["base_legal"]
    return valor, base_legal


def _regras(perfil, dia):
    """({parametro: valor}, {parametro: base_legal}) vigentes na data."""
    pares = {k: vigente(perfil, k, dia) for k in perfil}
    return {k: v[0] for k, v in pares.items()}, {k: v[1] for k, v in pares.items()}


# ---------------------------------------------------------------- marcações

class _Invalida(Exception):
    pass


def _data(valor):
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        raise _Invalida(f"data inválida: {valor!r}")


def _marca(dia, texto):
    if texto is None or str(texto).strip() == "":
        return None
    s = str(texto).strip()
    try:
        if "T" in s:
            iso = datetime.fromisoformat(s)
            if iso.tzinfo is not None:  # misturar com horários sem fuso lançaria TypeError
                raise _Invalida(f"horário com fuso não suportado: {texto!r}")
            return iso
        mais = s.endswith("+1")
        hh, mm = s[:-2].split(":") if mais else s.split(":")
        base = datetime.combine(dia, time(int(hh), int(mm)))
        return base + timedelta(days=1) if mais else base
    except ValueError:
        raise _Invalida(f"horário ilegível: {texto!r}")


def _pares_do_dia(item):
    """Devolve (data, [(entrada, saida)]) ou levanta _Invalida com o motivo.

    A entrada vem de LLM: qualquer formato inesperado vira _Invalida, nunca outra exceção.
    """
    if not isinstance(item, dict):
        raise _Invalida("item do dia não é um objeto")
    dia = _data(item.get("data"))
    lista = item.get("pares") or []
    if not isinstance(lista, (list, tuple)):
        raise _Invalida("pares não é uma lista")
    pares = []
    for par in lista:
        if not isinstance(par, (list, tuple)) or len(par) != 2:
            raise _Invalida("par de marcações malformado")
        ent, sai = _marca(dia, par[0]), _marca(dia, par[1])
        if ent is None and sai is None:
            continue
        if ent is None:
            raise _Invalida("saída sem entrada")
        if sai is None:
            raise _Invalida("entrada sem saída")
        if sai <= ent:
            raise _Invalida("saída antes (ou igual) da entrada")
        pares.append((ent, sai))
    for (_, s1), (e2, _) in zip(pares, pares[1:]):
        if e2 < s1:
            raise _Invalida("pares sobrepostos ou fora de ordem")
    return dia, pares


def _minutos(delta):
    return delta.total_seconds() / 60


def _noturno_real(pares, ini_min, fim_min):
    """Minutos reais dentro de [ini, fim) de cada dia (janela vira o dia). Considera a janela do dia anterior."""
    total = 0.0
    for ent, sai in pares:
        d = ent.date() - timedelta(days=1)
        while d <= sai.date():
            ini = datetime.combine(d, time()) + timedelta(minutes=ini_min)
            fim = datetime.combine(d + timedelta(days=1), time()) + timedelta(minutes=fim_min)
            total += max(0.0, _minutos(min(sai, fim) - max(ent, ini)))
            d += timedelta(days=1)
    return total


def _prorrogacao_noturna(pares, p):
    """Minutos reais de prorrogação do trabalho noturno depois do fim do horário noturno (CLT art. 73, § 5º).

    O texto do § 5º é só: "Às prorrogações do trabalho noturno aplica-se o disposto neste capítulo" (conferido em
    15/11/2026 no texto compilado do Planalto). Ele não define "prorrogação". CONDIÇÃO USADA (decisão de projeto, a
    leitura mais estrita: jornada cumprida integralmente no horário noturno e emendada depois das 5h), as três juntas:
      1. nenhum minuto do dia foi trabalhado antes do início do horário noturno (a jornada não é mista no começo;
         horário misto segue o § 4º);
      2. o trabalho dentro do horário noturno, já com a hora reduzida, completa a jornada diária normal
         (jornada_diaria_min), admitida a tolerância diária (tolerancia_dia_min). Das 22h às 5h são 7h de relógio,
         que em horas de 52min30s dão exatamente 8h;
      3. o par de marcações que contém o fim do horário noturno continua depois dele, sem interrupção: os minutos
         desse par depois das 5h são a prorrogação e contam como noturnos (hora de 52min30s).
    Trabalho retomado depois de um intervalo posterior às 5h NÃO entra. Jornada noturna com intervalo dentro do
    horário noturno (ex.: 22h-2h e 3h-7h) NÃO satisfaz a condição 2 e fica sem prorrogação: é um mínimo, não um teto.
    """
    if not pares:
        return 0.0
    base = datetime.combine(pares[0][0].date(), time())
    for inicio_dia in (base - timedelta(days=1), base):  # janela que começou na véspera e a que começa no dia
        ini = inicio_dia + timedelta(minutes=p["noturno_inicio_min"])
        fim = inicio_dia + timedelta(days=1, minutes=p["noturno_fim_min"])
        if pares[0][0] < ini or pares[0][0] >= fim:
            continue
        noturno = sum(max(0.0, _minutos(min(s, fim) - max(e, ini))) for e, s in pares)
        if noturno / p["hora_noturna_min"] * 60 < p["jornada_diaria_min"] - p["tolerancia_dia_min"]:
            continue
        return sum(_minutos(s - fim) for e, s in pares if e < fim < s)
    return 0.0


def _dias_de_repouso(seg, spans):
    """Dias de calendário da semana (segunda a domingo) sem nenhum minuto de trabalho.

    CF art. 7º, XV (redação da EC 141/2026): "repouso semanal remunerado de 2 (dois) dias, um dos quais
    preferencialmente aos domingos". AMBÍGUO: o texto não diz se os dias são consecutivos, não define "dia" e não
    fixa a janela. Leitura mais literal adotada: "semanal" = dentro da semana de segunda a domingo; "dia" = dia de
    calendário (0h às 24h) sem trabalho; os 2 dias NÃO precisam ser consecutivos. Um dia em que termina a jornada
    noturna da véspera tem trabalho e não conta. O domingo não é verificado. O regime compensatório por convenção
    ou acordo coletivo (art. 7º, § 2º, da CF) não é tratado: fica para o perfil próprio do contrato.
    """
    livres = 0
    for n in range(7):
        ini = datetime.combine(seg + timedelta(days=n), time())
        fim = ini + timedelta(days=1)
        if not any(e < fim and s > ini for e, s in spans):
            livres += 1
    return livres


# ---------------------------------------------------------------- apuração

def apurar_folha(marcacoes, perfil, previstos=None, intervalo_pre_assinalado=False, horario_contratual=None,
                 totais_declarados=None):
    """Apura minutos e divergências. Devolve {"dias": [...], "totais": {...}, "divergencias": [...]}.

    previstos (opcional): {"2025-11-03": ["08:00", "12:00", ...]} com os horários contratuais, na ordem
    das marcações; habilita a conferência da tolerância de 5 min por marcação. Sem ele, só vale o teto diário.

    intervalo_pre_assinalado: a CLT art. 74, § 2º, permite a pré-assinalação do período de repouso
    (redação dada pela Lei 13.874/2019; conferido no texto compilado do Planalto). Quando verdadeiro,
    um dia com um único par de marcações NÃO gera intervalo_intrajornada_insuficiente, porque o intervalo
    não foi registrado e não dá para verificá-lo; esses dias saem em "intervalos_nao_verificados".

    horario_contratual (opcional): lista de pares [["09:00","13:00"],["14:00","18:00"]] lida da folha. Vira o
    previsto de cada dia com o MESMO número de marcações (previstos explícito por data tem prioridade). Nos demais
    dias vale só o teto diário; o resultado registra isso em "tolerancia_por_marcacao".

    Hora noturna reduzida (CLT art. 73, § 1º; a Portaria MTP 671/2021, art. 84, VI, manda a duração da jornada
    considerar o horário noturno reduzido): cada 52min30s trabalhados entre 22h e 5h contam como 60 min. As horas
    extras do dia e o total da semana usam essa jornada computada (jornada_computada_min); trabalhado_min segue
    sendo o tempo de relógio. Em jornada mista só a parte noturna é reduzida (art. 73, § 4º). O intervalo
    intrajornada continua medido em tempo de relógio. A prorrogação após as 5h (art. 73, § 5º) também conta
    com a hora reduzida, nas condições de `_prorrogacao_noturna` (prorrogacao_noturna_min, fora de noturno_real_min).

    Os valores do perfil são os vigentes em cada data (ver o topo do módulo): o dia pela sua data e a semana pelo
    seu último dia. O resultado traz "semanas", com o limite aplicado a cada uma e a data de referência.

    totais_declarados (opcional): {"total_horas_min": n|None, "horas_extras_min": n|None} como declarado na folha.
    total_horas: compara com o trabalhado recalculado em tempo de relógio OU com a jornada computada (com a hora
    noturna reduzida); só diverge se não bater com nenhum dos dois. horas_extras: o declarado não gera divergência quando bate
    (dentro de CONFIG_PONTO["total_declarado_tolerancia_min"]) com o recalculado SEM tolerância (extras_bruto_min)
    OU COM a tolerância do art. 58, § 1º (extras_min_com_tolerancia), pois a folha pode ter aplicado qualquer
    dos dois critérios. Se não bate com nenhum, gera total_declarado_divergente com a menor diferença entre os dois
    e o detalhe cita ambos os valores. Os dois valores e os flags de igualdade ficam em totais.declarados.
    """
    previstos = previstos or {}
    divs, dias, nao_verificados = [], {}, []
    contrato, motivo_contrato = None, "sem_horario_contratual"
    if horario_contratual:
        try:
            if not all(isinstance(par, (list, tuple)) and len(par) == 2 for par in horario_contratual):
                raise _Invalida("formato")
            contrato = [h for par in horario_contratual for h in par]
            [_marca(date(2000, 1, 3), h) for h in contrato]  # valida o formato dos horários
            motivo_contrato = None
        except _Invalida:
            contrato, motivo_contrato = None, "horario_contratual_ilegivel"
    dias_com_previsto = dias_sem_previsto = 0

    def div(tipo, dia, minutos, base_legal, detalhe="", campo=None):
        d = {"tipo": tipo, "data": dia.isoformat() if dia else None, "minutos": minutos,
             "base_legal": base_legal, "detalhe": detalhe}
        if campo:
            d["campo"] = campo
        divs.append(d)

    for item in marcacoes:
        try:
            dia, pares = _pares_do_dia(item)
        except _Invalida as e:
            try:
                dia_ref = _data(item.get("data")) if isinstance(item, dict) else None
            except _Invalida:
                dia_ref = None
            divs.append({"tipo": "marcacao_invalida", "data": dia_ref.isoformat() if dia_ref else None,
                         "minutos": None, "base_legal": BASE_LEGAL_REGISTRO, "detalhe": str(e)})
            continue
        if dia in dias:
            div("marcacao_invalida", dia, None, BASE_LEGAL_REGISTRO, "data duplicada; segunda ocorrência ignorada")
            continue

        p, base = _regras(perfil, dia)  # regras do dia: as vigentes na data
        trabalhado = sum(_minutos(s - e) for e, s in pares)
        gaps = [_minutos(e2 - s1) for (_, s1), (e2, _) in zip(pares, pares[1:])]
        intervalo, maior_intervalo = sum(gaps), max(gaps, default=0.0)
        # Hora noturna reduzida (CLT art. 73, § 1º): cada hora_noturna_min (52,5) reais entre 22h e 5h conta 60 min.
        noturno = _noturno_real(pares, p["noturno_inicio_min"], p["noturno_fim_min"])
        noturno_computado = round(noturno / p["hora_noturna_min"] * 60, 2)
        prorrogacao = _prorrogacao_noturna(pares, p)  # art. 73, § 5º: também com a hora reduzida
        prorrogacao_computada = round(prorrogacao / p["hora_noturna_min"] * 60, 2)
        # jornada mista: só a parte noturna (e a prorrogação, quando houver) reduz
        computada = round(trabalhado - noturno - prorrogacao + noturno_computado + prorrogacao_computada, 2)
        bruto = computada - p["jornada_diaria_min"]

        # Tolerância (CLT art. 58, § 1º: "variações de horário no registro de ponto não excedentes de cinco
        # minutos, observado o limite máximo de dez minutos diários"). O excesso diário até tolerancia_dia_min
        # (e, se houver horários previstos, cada marcação dentro de tolerancia_marcacao_min) não conta.
        # INTERPRETAÇÃO (não está na lei; é a da Súmula 366 do TST, a confirmar): ultrapassado o limite, conta
        # o excesso INTEIRO, não só o que passa de 10 min. O limite diário é aplicado ao excesso líquido do dia,
        # não à soma das variações de cada marcação (também a confirmar).
        # Sem horários previstos não dá para medir a variação por marcação, então só o teto diário é aplicado.
        dentro = 0 < bruto <= p["tolerancia_dia_min"]
        prev = previstos.get(dia.isoformat()) or contrato
        flat = [m for par in pares for m in par]
        if flat:
            if isinstance(prev, (list, tuple)) and len(prev) == len(flat):
                dias_com_previsto += 1
            else:
                dias_sem_previsto += 1
        if dentro and isinstance(prev, (list, tuple)) and len(prev) == len(flat):
            try:
                alvo = [_marca(dia, h) for h in prev]
            except _Invalida:
                alvo = None  # previsto ilegível: cai no teto diário
            dentro = alvo is None or all(abs(_minutos(m - a)) <= p["tolerancia_marcacao_min"] for m, a in zip(flat, alvo))
        extras = 0.0 if (bruto <= 0 or dentro) else bruto

        dias[dia] = {
            "data": dia.isoformat(), "pares": pares, "trabalhado_min": trabalhado,
            "jornada_computada_min": computada, "extras_min": extras, "extras_bruto_min": max(0.0, bruto),
            "intervalo_min": intervalo, "maior_intervalo_min": maior_intervalo,
            "noturno_real_min": noturno, "noturno_computado_min": noturno_computado,
            "prorrogacao_noturna_min": prorrogacao, "prorrogacao_noturna_computada_min": prorrogacao_computada,
        }

        if extras > p["extras_max_dia_min"]:
            div("horas_extras_acima_limite", dia, round(extras - p["extras_max_dia_min"], 2), base["extras_max_dia_min"],
                f"{extras:g} min extras no dia")
        # Intrajornada (CLT art. 71): "jornada" = minutos efetivamente trabalhados, em tempo de relógio.
        # O caput exige "um intervalo" de no mínimo 1h; o fracionamento só é admitido no § 5º (transporte
        # coletivo, por convenção). Por isso vale o MAIOR intervalo do dia, não a soma dos intervalos.
        if trabalhado > p["intervalo_longo_acima_min"]:
            exigido = p["intervalo_longo_min"]
            ref = base["intervalo_longo_min"]
        elif trabalhado > p["intervalo_curto_acima_min"]:
            exigido = p["intervalo_curto_min"]
            ref = base["intervalo_curto_min"]
        else:
            exigido = 0
        if exigido and intervalo_pre_assinalado and len(pares) == 1:
            nao_verificados.append(dia.isoformat())
        elif exigido and maior_intervalo < exigido:
            div("intervalo_intrajornada_insuficiente", dia, exigido - maior_intervalo, ref,
                f"maior intervalo de {maior_intervalo:g} min, exigido {exigido:g}")

    # Semana = segunda a domingo (ISO). Passar da duração semanal numa semana parcial já é conclusivo (dias
    # ausentes só somariam). Dias com marcação inválida ficam fora da soma, então é um mínimo. A jornada que
    # atravessa a meia-noite conta inteira no dia (e na semana) em que começou. A soma usa a jornada computada
    # (hora noturna reduzida). É a duração NORMAL da semana (CF art. 7º, XIII): passar dela indica hora extra
    # semanal, que sozinha não é ilícita. O limite é o vigente no ÚLTIMO dia da semana (domingo), para a semana
    # inteira (decisão de projeto; ver o topo do módulo).
    semanas, resumo_semanas = {}, []
    for dia, d in dias.items():
        semanas.setdefault(dia - timedelta(days=dia.weekday()), []).append(d)
    for seg, ds in sorted(semanas.items()):
        ref = seg + timedelta(days=6)
        limite, ref_legal = vigente(perfil, "jornada_semanal_min", ref)
        total = round(sum(d["jornada_computada_min"] for d in ds), 2)
        resumo_semanas.append({"inicio": seg.isoformat(), "regra_vigente_em": ref.isoformat(),
                               "jornada_computada_min": total, "limite_semanal_min": limite, "dias_informados": len(ds)})
        if total > limite:
            div("semana_acima_limite", seg, round(total - limite, 2), ref_legal,
                f"semana iniciada em {seg.isoformat()}: {total:g} min (limite de {limite:g} min vigente em "
                f"{ref.isoformat()})")

    # Interjornada (CLT art. 66): só entre dias consecutivos (inclusive na virada de mês ou de ano), ambos com
    # marcações válidas e com trabalho. Com um dia faltando na folha entre os dois, não conclui.
    for dia in sorted(dias):
        prox = dias.get(dia + timedelta(days=1))
        d = dias[dia]
        if prox and d["pares"] and prox["pares"]:
            descanso = _minutos(prox["pares"][0][0] - d["pares"][-1][1])
            exigido, ref_legal = vigente(perfil, "interjornada_min", dia + timedelta(days=1))
            if descanso < exigido:
                div("interjornada_insuficiente", dia + timedelta(days=1), exigido - descanso,
                    ref_legal, f"descanso de {descanso:g} min entre jornadas")

    # Descanso semanal (CLT art. 67): só conclui se a semana tem os 7 dias informados e todos válidos
    # (dia de folga = data presente com pares vazios). Maior intervalo sem trabalho dentro da janela
    # segunda 00:00 -> segunda seguinte 00:00; descanso que atravessa a semana é cortado na borda
    # (limitação conhecida). Não verifica se o descanso cai no domingo.
    # Com repouso_semanal_dias >= 1 vigente no domingo da semana (CF art. 7º, XV, redação da EC 141/2026), a regra
    # passa a ser a contagem de dias de repouso (`_dias_de_repouso`); a falta sai em minutos como dias x 24h.
    avaliadas = 0
    todos_os_pares = [s for d in dias.values() for s in d["pares"]]
    for seg, ds in sorted(semanas.items()):
        if len(ds) < 7:
            continue
        avaliadas += 1
        ref = seg + timedelta(days=6)
        exigidos, ref_legal = vigente(perfil, "repouso_semanal_dias", ref)
        if exigidos >= 1:
            livres = _dias_de_repouso(seg, todos_os_pares)
            if livres < exigidos:
                div("descanso_semanal_ausente", seg, (exigidos - livres) * 1440, ref_legal,
                    f"{livres} dia(s) de repouso na semana, exigidos {exigidos:g} (regra vigente em {ref.isoformat()})")
            continue
        exigido, ref_legal = vigente(perfil, "descanso_semanal_min", ref)
        ini = datetime.combine(seg, time())
        fim = ini + timedelta(days=7)
        spans = sorted(s for d in ds for s in d["pares"])
        cursor, melhor = ini, 0.0
        for e, s in spans:
            melhor = max(melhor, _minutos(max(e, ini) - cursor))
            cursor = max(cursor, min(s, fim))
        melhor = max(melhor, _minutos(fim - cursor))
        if melhor < exigido:
            div("descanso_semanal_ausente", seg, exigido - melhor, ref_legal,
                f"maior descanso contínuo na semana: {melhor:g} min")

    lista = [dias[k] for k in sorted(dias)]
    for d in lista:
        d.pop("pares")
    extras_bruto = sum(d["extras_bruto_min"] for d in lista)
    extras_tol = sum(d["extras_min"] for d in lista)
    trabalhado_total = sum(d["trabalhado_min"] for d in lista)
    computada_total = round(sum(d["jornada_computada_min"] for d in lista), 2)
    decl = totais_declarados if isinstance(totais_declarados, dict) else {}
    invalidos = sum(1 for x in divs if x["tipo"] == "marcacao_invalida")
    declarados = {"total_horas_min": None, "horas_extras_min": None, "comparado": False,
                  "extras_bruto_min": extras_bruto, "extras_min_com_tolerancia": extras_tol,
                  "extras_declarado_igual_ao_bruto": None, "extras_declarado_igual_ao_com_tolerancia": None}
    tol_decl = CONFIG_PONTO["total_declarado_tolerancia_min"]
    for campo, chave, calculado in (("total_horas", "total_horas_min", trabalhado_total),
                                    ("horas_extras", "horas_extras_min", extras_bruto)):
        v = decl.get(chave)
        v = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        declarados[chave] = v
        if v is None or invalidos:  # sem declarado, ou dias inválidos tornam o recalculado um mínimo
            continue
        declarados["comparado"] = True
        if campo == "horas_extras":
            menor = min(abs(v - extras_bruto), abs(v - extras_tol))
            if menor > tol_decl:
                div("total_declarado_divergente", None, menor, BASE_LEGAL_REGISTRO,
                    f"{campo}: declarado {v:g} min, recalculado {extras_bruto:g} min sem tolerância "
                    f"e {extras_tol:g} min com tolerância", campo=campo)
        elif min(abs(v - calculado), abs(v - computada_total)) > tol_decl:
            # a folha pode declarar o total em tempo de relógio ou com a hora noturna reduzida
            noturna = "" if computada_total == calculado else f" ({computada_total:g} min com a hora noturna reduzida)"
            div("total_declarado_divergente", None, min(abs(v - calculado), abs(v - computada_total)),
                BASE_LEGAL_REGISTRO, f"{campo}: declarado {v:g} min, recalculado {calculado:g} min{noturna}",
                campo=campo)
    if declarados["horas_extras_min"] is not None and not invalidos:
        declarados["extras_declarado_igual_ao_bruto"] = abs(declarados["horas_extras_min"] - extras_bruto) <= tol_decl
        declarados["extras_declarado_igual_ao_com_tolerancia"] = (
            abs(declarados["horas_extras_min"] - extras_tol) <= tol_decl)
    totais = {
        "trabalhado_min": trabalhado_total,
        "jornada_computada_min": computada_total,
        "extras_min": extras_tol,
        "extras_bruto_min": extras_bruto,
        "noturno_real_min": sum(d["noturno_real_min"] for d in lista),
        "noturno_computado_min": round(sum(d["noturno_computado_min"] for d in lista), 2),
        "prorrogacao_noturna_min": sum(d["prorrogacao_noturna_min"] for d in lista),
        "prorrogacao_noturna_computada_min": round(sum(d["prorrogacao_noturna_computada_min"] for d in lista), 2),
        "dias_validos": len(lista),
        "dias_invalidos": invalidos,
    }
    return {"dias": lista, "totais": totais, "divergencias": divs,
            "intervalo_pre_assinalado": bool(intervalo_pre_assinalado),
            "intervalos_nao_verificados": nao_verificados, "semanas_avaliadas_descanso": avaliadas,
            "semanas": resumo_semanas,
            "tolerancia_por_marcacao": {
                "aplicada": dias_com_previsto > 0, "dias_com_horario_previsto": dias_com_previsto,
                "dias_sem_horario_previsto": dias_sem_previsto,
                "motivo_nao_aplicada": None if dias_com_previsto else (
                    motivo_contrato or "numero_de_marcacoes_diferente_do_horario_contratual")},
            "horario_contratual": horario_contratual or [], "declarados": declarados}


# ---------------------------------------------------------------- ponto britânico

def detectar_ponto_britanico(marcacoes, variacao_max_min=None, min_dias=None, fracao_min=None):
    """SINAL DE RISCO, não prova de fraude nem conclusão jurídica.

    Horários de entrada e saída praticamente idênticos todos os dias são indício de registro não
    fidedigno. Base normativa conferida: a Portaria MTP 671/2021 veda, no registro manual, "a mera assinalação
    do horário contratual" (art. 93) e, no eletrônico, a marcação automática com horários predeterminados
    (art. 74, II). A Súmula 338, III, do TST (registros uniformes) é jurisprudência e NÃO foi conferida em
    fonte oficial: não citar no resultado. Para cada posição de marcação calcula-se a mediana do minuto-do-dia;
    um dia é "uniforme" se TODAS as suas marcações ficam a até variacao_max_min da mediana da posição.
    Há sinal quando a fração de dias uniformes é >= fracao_min (assim um dia atípico não esconde um mês
    uniforme). Só considera dias válidos com trabalho e o número de marcações mais comum; com menos
    de min_dias não conclui (sinal_risco None).
    """
    variacao_max_min = CONFIG_PONTO["britanico_variacao_max_min"] if variacao_max_min is None else variacao_max_min
    min_dias = CONFIG_PONTO["britanico_min_dias"] if min_dias is None else min_dias
    fracao_min = CONFIG_PONTO["britanico_fracao_min_dias"] if fracao_min is None else fracao_min
    linhas = []
    for item in marcacoes:
        try:
            dia, pares = _pares_do_dia(item)
        except _Invalida:
            continue
        if pares:
            midnight = datetime.combine(dia, time())
            linhas.append([_minutos(m - midnight) for par in pares for m in par])
    nulo = {"conclusivo": False, "sinal_risco": None, "fracao_uniforme": None}
    if not linhas:
        return {**nulo, "dias": 0}
    n = Counter(len(x) for x in linhas).most_common(1)[0][0]
    linhas = [x for x in linhas if len(x) == n]
    if len(linhas) < min_dias:
        return {**nulo, "dias": len(linhas)}
    medianas = [median(c) for c in zip(*linhas)]
    uniformes = sum(all(abs(m - md) <= variacao_max_min for m, md in zip(x, medianas)) for x in linhas)
    fracao = uniformes / len(linhas)
    return {"conclusivo": True, "sinal_risco": fracao >= fracao_min, "dias": len(linhas),
            "fracao_uniforme": round(fracao, 4)}


# ---------------------------------------------------------------- Gemini x código

def comparar_com_gemini(apurado, divergencias_gemini):
    """Vale o cálculo do código; cada diferença é registrada. Casa por (tipo, data).

    Devolve {"divergencias": as do código, "diferencas": [{tipo, data, minutos_codigo, minutos_gemini, motivo}]}.
    motivo: so_codigo | so_gemini | minutos_diferentes. Os nomes de tipo do Gemini precisam usar o mesmo
    vocabulário do código (garantido pelo prompt, fora deste módulo).
    """
    divs = apurado["divergencias"] if isinstance(apurado, dict) else apurado
    cod = {(d["tipo"], d["data"], d.get("campo")): d for d in divs}
    gem = {(d.get("tipo"), d.get("data"), None): d for d in divergencias_gemini or []}
    diferencas = []
    for chave in sorted(set(cod) | set(gem), key=lambda k: (str(k[1]), str(k[0]), str(k[2]))):
        c, g = cod.get(chave), gem.get(chave)
        mc = c["minutos"] if c else None
        mg = g.get("minutos") if g else None
        if c and not g:
            motivo = "so_codigo"
        elif g and not c:
            motivo = "so_gemini"
        elif mc != mg:
            motivo = "minutos_diferentes"
        else:
            continue
        diferencas.append({"tipo": chave[0], "data": chave[1], "campo": chave[2], "minutos_codigo": mc,
                           "minutos_gemini": mg, "motivo": motivo})
    return {"divergencias": list(divs), "diferencas": diferencas}


# ---------------------------------------------------------------- score

def score_geral(respostas_jev, conf_min=None, nao_avaliadas=None):
    """Máximo entre as dimensões normalizadas (sem média: problema grave não pode ser diluído).

    respostas_jev: {dimensao: {"score": int, "n_niveis": int, "confianca": float}}.
    normalizado = score / (n_niveis - 1). Dimensão com confiança < conf_min fica indeterminada (não entra
    no máximo) e força revisão. Se houver indeterminada, o score geral é um piso; se todas, é None.
    nao_avaliadas: {dimensao: motivo} das dimensões que o código não mandou ao Jev por falta de dados. Ficam
    marcadas (nao_avaliada), não entram no máximo e, sozinhas, não forçam revisão (reservada à confiança baixa);
    o score geral é parcial e a lista vai em "nao_avaliadas".
    """
    conf_min = CONFIG_PONTO["conf_min_dimensao"] if conf_min is None else conf_min
    dims, normalizados = {}, []
    for nome, r in respostas_jev.items():
        n, s = r["n_niveis"], r["score"]
        if n < 2 or not 0 <= s <= n - 1:
            raise ValueError(f"dimensão {nome}: score {s} inválido para {n} níveis")
        if r["confianca"] < conf_min:
            dims[nome] = {"normalizado": None, "indeterminada": True, "nao_avaliada": False}
        else:
            v = s / (n - 1)
            dims[nome] = {"normalizado": v, "indeterminada": False, "nao_avaliada": False}
            normalizados.append(v)
    indeterminadas = [k for k, v in dims.items() if v["indeterminada"]]
    for nome, motivo in (nao_avaliadas or {}).items():
        dims[nome] = {"score": None, "confianca": None, "n_niveis": None, "probabilidades": None,
                      "normalizado": None, "indeterminada": True, "nao_avaliada": True, "motivo": motivo}
    return {"score_geral": max(normalizados) if normalizados else None, "dimensoes": dims,
            "indeterminadas": indeterminadas, "nao_avaliadas": list(nao_avaliadas or {}),
            "requer_revisao": bool(indeterminadas) or not respostas_jev}


# ---------------------------------------------------------------- contagens para o Jev

def resumir_contagens(apuracao, britanico):
    """Contagens por dimensão, TODAS calculadas aqui: o Jev só julga a situação, não conta."""
    divs = apuracao["divergencias"]

    def de(tipo):
        return [d for d in divs if d["tipo"] == tipo]

    def maior(lista):
        return max((d["minutos"] for d in lista), default=0)

    pequena = CONFIG_PONTO["falta_intervalo_pequena_max_min"]
    validos = len(apuracao["dias"])
    invalidos = apuracao["totais"]["dias_invalidos"]
    extras, semanas = de("horas_extras_acima_limite"), de("semana_acima_limite")
    intra, inter = de("intervalo_intrajornada_insuficiente"), de("interjornada_insuficiente")
    sem_descanso = de("descanso_semanal_ausente")
    total_div = de("total_declarado_divergente")
    decl_inf = [k for k in ("total_horas_min", "horas_extras_min") if apuracao["declarados"][k] is not None]
    if britanico.get("sinal_risco") is None:
        sinal = "inconclusivo"
    else:
        sinal = "sinal_de_ponto_britanico" if britanico["sinal_risco"] else "sem_sinal"
    return {
        "horas_extras": {
            "dias_analisados": validos, "dias_acima_do_limite_diario": len(extras),
            "fracao_dos_dias_acima_do_limite": round(len(extras) / validos, 2) if validos else 0,
            "maior_excesso_diario_min": maior(extras), "semanas_acima_do_limite_semanal": len(semanas),
            "total_horas_extras_min": apuracao["totais"]["extras_min"],
        },
        "intervalos": {
            "dias_analisados": validos, "dias_com_intervalo_intrajornada_insuficiente": len(intra),
            "maior_falta_de_intervalo_min": maior(intra),
            "dias_com_falta_de_intervalo_pequena": sum(d["minutos"] <= pequena for d in intra),
            "dias_com_falta_de_intervalo_maior": sum(d["minutos"] > pequena for d in intra),
            "limite_da_falta_pequena_min": pequena,
            "dias_com_interjornada_menor_que_11h": len(inter), "maior_falta_de_interjornada_min": maior(inter),
            "dias_com_intervalo_nao_verificado": len(apuracao.get("intervalos_nao_verificados", [])),
        },
        "descanso": {
            "semanas_completas_avaliadas": apuracao.get("semanas_avaliadas_descanso", 0),
            "semanas_sem_descanso_semanal": len(sem_descanso), "maior_falta_de_descanso_min": maior(sem_descanso),
        },
        "registro": {
            "dias_com_marcacao_valida": validos, "dias_com_marcacao_invalida": invalidos,
            "ponto_britanico": sinal, "fracao_de_dias_com_horario_uniforme": britanico.get("fracao_uniforme"),
            "totais_declarados_informados": bool(decl_inf),
            "totais_declarados_divergentes": len(total_div),
            "maior_diferenca_do_total_declarado_min": maior(total_div),
        },
    }
