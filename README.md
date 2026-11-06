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

A pasta `frontend/` é um projeto separado do backend (Vite + React + TypeScript + Tailwind v4). Hoje contém apenas o esqueleto inicial gerado pelo template do Vite, sem chamadas à API. Não faz parte do `docker-compose.yml` e não foi testada para este README.

## Endpoints

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
| `PUT /documentos/{id}/campos` | Corrige campos extraídos (`{"campos": {nome: valor ou null}, "revisor"}`): valor grava com origem `humano`, `null` remove. Nome `^[a-z0-9_]{1,40}$`, valor não vazio até 500 caracteres, `campos` e `revisor` não vazios (422); 404 se não existe; qualquer estado. Devolve o documento | `curl -X PUT -H "Content-Type: application/json" -d '{"campos":{"nome":"Maria"},"revisor":"ana"}' localhost:8000/documentos/1/campos` | `curl localhost:8000/revisao` |
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

Também podem ser ajustadas por ambiente (valores em `app/config.py`, não listadas no `.env.example` nem repassadas pelo `docker-compose.yml` atual, então exigem editá-lo): `SEG_SIM_BAIXO`, `SEG_SIM_ALTO`, `SEG_LLM_CONTINUA`, `SEG_LLM_ABRE`, `LLM_TIMEOUT`, `LLM_TENTATIVAS`, `LLM_ESPERA`. As respostas dos LLMs são cacheadas em disco (volume `cache_llm`).

## Estado atual

| Item | Situação | Observação |
|---|---|---|
| Goal 1: início e fim de cada documento | Parcial | Cascata implementada (regras, TF-IDF, Jev na faixa ambígua, reconciliação). Limiares não calibrados. Não há correção de fronteiras na revisão |
| Goal 2: agrupamento de páginas | Parcial | Persistência de documentos e páginas e consulta por API prontas. Juntar e dividir documentos na revisão não existe. UI Streamlit fora do escopo por enquanto |
| Goal 3: classificação por tipo | Parcial | Jev + Gemini e classificador por regras funcionando. O baseline TF-IDF + regressão logística não está implementado |
| Goal 4: OCR pesquisável | Parcial | OCR e busca por texto no banco prontos. PDF pesquisável por documento não implementado: a busca é por texto no banco |
| Goal 5: confiança e revisão humana | Parcial | Roteamento por limiares, `GET /revisao` e `POST /documentos/{id}/revisao` prontos; `scripts/relatorio_cobertura.py` gera a curva cobertura x precisão. Limiares ainda não escolhidos com dados reais. Sem tela de revisão |
| Goal 6: score de risco de ponto | Não implementado | Em desenvolvimento; não existe nesta branch (sem `worker_analise`, `analise_ponto` nem endpoint) |
| Goal 7: score de conformidade da empresa prestadora | Não implementado | Em desenvolvimento; não existe nesta branch (sem `documento_campos` nem `/lotes/{id}/conformidade`) |
| UI Streamlit | Não implementado | Fora do escopo por enquanto |
| `frontend/` | Esqueleto | Template inicial do Vite, separado do backend |

## Limitações

- Os dados sintéticos são otimistas. A validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.
- Um worker por fila: não há escala horizontal testada.
- Sem autenticação: qualquer cliente que alcance a API pode enviar, ler e revisar lotes. Não exponha a API fora de um ambiente local.
- Sem CI.
- O Jev e o Gemini recebem texto e imagem de páginas dos documentos. Use `CLASSIFICADOR=regras` se o conteúdo não puder sair da máquina.
- A confiança do classificador por regras é uma heurística sem calibração, usada só para roteamento.
- O sistema apoia a auditoria e não substitui parecer jurídico.

## Resultados

**Nenhuma métrica de qualidade foi medida ainda.** O gerador de lotes sintéticos (`gerar_lotes.py`) e o gabarito (`anotacoes.csv`) não estão neste repositório, então não há número de segmentação ou de classificação para reportar, e este README não cita acurácia, precisão ou recall.

Os scripts de avaliação já existem e usam só a biblioteca padrão do Python. Rodam no host, contra a API em execução, quando houver um `anotacoes.csv`:

```bash
python scripts/avaliar_segmentacao.py anotacoes.csv --api http://localhost:8000
python scripts/relatorio_cobertura.py anotacoes.csv --api http://localhost:8000
```

- `scripts/avaliar_segmentacao.py`: precisão e recall das fronteiras e fração de documentos exatos (início e fim), por documento.
- `scripts/relatorio_cobertura.py`: para cada limiar, % automático, precisão na parte automática e % em revisão.

Os scripts em si foram executados apenas sobre um CSV mínimo de 3 páginas criado para conferir o funcionamento; esses valores não são resultado do projeto.
