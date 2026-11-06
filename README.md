# Document AI Factory

Projeto de hackathon. Recebe um PDF de lote com muitas páginas escaneadas (ou uma imagem), faz OCR de cada página, separa os documentos do lote, classifica cada um por tipo documental e envia os casos duvidosos para uma fila de revisão humana. O texto das páginas fica no PostgreSQL e pode ser pesquisado.

Hoje existe apenas o backend (API + workers). O que está pronto, o que é parcial e o que ainda não existe está na seção [Estado atual](#estado-atual).

## Stack e serviços

- Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Docker Compose.
- OCR: Tesseract (`-l por`) sobre páginas rasterizadas a 150 dpi com `pdf2image`/Poppler, 4 páginas em paralelo.
- Classificação: Jev (via OpenRouter) como classificador principal e Gemini como segunda opinião quando a confiança é baixa; ou um classificador por palavras-chave (`CLASSIFICADOR=regras`) que roda sem rede.
- Arquivos do lote em volume Docker (`/data/lote_<id>/`).

| Serviço | Função |
|---|---|
| `api` | FastAPI: upload, consulta, busca e revisão |
| `worker_ocr_seg` | Consome `segmentar_lote`: rasteriza, faz OCR, segmenta em documentos |
| `worker_classify` | Consome `classificar_documento`: classifica, roteia por confiança, fecha o lote |
| `migrate` | One-shot: roda `alembic upgrade head` e sai; `api` e os workers só sobem depois que ele termina com sucesso |
| `worker_extracao` | Consome `extrair_campos`: Gemini extrai empresa (CNPJ e razão social), datas e identificação em `documento_campos` (Goal 7); fora do fan-in do lote |
| `worker_analise` | Consome `analisar_folha_ponto`: Gemini + cálculo em código + Jev, grava `analise_ponto` (Goal 6); fora do fan-in do lote |
| `postgres` | Dados e busca full-text (config `portuguese`) |
| `redis` | Filas (listas, com ack via `BLMOVE`, 3 tentativas e depois `dlq`) |

```
POST /lotes (PDF/imagem)
      |
      v
    api --------> Redis: segmentar_lote
                        |
                        v
                 worker_ocr_seg: rasteriza + OCR (texto por página no Postgres)
                                 segmentação (cascata abaixo)
                        |  um job por documento
                        v
                 Redis: classificar_documento
                        |
                        v
                 worker_classify: classificador -> roteamento por confiança
                        |                |
                 classificado        em_revisao ----> GET /revisao
                        |                             POST /documentos/{id}/revisao
                        v                                      |
              fan-in: lote.docs_pendentes = 0 => lote concluido
```

**Segmentação em cascata** (`app/segmentacao.py`): página em branco herda o documento anterior; "Página 1 de N" abre documento e "Página k de N" (k>1) continua; senão, similaridade TF-IDF entre páginas consecutivas (abaixo de `SEG_SIM_BAIXO` abre, a partir de `SEG_SIM_ALTO` continua); na faixa ambígua pergunta Sim/Não ao Jev (só com `CLASSIFICADOR=jev`). Se o Jev não responde ou fica no meio, o sistema abre documento novo e marca `segmentacao_ambigua`, o que leva o documento à revisão. Os limiares ainda não foram calibrados.

**Roteamento** (`app/roteamento.py`): confiança >= `CONF_AUTO` e sem desacordo entre modelos vira `classificado`; entre `CONF_MIN` e `CONF_AUTO`, ou com desacordo, ou segmentação ambígua, vira `em_revisao` com o tipo sugerido; abaixo de `CONF_MIN`, `em_revisao` com tipo `desconhecido`.

**Tipos documentais** (`app/config.py`): `aso`, `folha_pagamento`, `folha_ponto`, `holerite`, `recibo_ferias`, `atestado_medico`, `contrato_trabalho`.

**Estados.** Lote: `recebido`, `ocr`, `classificando`, `concluido`, `erro`. Documento: `segmentado`, `classificado`, `em_revisao`, `revisado`, `erro`.

## Como rodar

### Pré-requisitos

- Docker com Docker Compose v2.
- `curl`.
- Para o modo com LLM: chaves de OpenRouter (Jev) e Google AI Studio (Gemini). Para o modo sem rede, nenhuma chave.

Testado com Docker 28 e Compose v2.39 no Windows (Git Bash).

### 1. Configurar o `.env`

```bash
cp .env.example .env
```

Edite o `.env`:

- `POSTGRES_PASSWORD` é obrigatória (o `docker compose` falha sem ela). Use uma senha de desenvolvimento.
- `API_PORT` define a porta da API no host (padrão 8000).
- Para rodar sem rede e sem chaves, defina `CLASSIFICADOR=regras`. Com `CLASSIFICADOR=jev` (padrão do `.env.example`), preencha `OPENROUTER_API_KEY`, `JEV_MODEL` e `GEMINI_API_KEY`.

- `AUTH_USUARIO`, `AUTH_SENHA` e `AUTH_SEGREDO` configuram o login do administrador (ver "Autenticação"). **Sem elas o sistema recusa o login (503) e toda rota protegida nega acesso.** Gere o segredo com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

O `.env` está no `.gitignore`. Nunca o versione.

### 2. Subir os serviços

```bash
docker compose up -d --build
docker compose ps
```

Na primeira vez a imagem é construída (instala Tesseract e Poppler). Quando `api`, `postgres` e `redis` estiverem `healthy`:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

(troque `8000` pelo valor de `API_PORT`; os exemplos abaixo usam 8000).

### 3. Enviar um lote e consultar o resultado

```bash
curl -F "arquivo=@meu_lote.pdf" http://localhost:8000/lotes
# {"lote_id":1,"estado":"recebido","existente":false}

curl http://localhost:8000/lotes/1
```

O processamento é assíncrono: repita o `GET /lotes/1` até `"estado":"concluido"` (um lote pequeno leva alguns segundos). A resposta traz os documentos com intervalo de páginas, estado, tipo, confiança e probabilidades. Reenviar o mesmo arquivo não cria outro lote (a identidade é o SHA-256 dos bytes): a API devolve o existente com `"existente":true`.

Exemplo de resposta (lote de 3 páginas, `CLASSIFICADOR=regras`, resumida):

```json
{"id":1,"estado":"concluido","docs_pendentes":0,
 "documentos":[
  {"id":1,"ordem":1,"pagina_ini":1,"pagina_fim":1,"estado":"classificado","tipo":"aso","confianca":1.0},
  {"id":2,"ordem":2,"pagina_ini":2,"pagina_fim":3,"estado":"classificado","tipo":"contrato_trabalho","confianca":1.0}]}
```

Busca por texto e detalhe de um documento:

```bash
curl "http://localhost:8000/busca?q=contrato"
curl http://localhost:8000/documentos/2
```

### 4. Testes

```bash
docker compose exec api python -m pytest tests -q
```

Os testes rodam dentro do container `api`, que tem acesso ao Postgres e ao Redis do Compose. `tests/test_migracoes.py` cria um banco descartável no mesmo servidor e testa `upgrade head` e `downgrade base`.

### 5. Rodar sem rede

Com `CLASSIFICADOR=regras` no `.env`, a classificação usa palavras-chave (`app/classificador_regras.py`) e a segmentação não chama o Jev, então nenhum texto de documento sai da máquina. Ao mudar o `.env`, recrie os serviços: `docker compose up -d`.

### 6. Mudança de schema e dados locais

O schema é versionado com Alembic (`alembic.ini`, `migrations/versions/`). As migrações são SQL cru via `op.execute`/`exec_driver_sql` (o app usa `psycopg` direto, sem models SQLAlchemy). O serviço `migrate` do Compose roda `alembic upgrade head` a cada `docker compose up`, antes da `api` e dos workers; `migrations/env.py` lê `DATABASE_URL` do ambiente. A revisão `0001_baseline` reproduz o schema inicial completo.

Criar uma nova revisão (dentro do container, o arquivo gerado fica na imagem; copie-o para `migrations/versions/` do repositório):

```bash
docker compose run --rm migrate alembic revision -m "descricao curta"
```

Edite `upgrade()`/`downgrade()` com SQL e rebuild (`docker compose up -d --build`). Para aplicar manualmente: `docker compose run --rm migrate alembic upgrade head`; para voltar uma: `alembic downgrade -1`.

**Banco que já existe** (criado pelo antigo `sql/schema.sql`): não rode o baseline de novo, apenas marque-o como aplicado:

```bash
docker compose run --rm migrate alembic stamp head
```

Para recomeçar do zero:

```bash
docker compose down -v
```

O `-v` apaga os volumes: **todos os dados locais** (lotes, documentos, arquivos enviados e o cache de LLM) são perdidos. Para só parar os serviços, use `docker compose down` sem `-v`.

### Frontend

A pasta `frontend/` é um projeto separado do backend (Vite + React + TypeScript + Tailwind v4). Tem tela de login e chama a API com o token (ver `frontend/.env.example`; `VITE_API_PREFIX` fica vazio, a API não tem prefixo). Não faz parte do `docker-compose.yml` e não foi testada para este README.

## Autenticação

Há um único administrador, definido no ambiente (`AUTH_USUARIO`, `AUTH_SENHA`, `AUTH_SEGREDO`; `AUTH_EXPIRA_MIN` é a validade do token em minutos, padrão 480). Não há senha nem segredo padrão: sem as três variáveis, `POST /auth/login` responde 503 e as demais rotas protegidas também negam acesso. Ficam abertos só `GET /health`, `POST /auth/login`, `/docs` e `/openapi.json`.

Para obter o token (substitua pelos seus valores):

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"usuario":"SEU_USUARIO","senha":"SUA_SENHA"}' \
  localhost:8000/auth/login
# {"access_token":"...","token_type":"bearer","expira_em":"..."}

curl -H "Authorization: Bearer $TOKEN" localhost:8000/auth/me
```

O token é um JWT HS256 (claims `sub`, `iat`, `exp`). No `/docs`, use o botão Authorize. Token em query string não é aceito, nem para a imagem da página: o cliente deve enviar o cabeçalho `Authorization`.

## Endpoints

**Todas as rotas abaixo, exceto `GET /health`, exigem `Authorization: Bearer <token>`.** Os exemplos de `curl` da tabela omitem o cabeçalho por brevidade: acrescente `-H "Authorization: Bearer $TOKEN"`.

| Método e rota | Descrição | Exemplo |
|---|---|---|
| `GET /health` | Verifica Postgres e Redis | `curl localhost:8000/health` |
| `POST /lotes` | Envia PDF, JPEG, PNG ou TIFF (multipágina inclusive); imagens viram `original.pdf`. Arquivo inválido: 400. Campo opcional `empresa_id` vincula o lote a uma empresa cadastrada (404 se não existir; 409 se o lote já pertence a outra) | `curl -F "arquivo=@lote.pdf" localhost:8000/lotes` |
| `GET /lotes/{id}` | Estado do lote e lista de documentos (intervalo, tipo, confiança, probabilidades) | `curl localhost:8000/lotes/1` |
| `GET /documentos/{id}` | Documento com tipo, confiança, motivo de revisão e páginas (texto e `imagem_url`); também `campos` (extraídos, campo->valor), `pessoa` (`campos.nome` ou null), `nome_arquivo`, `n_paginas` e `processado_em` (criação do lote) | `curl localhost:8000/documentos/2` |
| `GET /documentos?empresa_id=&falhou=` | Documentos agrupados por tipo (`grupos`; `sem_tipo` para quem não tem); cada item traz também `campos`, `pessoa`, `nome_arquivo`, `n_paginas` e `processado_em`. `empresa_id` filtra pela empresa do lote (404 se não existir); `falhou=true` só estado `erro`, `false` exclui | `curl "localhost:8000/documentos?falhou=false"` |
| `PATCH /documentos/{id}/tipo` | Corrige o tipo (`{"tipo","revisor"}`) em qualquer estado exceto `segmentado` e `erro` (409); vira `revisado`; `tipo_original` guarda o primeiro tipo; dispara análise de ponto e extração como a revisão | `curl -X PATCH -H "Content-Type: application/json" -d '{"tipo":"aso","revisor":"ana"}' localhost:8000/documentos/1/tipo` |
| `DELETE /documentos/{id}` | 204. Apaga só a linha do documento: análise de ponto e campos extraídos caem em cascata; as páginas e o texto permanecem (`documento_id` NULL) e nenhum arquivo em disco é apagado. 409 se o lote está em andamento | `curl -X DELETE localhost:8000/documentos/1` |
| `GET /lotes/{lote_id}/paginas/{n}/imagem` | PNG da página | `curl -o p1.png localhost:8000/lotes/1/paginas/1/imagem` |
| `GET /busca?q=...&limite=20` | Full-text search (`portuguese`); devolve lote, página e trecho com `<b>`, mais `documento_id` (null se a página estiver órfã), `tipo` e `nome_arquivo` | `curl "localhost:8000/busca?q=contrato"` |
| `POST /cadastro-empresas` | Cadastra empresa por nome (`{"nome": "..."}`); 201. Nome vazio: 422; nome repetido (sem diferenciar caixa nem espaços nas pontas): 409 | `curl -H "Content-Type: application/json" -d '{"nome":"Alfa Ltda"}' localhost:8000/cadastro-empresas` |
| `GET /cadastro-empresas` | Lista empresas com seus lotes e documentos (`n_lotes`, `n_documentos`) | `curl localhost:8000/cadastro-empresas` |
| `GET /cadastro-empresas/{id}` | Uma empresa no mesmo formato; 404 se não existir | `curl localhost:8000/cadastro-empresas/1` |
| `GET /revisao` | Fila de documentos `em_revisao`, com tipo sugerido e motivo; também `pagina_ini`, `pagina_fim`, `campos`, `pessoa`, `nome_arquivo`, `n_paginas` e `processado_em` | `curl localhost:8000/revisao` |
| `GET /tipos` | Tipos documentais `[{slug, nome, icone}]` na ordem da configuração (`TIPOS_INFO` em `app/config.py`), sem `desconhecido` | `curl localhost:8000/tipos` |
| `PUT /documentos/{id}/campos` | Corrige campos extraídos (`{"campos": {nome: valor ou null}, "revisor"}`): valor grava com origem `humano`, `null` remove. Nome `^[a-z0-9_]{1,40}$`, valor não vazio até 500 caracteres, `campos` e `revisor` não vazios (422); 404 se não existe; qualquer estado. Devolve o documento | `curl -X PUT -H "Content-Type: application/json" -d '{"campos":{"nome":"Maria"},"revisor":"ana"}' localhost:8000/documentos/1/campos` |
| `GET /documentos/{id}/analise-ponto` | Análise de risco da folha de ponto (Goal 6): marcações, divergências (tipo, data, minutos, base legal, evidência), score por dimensão e score geral (máximo entre as dimensões), modelos e versões dos prompts | `curl localhost:8000/documentos/1/analise-ponto` |
| `GET /empresas` | Empresas prestadoras (CNPJ validado) com score geral de conformidade e classificação (Goal 7) | `curl localhost:8000/empresas` |
| `GET /empresas/{cnpj}/conformidade` | Os três níveis (documento, tipo, geral), notas por critério, classificação, descontos com motivo e pendências | `curl localhost:8000/empresas/12.345.678/0001-95/conformidade` |
| `GET /lotes/{id}/conformidade` | Empresas encontradas no lote e documentos sem empresa, com o motivo | `curl localhost:8000/lotes/1/conformidade` |
| `POST /documentos/{id}/revisao` | Corrige o tipo; o documento vira `revisado` e `tipo_original` guarda o tipo sugerido. 409 se o documento não está em revisão | ver abaixo |

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"tipo":"aso","revisor":"nome_do_revisor"}' \
  localhost:8000/documentos/1/revisao
```

O `tipo` deve ser um dos tipos documentais listados acima. A documentação interativa do FastAPI fica em `/docs`.

## Variáveis de ambiente

Definidas no `.env` (modelo em `.env.example`), repassadas aos containers pelo `docker-compose.yml`. Nenhum valor secreto vai no repositório.

| Variável | Padrão | Uso |
|---|---|---|
| `POSTGRES_USER` | `docfactory` | Usuário do Postgres |
| `POSTGRES_PASSWORD` | (obrigatória) | Senha do Postgres |
| `POSTGRES_DB` | `docfactory` | Nome do banco |
| `API_PORT` | `8000` | Porta da API no host |
| `CONF_AUTO` | `0.85` | Confiança mínima para classificação automática |
| `CONF_MIN` | `0.50` | Abaixo disso o tipo vira `desconhecido` e vai para revisão |
| `CLASSIFICADOR` | `jev` | `jev` (Jev + Gemini) ou `regras` (sem rede) |
| `OPENROUTER_API_KEY` | vazio | Chave do OpenRouter (Jev). Só no `.env` |
| `JEV_MODEL` | vazio | Modelo do Jev. Testado com `typesafe/jev-1.13` |
| `GEMINI_API_KEY` | vazio | Chave do Google AI Studio. Só no `.env` |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Modelo da segunda opinião |
| `AUTH_USUARIO` | vazio | Usuário do administrador. Sem valor, o login responde 503 |
| `AUTH_SENHA` | vazio | Senha do administrador. Só no `.env` |
| `AUTH_SEGREDO` | vazio | Segredo que assina o JWT. Só no `.env` |
| `AUTH_EXPIRA_MIN` | `480` | Validade do token, em minutos |

Também podem ser ajustadas por ambiente (valores em `app/config.py`, não listadas no `.env.example` nem repassadas pelo `docker-compose.yml` atual, então exigem editá-lo): `SEG_SIM_BAIXO`, `SEG_SIM_ALTO`, `SEG_LLM_CONTINUA`, `SEG_LLM_ABRE`, `LLM_TIMEOUT`, `LLM_TENTATIVAS`, `LLM_ESPERA`. As respostas dos LLMs são cacheadas em disco (volume `cache_llm`).

## Estado atual

| Item | Situação | Observação |
|---|---|---|
| Goal 1: início e fim de cada documento | Medido | Cascata implementada (regras, TF-IDF, Jev na faixa ambígua, reconciliação); números em "Resultados". Não há correção de fronteiras na revisão |
| Goal 2: agrupamento de páginas | Parcial | Persistência de documentos e páginas e consulta por API prontas. Juntar e dividir documentos na revisão não existe. UI Streamlit fora do escopo por enquanto |
| Goal 3: classificação por tipo | Medido | Jev + Gemini, classificador por regras e baseline TF-IDF + regressão logística (`scripts/baseline_tfidf.py`); números em "Resultados" |
| Goal 4: OCR pesquisável | Parcial | OCR e busca por texto no banco prontos. PDF pesquisável por documento não implementado: a busca é por texto no banco |
| Goal 5: confiança e revisão humana | Medido | Roteamento por limiares, `GET /revisao` e `POST /documentos/{id}/revisao`; `scripts/relatorio_cobertura.py` gera a curva. Limiares revistos com os dados de ajuste (ver "Resultados"). Sem tela de revisão |
| Goal 6: score de risco de ponto | Implementado | `worker_analise`, tabelas `perfil_jornada` e `analise_ponto`, `GET /documentos/{id}/analise-ponto`. Sem gabarito de divergências, então não há métrica de acurácia; base legal ainda por conferir no texto oficial |
| Goal 7: score de conformidade da empresa prestadora | Implementado | `worker_extracao`, tabela `documento_campos`, `GET /empresas`, `GET /empresas/{cnpj}/conformidade` e `GET /lotes/{id}/conformidade`. Sem gabarito de extração, então não há métrica de acurácia; prazo do ASO (NR-7) ainda por conferir |
| UI Streamlit | Não implementado | Fora do escopo por enquanto |
| `frontend/` | Esqueleto | Template inicial do Vite, separado do backend |

## Anonimização

`app/anonimizacao.py` é determinístico (regex e heurísticas de linha; sem LLM, sem modelo).

**O que é mascarado e onde**

- Texto enviado a LLM (`anonimizar_texto`: `[CPF]`, `[RG]`, `[PIS]`, `[NASCIMENTO]`, `[NOME]`): a classificação do Jev, as duas fatias da pergunta de fronteira, o texto de OCR enviado ao Gemini na análise de ponto e a `analise_gemini` que vai ao Jev. As regras locais da segmentação (paginação, CNPJ, TF-IDF) usam o texto original.
- Respostas da API (`mascarar_documentos`; CPF no formato `***.456.789-**`, RG e PIS como `***`): `pagina.texto` e `campos` de `GET /documentos/{id}`, `GET /documentos` e `GET /revisao` (e das respostas de `PUT /documentos/{id}/campos` e `PATCH /documentos/{id}/tipo`), `trecho` de `GET /busca`, `GET /documentos/{id}/analise-ponto` e os três endpoints de conformidade (`GET /empresas`, `GET /empresas/{cnpj}/conformidade`, `GET /lotes/{id}/conformidade`).
- A busca continua procurando no texto original do banco: achar por nome ou pelo CPF pontuado funciona, e o trecho devolvido sai mascarado.
- `PUT /documentos/{id}/campos` rejeita com 422 um `cpf`, `rg` ou `pis` que chegue mascarado (contém `*`), para a máscara nunca sobrescrever o valor real. Para manter o valor, omita o campo.
- Não são mascarados: CNPJ (é da empresa e a chave do Goal 7), datas e horários comuns (as marcações da folha de ponto ficam intactas) e termos de tipo documental e de RH (cargos, setores, títulos), que o classificador precisa ler.

**Decisão:** nomes continuam visíveis na API (`pessoa`, `campos.nome`), porque a tela de revisão precisa deles e mostra a imagem da página de qualquer forma.

**Resultado medido** (`docker compose exec api python scripts/avaliar_anonimizacao.py documentos.jsonl --db`, com os lotes já processados; lotes `L0001` a `L0005` do conjunto de ajuste do gerador sintético, texto do OCR do banco; a heurística foi ajustada nesse mesmo conjunto, então **não é métrica final**):

- Nome completo do funcionário que ainda aparece no texto anonimizado: 0 de 26 documentos (em 3 dos 29 documentos com nome no gabarito o OCR não leu o nome, e eles ficam fora da conta).
- Algum nome ou sobrenome (4+ letras) que ainda aparece: 2 de 26. Em um deles o OCR trocou o primeiro nome por "pára" e sobrou "Marques"; no outro "Rezende" aparece no endereço da empresa, que não é mascarado de propósito.
- CPFs válidos no texto: 26 antes, 0 depois.
- Termos de tipo documental apagados por engano (lista `TERMOS_DOCUMENTAIS` do módulo): 0.
- A medição só olha os nomes dos funcionários do gabarito. Nomes de médicos e de outros funcionários da folha de pagamento não têm gabarito: o módulo os mascara, mas não há número para isso. Ainda há falso positivo em texto com ruído de OCR (por exemplo, `[NOME]` no lugar de lixo em páginas rotacionadas).

**Limitações**

- As imagens das páginas enviadas ao Gemini (segunda opinião, análise de ponto e extração) não são mascaradas, e a extração de campos (`app/extracao.py`) envia o texto sem anonimizar, porque precisa ler nome e CPF.
- O banco, o volume de arquivos (`/data`, com as imagens das páginas) e o cache de LLM (`/cache`) guardam dados reais. Não há hash nem cifragem. O cache guarda as respostas dos LLMs, e a da extração contém nome e CPF.
- Nomes visíveis na API (decisão acima).
- A heurística de nome (2 a 6 palavras capitalizadas numa linha, mais rótulos) não é garantia: erra em nomes de uma palavra só, em nomes quebrados de forma incomum pelo OCR e em lixo de OCR, e pode mascarar expressões capitalizadas que não estejam na lista de exclusão. Só foi ajustada em documentos sintéticos.
- Isto não é conformidade LGPD por si só.

## Limitações

- Os dados sintéticos são otimistas. A validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.
- Um worker por fila: não há escala horizontal testada.
- Autenticação mínima: um único usuário administrador, sem tabela de usuários nem papéis; sem limite de tentativas de login; sem revogação de token (ele vale até expirar; para invalidar todos, troque `AUTH_SEGREDO`); e sem HTTPS, que em produção precisa ficar a cargo de um proxy reverso. O token fica em `sessionStorage` no frontend.
- Sem migrações: `sql/schema.sql` só vale em banco novo (ver `docker compose down -v`).
- Sem CI.
- O Jev e o Gemini recebem texto (anonimizado, ver "Anonimização") e imagem de páginas dos documentos. Use `CLASSIFICADOR=regras` se o conteúdo não puder sair da máquina.
- A confiança do classificador por regras é uma heurística sem calibração, usada só para roteamento.
- O sistema apoia a auditoria e não substitui parecer jurídico.
- Score de risco de ponto (Goal 6): é apoio à auditoria, não parecer jurídico, e vale por folha (não há consolidado por funcionário). A convenção coletiva e o acordo de compensação podem alterar os limites do perfil padrão (CLT de referência), e o perfil não os considera. O ponto britânico é sinal de risco, não prova de fraude.
- Completude por empresa (Goal 7): só verifica se existe ao menos um documento de cada tipo obrigatório para a empresa, não se cada funcionário tem o seu.

## Resultados

Todos os números abaixo vieram dos scripts de `scripts/`, rodados contra o sistema completo (com anonimização e login), com `CLASSIFICADOR=jev` (Jev `typesafe/jev-1.13`; Gemini só como segunda opinião, acionado 1 vez nos dois conjuntos medidos) e `CONF_AUTO=0.85`, `CONF_MIN=0.50`. **Os dados são sintéticos (gerador `gerar_lotes.py`, fora do repositório) e otimistas: a validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.** As amostras são pequenas; um erro a mais ou a menos muda bastante as taxas.

| Conjunto | Seed | Lotes | Documentos reais | Uso |
|---|---|---|---|---|
| ajuste | 101 | 5 | 30 | escolha dos limiares |
| treino | 202 | 20 | 159 | só o baseline TF-IDF |
| teste | 303 | 10 | 76 | medição final, enviado e medido uma única vez, depois de congelar código, prompts e limiares |

### Como reproduzir os scripts

Os scripts usam só a biblioteca padrão (exceto `baseline_tfidf.py`, que precisa de `requirements-baseline.txt`) e rodam no host. Com o login ativo, eles leem o token da variável de ambiente `API_TOKEN` (nunca por argumento, para não ficar no histórico). Para obtê-lo:

```bash
export API_TOKEN=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"usuario":"SEU_USUARIO","senha":"SUA_SENHA"}' \
  localhost:8000/auth/login | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
python scripts/avaliar_segmentacao.py anotacoes.csv --api http://localhost:8000 --lote L0001:1 --lote L0002:2
python scripts/avaliar_classificacao.py anotacoes.csv --api http://localhost:8000 --lote L0001:1 --lote L0002:2
python scripts/relatorio_cobertura.py anotacoes.csv --api http://localhost:8000 --lote L0001:1 --lote L0002:2
python scripts/baseline_tfidf.py treinar anotacoes_treino.csv --lote L0001:1 ... --modelo modelo.joblib
python scripts/baseline_tfidf.py avaliar anotacoes_teste.csv --lote L0001:1 ... --modelo modelo.joblib
```

O token vale `AUTH_EXPIRA_MIN` minutos. Sem ele, os scripts param com a mensagem "401 da API". Os IDs `L0001...` se repetem entre os conjuntos e o ID da API é outro, por isso o mapa `--lote ID_CSV:ID_API`.

### Limiares: regra e escolha

Regra definida antes de olhar o teste: a maior cobertura automática com precisão automática de pelo menos 0,95 no conjunto de ajuste; em empate, manter o valor atual. No ajuste (31 documentos previstos), a curva ficou em 93,5% automático e precisão 1,000 de `0,50` a `0,90`, e caiu para 90,3% em `0,95`. A curva não justifica mudança, então ficaram **`CONF_AUTO=0.85` e `CONF_MIN=0.50`**. Com cerca de 30 documentos e precisão 1,000 em todo o platô, isso não prova que 0,85 é ótimo, só que não há evidência para mudar.

### Segmentação (Goal 1), conjunto de teste

Métricas por documento. Precisão e recall são das fronteiras (início de documento); "exatos" exige início e fim corretos.

| | Ajuste (5 lotes) | Teste (10 lotes) |
|---|---|---|
| Documentos reais / previstos | 30 / 31 | 76 / 77 |
| Precisão das fronteiras | 0,923 | 0,896 |
| Recall das fronteiras | 0,960 | 0,909 |
| Documentos exatos | 26/30 (0,867) | 60/76 (0,789) |

No teste, os lotes L0001 (2/4 exatos), L0006 (5/10) e L0008 (4/11) concentram os erros; os outros sete lotes têm 4/5 ou mais. O mesmo `L0001` de 4 documentos reais virou 7 previstos.

### Classificação (Goal 3), conjunto de teste

Três números que medem coisas diferentes:

- **Jev, todos os documentos do gabarito:** o tipo previsto de cada documento do gabarito é o do documento previsto que cobre mais páginas dele; erros de segmentação contam como erro de classificação. 76 documentos.
- **Jev, só segmentação exata:** apenas os 60 documentos cujo intervalo previsto é idêntico ao real. Comparação justa com o baseline.
- **Baseline TF-IDF + regressão logística:** treinado só no `treino` (159 documentos, 20 lotes) e avaliado nos 76 documentos do gabarito, sobre o texto do OCR do intervalo real (a segmentação do sistema não entra).

| | Documentos | Acurácia | F1 macro |
|---|---|---|---|
| Jev, todos os documentos do gabarito | 76 | 1,000 | 1,000 |
| Jev, só segmentação exata | 60 | 1,000 | 1,000 |
| Baseline TF-IDF + regressão logística | 76 | 1,000 | 1,000 |

Matriz de confusão (linhas = real, colunas = previsto) do Jev nos 76 documentos, idêntica à do baseline: diagonal pura, com suporte `aso` 11, `folha_pagamento` 11, `folha_ponto` 14, `holerite` 8, `recibo_ferias` 10, `atestado_medico` 7 e `contrato_trabalho` 15 e nenhum erro fora da diagonal. Por qualidade do documento (Jev): boa 32/32, média 30/30, ruim 14/14.

**Leitura honesta:** o F1 1,000 dos dois métodos mostra que este conjunto sintético não separa Jev de baseline: os tipos têm vocabulário muito distinto. Não dá para concluir que o Jev é melhor ou pior, nem que o sistema acerta 100% em documentos reais. Para referência, no ajuste o Jev teve F1 macro 0,992 nos 30 documentos (0,991 na segmentação exata; 1 `recibo_ferias` ficou `desconhecido`), e a validação cruzada do baseline no treino (GroupKFold por lote, não é métrica final) deu F1 macro 0,982 em 159 documentos.

### Cobertura x precisão (Goal 5), conjunto de teste

Sobre os 77 documentos previstos (a precisão compara com o tipo real do documento do gabarito que o cobre). No limiar escolhido (`CONF_AUTO=0.85`): **90,9% automático (70/77), precisão automática 1,000 e 9,1% em revisão**.

| Limiar | % automático | Precisão automática | % revisão | Auto/total |
|---|---|---|---|---|
| 0,50 | 92,2% | 1,000 | 7,8% | 71/77 |
| 0,60 | 92,2% | 1,000 | 7,8% | 71/77 |
| 0,70 | 92,2% | 1,000 | 7,8% | 71/77 |
| 0,80 | 92,2% | 1,000 | 7,8% | 71/77 |
| 0,85 | 90,9% | 1,000 | 9,1% | 70/77 |
| 0,90 | 90,9% | 1,000 | 9,1% | 70/77 |
| 0,95 | 88,3% | 1,000 | 11,7% | 68/77 |

### Anonimização, conjunto de teste

`scripts/avaliar_anonimizacao.py` (texto lido pela API, com o CPF já mascarado, então a contagem de CPFs não é informativa): 76 documentos, 65 com nome de funcionário no gabarito; 8 nomes não localizados no OCR (fora do denominador). Nome completo que ainda aparece no texto anonimizado: 0/57. Algum nome ou sobrenome de 4+ letras sobrando: 3/57 (5,3%). Termos de tipo documental apagados por engano: 0. Com a anonimização ativa, o Jev classificou os 76 documentos sem erro; não houve medição sem anonimização, então não há comparação do efeito.

### Tempos e filas

Tempo desde o envio dos lotes até todos `concluido`: treino (20 lotes, `CLASSIFICADOR=regras`) 120,1 s; ajuste (5 lotes, Jev) 27,7 s; teste (10 lotes, Jev) 55,3 s. Em todos os conjuntos, a `dlq` ficou vazia e nenhum documento ficou em `erro`. Foram 116 registros `llm_chamada` (ajuste e teste juntos, 115 do Jev e 1 do Gemini).

### O que não foi medido

- Goals 6 e 7: sem gabarito de divergências nem de extração, então não há métrica de acurácia.
- Documentos reais; páginas giradas; efeito da anonimização sobre o Jev (sem comparação com e sem).
- Os valores acima valem para estes três conjuntos sintéticos e não foram repetidos.
