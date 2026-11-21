# Document AI Factory

Projeto de hackathon (7 horas). Recebe PDFs de lote com muitas páginas escaneadas, separa cada documento, classifica por tipo, gera OCR pesquisável e manda casos duvidosos para revisão humana.

**Prioridade: fluxo ponta a ponta funcionando antes de qualquer refinamento. Sem over-engineering.**

## Como trabalhamos

- **Supervisão e implementação:** a sessão principal (Opus) só planeja, delega e revisa. A implementação é feita por subagents com `model: sonnet`, um por etapa, em worktree próprio.
- **PRs pequenos:** um PR por entrega, contra `master`. Cada commit tem no máximo ~800 linhas alteradas. Se passar disso, divida. Arquivos gerados e lockfiles não entram nessa conta.
- **Nunca commitar direto na `master`.** Crie uma branch `feat/...`, `fix/...` ou `chore/...`.
- **Sem assinatura nos commits:** não adicione `Co-Authored-By` nem outra linha de atribuição.
- **Não use o agent `gcp`.**
- **Rode de verdade:** nada está pronto sem ter sido executado (`docker compose up`, processar um lote, rodar a avaliação). Mostre a saída real.
- **Pergunte em vez de assumir:** se algo for ambíguo ou depender de informação que você não tem, pare e reporte. Subagents devolvem a dúvida à sessão principal.
- **Não invente métricas:** todo número no README vem de um script que foi rodado.
- **Nunca suba chaves de API nem outros segredos:** o repositório é público. `OPENROUTER_API_KEY`, `GEMINI_API_KEY` e `POSTGRES_PASSWORD` ficam só no `.env`, que está no `.gitignore`.
  - Nunca force a inclusão do `.env` (`git add -f`) nem coloque chaves no código, em testes, em exemplos, no `docker-compose.yml`, em commits ou em PRs.
  - Nunca imprima chaves em logs, saídas de comando ou relatórios. Para conferir uma variável, mostre só o nome.
  - O cache de LLM não pode guardar cabeçalhos de autenticação.
  - Mantenha `.env.example` atualizado, sem valores.
  - Antes de cada commit, revise o que está sendo adicionado com `git diff --cached`.
  - Se uma chave vazar, pare e avise a pessoa responsável, porque ela precisa revogar a chave. Apagar o commit não basta.

### Se estiver atrasado, corte nesta ordem

1. UI Streamlit
2. Correção de fronteiras
3. PDF pesquisável (mantendo a busca por texto)
4. Gemini

Nunca corte o fluxo ponta a ponta nem a avaliação.

## Stack e arquitetura (decidido, não rediscuta)

- Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Docker Compose.
- Serviços: `api` (FastAPI), `worker_ocr_seg` (OCR + segmentação), `worker_classify` (classificação), `ui` (Streamlit, opcional, por último).
- Arquivos em volume local (`/data/lote_<id>/`). Sem S3/MinIO.
- Tudo idempotente: reprocessar um lote ou documento não pode duplicar nem corromper dados.

### Filas (Redis, listas, com ack)

- `BLMOVE fila -> fila:proc`. Remover de `:proc` só após sucesso.
- Retry 3x, depois `dlq`.
- Ao subir, o worker devolve para a fila os jobs presos em `:proc`.
- `segmentar_lote`, payload `{lote_id}`.
- `classificar_documento`, payload `{documento_id}`.

### Fan-in

Coluna `lote.docs_pendentes`, decrementada atomicamente (`UPDATE ... RETURNING`). Em 0, o lote vira `concluido`.

### Estados

- Lote: `recebido`, `ocr`, `classificando`, `concluido`, `erro`.
- Documento: `segmentado`, `classificado`, `em_revisao`, `revisado`, `erro`.

### Tipos documentais

`aso`, `folha_pagamento`, `folha_ponto`, `holerite`, `recibo_ferias`, `atestado_medico`, `contrato_trabalho`.

A lista fica em configuração, em um único lugar, nunca espalhada pelo código.

## Modelos de IA

- **Jev:** classificador principal, só texto, via OpenRouter (`OPENROUTER_API_KEY`, `JEV_MODEL`). Devolve escolha, confiança e probabilidades por opção. **Antes de implementar, faça uma chamada de teste e confirme o formato real da resposta.** Se não houver confiança utilizável, avise e proponha alternativa em vez de inventar.
- **Gemini:** segunda opinião (Google AI Studio, `GEMINI_API_KEY`), com a imagem da primeira página, usado só quando a confiança do Jev for baixa. A confiança autodeclarada do Gemini **não** entra na regra de decisão.
- **Gemini na análise de folha de ponto (Goal 6):** modelo em `GEMINI_ANALISE_MODEL`, padrão `gemini-3.5-flash`. A documentação do Gemini indica esse ID como obsoleto e redirecionado para um modelo mais novo, então registre o modelo realmente devolvido pela API.
- **Jev no score de risco (Goal 6):** usa uma pergunta `Score` do Jev por dimensão de risco, sobre as divergências já apuradas.
- **Toda implementação com Jev segue a skill `building-with-typesafe-jev`.** Leia o `SKILL.md` e o `api-reference.md` dela antes de escrever perguntas. Em resumo:
  - Uma decisão simples por pergunta, com `state` em JSON nomeado e instruções que apontam para ele por caminho.
  - Níveis de `Score` descrevem situações concretas, com uma dimensão cada.
  - `Choice` tem a lista completa mais uma opção de nenhum dos anteriores.
  - Contas, datas e contagens ficam no código.
  - Perguntas, limiares e pesos ficam em um único módulo de constantes.
- Toda decisão de confiança (limiares, roteamento) é feita em código determinístico, não pelo LLM.
- Cache em disco das respostas dos LLMs, com chave = hash da entrada + modelo + prompt, para a demo não depender de rede.
- Em cada classificação, guarde o modelo usado, a versão do prompt e as probabilidades.

## Dados de teste

Gerador de lotes sintéticos: `gerar_lotes.py`, com gabarito `anotacoes.csv` (`lote_id,pagina,inicio_documento,documento_id,tipo,qualidade,observacao`). Verso em branco pertence ao documento anterior (observação `verso_em_branco`).

**Se o gerador não estiver no repositório, peça o caminho. Não o reescreva.**

Os dados sintéticos são otimistas. O README deve registrar que a validação em documentos reais ainda é necessária.

## Ordem de execução

1. Fundação: `docker-compose`, schema SQL, módulo de filas Redis, endpoint de upload. Validar com `docker compose up` e um PDF de teste.
2. Goal 4 (OCR) e Goal 1 (segmentação com regras e TF-IDF), ponta a ponta, sem LLM.
3. Goal 3 com um classificador simples para fechar o fluxo, depois trocar por Jev + Gemini.
4. Goal 5 (roteamento e revisão) e script de avaliação com números reais.
5. Goal 6 (análise de risco das folhas de ponto).
6. Goal 7 (score de conformidade dos documentos).
7. Goal 2 (refinamentos de agrupamento/correção). **Por enquanto, só backend:** não implemente a UI Streamlit nem o serviço `ui` até nova decisão.
8. README com como rodar, arquitetura, resultados medidos e limitações.

## Goals

### Goal 1: Detecção de início e fim de cada documento

Segmentação em cascata:

1. Regras determinísticas: página em branco herda o documento anterior; "Página 1 de N" abre documento; "Página k de N" (k>1) continua.
2. Similaridade TF-IDF entre páginas consecutivas: abaixo de um limiar baixo abre documento novo; acima de um limiar alto continua.
3. Faixa ambígua entre os limiares: pergunta Sim/Não ao LLM ("estas duas páginas pertencem ao mesmo documento?"), enviando o fim da página anterior e o início da atual.
4. Reconciliação final: nenhuma página fica sem documento e os intervalos não se sobrepõem.

**Aceite:** script de avaliação que compara com `anotacoes.csv` e imprime, por documento (não por página), precisão e recall das fronteiras e a taxa de documentos exatos (início e fim corretos). Documentos consecutivos do mesmo tipo precisam estar nos testes.

### Goal 2: Agrupamento de páginas

- Persistir `documento` (lote, ordem, `pagina_ini`, `pagina_fim`) e vincular cada `pagina` ao seu `documento_id`.
- `GET /documentos/{id}`: páginas (imagem + texto), tipo, confiança e status.
- `GET /lotes/{id}`: lista de documentos do lote.
- Corrigir fronteiras na revisão: juntar com o anterior e dividir em uma página, recalculando os intervalos (mínimo viável, se sobrar tempo).

**Aceite:** após processar um lote, é possível abrir cada documento pela API e ver exatamente suas páginas na ordem.

### Goal 3: Classificação por tipo documental

- `worker_classify` consome `classificar_documento`, monta o texto (primeiras páginas, truncado em ~6000 caracteres), chama o Jev e devolve tipo, confiança e probabilidades.
- Confiança abaixo do limiar alto: chama o Gemini com a imagem da primeira página. Se discordarem, vai para revisão.
- Ao final, faz o fan-in do lote.
- Baseline obrigatório: TF-IDF + regressão logística sobre o texto do OCR, treinado nos lotes sintéticos. Reportar lado a lado com o Jev.

**Aceite:** F1 macro e matriz de confusão por tipo, medidos por documento, sobre lotes sintéticos que **não** foram usados para ajustar prompt ou limiares.

### Goal 4: OCR pesquisável

- Rasterizar com `pdf2image` a 150 dpi, OCR com Tesseract (`-l por`), páginas em paralelo.
- Salvar o texto por página no banco.
- Gerar um PDF pesquisável por documento (OCRmyPDF ou camada de texto sobre a imagem). Se não der tempo, entregar a busca no banco e registrar isso claramente.
- `GET /busca?q=`: full-text search do PostgreSQL (configuração `portuguese`), retornando lote, página e trecho destacado.
- O upload (`POST /lotes`) aceita PDF, JPEG, PNG e TIFF (inclusive multipágina); imagens são convertidas para `original.pdf` na chegada.

**Aceite:** buscar uma palavra presente num documento (ex.: nome de um funcionário) retorna a página correta.

### Goal 5: Confiança e fila de revisão humana

Roteamento em código, com limiares em variáveis de ambiente (`CONF_AUTO`, `CONF_MIN`):

- Confiança >= `CONF_AUTO` e sem desacordo entre modelos: `classificado`.
- Entre `CONF_MIN` e `CONF_AUTO`, ou desacordo: `em_revisao` com o tipo sugerido.
- Abaixo de `CONF_MIN`: `em_revisao` com tipo `desconhecido`.
- Segmentação ambígua também pode marcar o documento para revisão.

Demais entregas:

- `GET /revisao` (fila) e `POST /documentos/{id}/revisao` (corrige o tipo; guarda `tipo_original`, revisor e momento).
- Streamlit mínimo: upload de lote, lista de documentos por lote e tela de revisão com a página, o tipo sugerido e um seletor para confirmar ou corrigir.
- Escolher os limiares pela curva cobertura x precisão nos dados de validação e reportar % automático, precisão na parte automática e % em revisão.

**Aceite:** documentos de baixa confiança aparecem na fila, a correção humana muda o status para `revisado` e o relatório de cobertura x precisão é gerado por script.

### Goal 6: Análise de risco das folhas de ponto

Para documentos do tipo `folha_ponto`, encontrar divergências, com foco principal em horas extras, e gerar um score de risco com base na CLT e na Portaria MTP nº 671/2021. O score é **por folha**; o consolidado por funcionário fica fora do escopo por enquanto.

**Perfil padrão:** tabela `perfil_jornada`, criada com um perfil CLT de referência. Cada parâmetro guarda o valor e a base legal. Confira os valores no texto oficial da CLT e da Portaria antes de usar:

| Parâmetro | Referência |
|---|---|
| Jornada diária de 8h e semanal de 44h | CF art. 7º, XIII; CLT art. 58 |
| Tolerância de 5 min por marcação, até 10 min por dia | CLT art. 58, § 1º |
| Até 2h extras por dia | CLT art. 59 |
| Adicional mínimo de 50% sobre a hora extra | CF art. 7º, XVI |
| Intervalo interjornada de 11h | CLT art. 66 |
| Descanso semanal de 24h | CLT art. 67 |
| Intervalo intrajornada: 1h acima de 6h de jornada; 15 min entre 4h e 6h | CLT art. 71 |
| Noturno das 22h às 5h, adicional de 20%, hora de 52min30s | CLT art. 73 |
| Requisitos do registro de ponto e do espelho | CLT art. 74; Portaria MTP 671/2021 |

**Fluxo:**

1. Documento que termina como `folha_ponto`, inclusive por correção humana, entra na fila `analisar_folha_ponto` (payload `{documento_id}`), consumida pelo serviço `worker_analise`. A análise não participa do fan-in do lote.
2. O Gemini recebe o texto do OCR, a imagem das páginas e o perfil padrão e devolve em JSON as marcações por dia, as divergências (tipo, data, minutos, base legal, trecho de evidência) e uma análise breve.
3. O código recalcula os minutos a partir das marcações e compara com o perfil. Quando o resultado não bater com o do Gemini, vale o cálculo do código e a diferença é registrada. O código também detecta o ponto britânico (horários quase idênticos ao longo do período), com limite configurável, como sinal de risco e não como prova de fraude.
4. O Jev recebe as divergências apuradas e a análise e responde uma pergunta `Score` por dimensão (horas extras, intervalos, descanso e registro), em uma única requisição, com níveis concretos. O score geral é calculado em código: cada dimensão é normalizada e o resultado é o **máximo** entre elas, sem média, porque um problema grave não pode ser diluído. Dimensão com confiança baixa fica como indeterminada e manda o documento para revisão.
5. Persistir em `analise_ponto`, uma linha por documento (reprocessar substitui, sem duplicar): perfil usado, marcações, divergências, análise, scores por dimensão, score geral, probabilidades, modelos e versões dos prompts.
6. `GET /documentos/{id}/analise-ponto` devolve o resultado.

O score é apoio à auditoria, não parecer jurídico. A convenção coletiva e o acordo de compensação podem alterar os limites do perfil padrão. O README deve registrar as duas ressalvas.

**Aceite:** uma folha de ponto com horas extras acima do limite gera divergências com data, minutos e base legal, além do score; uma folha regular gera score menor. Não reporte métrica de acurácia sem um gabarito de divergências.

### Goal 7: Score de conformidade dos documentos

Score de 0 a 100 sobre a **empresa prestadora**: a terceirizada que fornece os funcionários para a tomadora. Um lote pode misturar empresas, então o lote não é a unidade. A empresa é identificada pelo CNPJ da prestadora, e seus documentos são reunidos entre lotes. É separado do risco de ponto do Goal 6, que não entra nesta nota. Fica nos 7 tipos atuais. O cálculo é feito em código determinístico; os LLMs só extraem os dados.

**Três níveis, com a mesma fórmula e os mesmos pesos, redistribuindo os critérios que não se aplicam:**

- **Por documento:** Validade e Consistência; Completude não se aplica.
- **Por tipo:** presença do tipo (Completude, se obrigatório), mais Validade e Consistência dos documentos desse tipo.
- **Geral da empresa:** os três critérios sobre todos os documentos.

| Critério | Peso | Regra | Nota do critério |
|---|---|---|---|
| Completude | 40% | Todos os documentos obrigatórios foram enviados | Obrigatórios presentes / obrigatórios |
| Validade | 35% | Documentos vencidos ou dentro da validade | Válidos / analisados com regra de validade |
| Consistência | 25% | Divergências nas informações entre documentos | Campos coerentes / campos comparados |

**Classificação:** 85–100 Regular; 65–84 Atenção; 0–64 Crítico.

**Regras:**

- Documento ausente reduz a pontuação.
- Documento vencido reduz a pontuação.
- Divergências são sinalizadas para conferência e reduzem a nota de Consistência.
- Documento não analisado (`segmentado`, `em_revisao`, `erro` ou com tipo `desconhecido`) fica pendente, sem nota zero automática. A extração de campos roda também para `em_revisao`, para o documento ficar ligado à sua empresa; `segmentado` e `erro` não têm empresa.
- Completude e pendência: um obrigatório faltante conta como pendente somente se a PRÓPRIA empresa tiver documento não analisado, respeitando o tipo: documento em revisão com tipo sugerido conhecido cobre só esse tipo, e com tipo `desconhecido` pode cobrir qualquer faltante. Fora disso o faltante é ausente e desconta. Documento sem empresa não afeta a Completude de nenhuma empresa; aparece só em `sem_empresa` no lote, com o motivo. Empresa sem nenhum obrigatório presente tem Completude 0 de 5, e o score existe.
- Critério sem nada analisável fica pendente, e seu peso é redistribuído entre os demais. Nesse caso, ou quando houver pendências, o score é marcado como `provisorio`. Sem nenhum critério analisável, não há score.
- O score mostra o motivo de cada desconto: critério, documento, regra e pontos descontados.
- A correção humana entra no cálculo: o score é recalculado a partir do estado atual dos documentos.

**Configuração, em um único módulo:** pesos, faixas, tipos obrigatórios e regras de validade.

- Obrigatórios: `aso`, `contrato_trabalho`, `holerite`, `folha_pagamento` e `folha_ponto`. `atestado_medico` e `recibo_ferias` só existem quando há afastamento ou férias, então não contam como ausência.
- Validade: `aso` e `contrato_trabalho` por prazo determinado. Contrato por prazo indeterminado não se aplica, em vez de ficar pendente. Confira o prazo do ASO na NR-7. Documento sem data legível fica pendente. A data de referência é registrada no resultado.
- Consistência: o CNPJ é a chave de agrupamento da empresa e por isso não entra na Consistência; só a razão social é comparada entre os documentos da empresa. Nome, matrícula e data de admissão só são comparados entre documentos do mesmo funcionário (mesmo CPF), nunca entre pessoas diferentes.
- `provisorio`: só com documento não analisado, obrigatório pendente ou critério inteiro pendente. Campo ausente aparece nas pendências, mas não marca o score como provisório.

**Identificação da empresa:** o Gemini extrai o CNPJ e a razão social da prestadora, e o código valida os dígitos verificadores. O contrato do lote (`lote.contrato_id` -> prestador) é fonte cadastrada, não palpite: em lote com contrato, o documento sem CNPJ claro, com CNPJ inválido ou sem distinção entre prestadora e tomadora é ligado ao prestador do contrato (origem `contrato`), e um CNPJ extraído válido e diferente do contrato também liga ao prestador do contrato, com a divergência `cnpj_diferente_do_contrato`, sinalizada para conferência e descontada da Consistência. Em lote sem contrato, o documento sem CNPJ claro, com CNPJ inválido ou sem distinção entre prestadora e tomadora fica pendente, listado no lote, sem ser ligado a uma empresa por palpite.

**Fluxo:** o Gemini extrai a empresa, as datas e os campos de identificação (nome, CPF, matrícula, data de admissão) em JSON, depois da classificação. A extração não participa do fan-in do lote. O código normaliza, compara e calcula. Conferências de texto ambíguas, como variação de nome, podem usar `Noul` do Jev, seguindo a skill. Os dados extraídos ficam em `documento_campos`.

**Endpoints:**

- `GET /empresas`: empresas com o score geral e a classificação.
- `GET /empresas/{cnpj}/conformidade`: os três níveis, com notas por critério, classificação, descontos e pendências.
- `GET /lotes/{id}/conformidade`: as empresas encontradas no lote e os documentos sem empresa.

**Limitação conhecida:** a Completude por empresa só verifica se existe ao menos um documento de cada tipo obrigatório, não se cada funcionário tem o seu. O README deve registrar isso.

**Aceite:** testes cobrem cada regra, os três níveis e cada limite de faixa; em lotes sintéticos, dois CNPJs no mesmo lote geram scores separados, a remoção de um obrigatório, um ASO vencido e um nome divergente do mesmo CPF geram os descontos esperados com o motivo, nomes de CPFs diferentes não geram divergência, e documento pendente não zera a nota. Não reporte métrica de acurácia sem gabarito.
