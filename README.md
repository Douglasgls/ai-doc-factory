# Document AI Factory

Projeto de hackathon. Recebe um PDF de lote com muitas páginas escaneadas (ou uma imagem), faz OCR de cada página, separa os documentos do lote, classifica cada um por tipo documental e envia os casos duvidosos para uma fila de revisão humana. O texto das páginas fica no PostgreSQL e pode ser pesquisado.

Hoje existem o backend (API + workers) e uma interface React em `frontend/`. O que está pronto, o que é parcial e o que ainda não existe está na seção [Estado atual](#estado-atual).

## Stack e serviços

- Python 3.12, FastAPI, PostgreSQL 16, Redis 7, Docker Compose.
- Leitura de páginas e OCR (`app/ocr.py`): híbrida por página com **PyMuPDF (`fitz`)** e **Tesseract (`-l por`)** a 150 dpi. O PyMuPDF percorre o PDF em sequência numa única thread (pois `fitz` não é thread-safe), libera o cache interno de imagens (`fitz.TOOLS.store_shrink(100)`) após cada página/documento para evitar retenção de RAM, gera o PNG da página para visualização/fallback e, quando a página possui camada de texto digital nativo válida e não é coberta por imagem escaneada (`>= 65%` da área), extrai o texto diretamente ordenado por blocos visuais (`pagina.texto_nativo = true`), sem acionar o Tesseract; as páginas escaneadas (`pagina.texto_nativo = false`) rodam o Tesseract em paralelo (até 4 páginas por worker).
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
| `frontend` | Interface React servida por Nginx (`FRONTEND_PORT`, padrão 5173): login, convite, upload, documentos por tipo, revisão manual, auditoria de ponto, conformidade, convenções coletivas, organizações e equipe (ver [Frontend](#frontend)) |
| `postgres` | Dados e busca full-text (config `portuguese`) |
| `redis` | Filas (listas, com ack via `BLMOVE`, 3 tentativas com espera entre elas e depois `dlq`) |

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

**Segmentação em cascata** (`app/segmentacao.py`): página em branco herda o documento anterior; "Página 1 de N" abre documento e "Página k de N" (k>1) continua só se for coerente com a última página paginada do documento (mesmo N e k maior; salto tolerado), senão abre documento novo marcado como ambíguo (revisão); a paginação só vale nas primeiras e últimas `SEG_PAG_LINHAS` linhas da página; senão, sem paginação, dois CNPJs válidos (dígitos verificadores) e diferentes abrem documento mesmo com similaridade alta (sem perguntar ao Jev; CNPJ que não fecha os dígitos é erro de OCR, não outra empresa); um CPF válido em cada página, diferentes, também abrem mesmo com similaridade alta (mesma empresa e mesmo modelo, outra pessoa); página anterior com a linha de total geral (`SEG_FECHO_REGEX`) fechou a tabela, e a página seguinte com conteúdo próprio abre; depois, similaridade TF-IDF entre páginas consecutivas (a partir de `SEG_SIM_ALTO` continua, abaixo de `SEG_SIM_BAIXO` abre) e página residual (continua); na faixa ambígua pergunta Sim/Não ao Jev (só com `CLASSIFICADOR=jev`). Se o Jev não responde ou fica no meio, o sistema abre documento novo e marca `segmentacao_ambigua`, o que leva o documento à revisão. Exceção, a continuação esperada: quando o documento anunciou a página ("Página k de N" com k < N e a paginação da página seguinte não foi lida) ou quando a linha de total geral está na página atual, a página continua e o Jev só veta (abre se P <= `SEG_LLM_ABRE`); com o Jev no meio da faixa, continua e marca o documento como ambíguo; sem Jev, abre e marca. Os limiares ainda não foram calibrados.

**Roteamento** (`app/roteamento.py`): confiança >= `CONF_AUTO` e sem desacordo entre modelos vira `classificado`; entre `CONF_MIN` e `CONF_AUTO`, ou com desacordo, ou segmentação ambígua, vira `em_revisao` com o tipo sugerido; abaixo de `CONF_MIN`, `em_revisao` com tipo `desconhecido`.

**Extração de campos em cascata** (`app/extracao.py`): quando a 1ª página do documento tem `texto_nativo = true`, o `worker_extracao` chama primeiro o Gemini enviando **apenas o texto** (`imagem_png=None`, zero tokens de imagem) com prompt dedicado (`VERSAO_PROMPT_EXTRACAO_TEXTO`, hoje `gemini-extracao-texto-v1`). Em seguida, `campos_essenciais_completos()` confere se os campos obrigatórios e dígitos verificadores (CNPJ/CPF) esperados para aquele tipo documental vieram preenchidos; se faltar algum campo essencial (por exemplo, data ou parecer em carimbo de imagem dentro de um PDF digital), o worker faz fallback automático chamando o Gemini com texto + imagem PNG da 1ª página (`VERSAO_PROMPT_EXTRACAO`, hoje `gemini-extracao-v4`) e mescla os resultados dando prevalência à resposta com imagem (preservando CNPJ/CPF válidos do texto nativo caso a leitura por imagem venha inválida). Páginas escaneadas (`texto_nativo = false`) enviam texto + imagem PNG diretamente na primeira chamada. **Limite da trava:** `campos_essenciais_completos()` detecta campos ausentes ou CNPJ/CPF com dígito verificador inválido, não valores trocados que tenham formato válido (por exemplo, confundir CNPJ da tomadora com o da prestadora quando só o layout visual os separa).

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

- `AUTH_USUARIO` e `AUTH_SENHA` servem só para criar o primeiro administrador (ver "Primeiro administrador" abaixo); `AUTH_SEGREDO` assina o token. **Sem `AUTH_SEGREDO` o sistema recusa o login (503) e toda rota protegida nega acesso.** Gere o segredo com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `UPLOAD_MAX_MB` (padrão 50) e `UPLOAD_MAX_PAGINAS` (padrão 300) limitam o upload: acima do tamanho a API responde 413, acima das páginas, 422. Nada é gravado antes dessas validações.
- `GEMINI_MODEL` e `GEMINI_ANALISE_MODEL` escolhem os modelos do Gemini (segunda opinião e extração de campos; análise de ponto); `CORS_ORIGINS` lista as origens do frontend; `CONVITE_VALIDADE_DIAS` (padrão 7) é a validade do link de convite. `FILA_ESPERAS` (padrão `5,30`) lista, em segundos e separada por vírgula, a espera antes da 2ª e da 3ª tentativa de um job; vazia usa o padrão. As demais variáveis estão na tabela "Variáveis de ambiente".

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

**Primeiro administrador.** Com `AUTH_USUARIO` (e-mail) e `AUTH_SENHA` preenchidos no `.env`, o serviço `migrate` cria, na primeira subida, um usuário de nível `plataforma` e papel `admin`. Se o usuário já existe, nada muda: trocar `AUTH_SENHA` depois não altera a senha dele. Para entrar, use `POST /auth/login` (ver "Autenticação") ou a tela de login em `http://localhost:5173` (`FRONTEND_PORT`). Dali em diante os demais acessos nascem por convite (ver "Organizações, contratos e convenções coletivas").

### 3. Enviar um lote e consultar o resultado

```bash
curl -F "arquivo=@meu_lote.pdf" http://localhost:8000/lotes
# {"lote_id":1,"estado":"recebido","existente":false}

curl http://localhost:8000/lotes/1
```

O processamento é assíncrono: repita o `GET /lotes/1` até `"estado":"concluido"` (um lote pequeno leva alguns segundos). A resposta traz os documentos com intervalo de páginas, estado, tipo, confiança e probabilidades. Reenviar o mesmo arquivo não cria outro lote (a identidade é o SHA-256 dos bytes): a API devolve o existente com `"existente":true`. Se esse lote estiver em `erro`, o reenvio o reprocessa (volta a `recebido` e a resposta traz `"reprocessando":true`); em `ocr`, `classificando` e `concluido` nada é reprocessado.

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

Os testes rodam dentro do container `api`, que tem acesso ao Postgres e ao Redis do Compose. Para o resultado ser limpo, rode com `CLASSIFICADOR=regras` e sem o administrador de bootstrap (`docker compose exec -e AUTH_USUARIO= -e AUTH_SENHA= api python -m pytest tests -q`), num Postgres e num Redis descartáveis, como no CI, e não no banco do stack em uso: um admin criado pelo `migrate` quebra `test_modelo_acesso`, e workers ativos consomem o lote que `test_schemas_saida` acabou de enviar. O CI (`.github/workflows/ci.yml`) roda backend (Postgres 16, Redis 7, `alembic upgrade head`, `pytest`) e frontend (`npm run lint`, `npm run build`).

Última execução registrada: 2026-11-23, commit `e14c311`, imagem do `api` (Python 3.12) construída desse commit, com Postgres 16 e Redis 7 do Compose, workers parados, sem usuário de bootstrap, `CLASSIFICADOR=regras`, `python -m pytest tests -q`: **`1143 passed, 1 skipped, 1 warning in 138.41s`**. Uma execução anterior, feita com os workers e o admin de bootstrap ativos no mesmo banco, deu 2 falhas (`test_modelo_acesso` e `test_schemas_saida::test_upload_de_lote`) pelos motivos descritos acima. `tests/test_migracoes.py` cria um banco descartável no mesmo servidor e testa `upgrade head` e `downgrade base`.

### 5. Rodar sem rede

Com `CLASSIFICADOR=regras` no `.env`, a classificação usa palavras-chave (`app/classificador_regras.py`) e a segmentação não chama o Jev, então nenhum texto de documento sai da máquina. Ao mudar o `.env`, recrie os serviços: `docker compose up -d`.

### 6. Mudança de schema e dados locais

O schema é versionado com Alembic (`alembic.ini`, `migrations/versions/`). As migrações são SQL cru via `op.execute`/`exec_driver_sql` (o app usa `psycopg` direto, sem models SQLAlchemy). O serviço `migrate` do Compose roda `alembic upgrade head` a cada `docker compose up`, antes da `api` e dos workers; `migrations/env.py` lê `DATABASE_URL` do ambiente. A revisão `0001_baseline` reproduz o schema inicial completo. As seguintes: `0002_modelo_acesso` (tabelas `tomador`, `prestador`, `contrato` e `usuario`), `0003_nome_padronizado_documento`, `0004_lote_contrato` (liga o lote a um contrato, `lote.contrato_id`, opcional; troca a unicidade global de `lote.sha256` por unicidade por contrato; **remove a tabela `empresa` e `lote.empresa_id`, com todos os seus dados**; o downgrade recria `empresa` vazia e falha, sem apagar lote, se o mesmo arquivo existir em mais de um lote), `0005_convite`, `0006_perfil_jornada_vigencia` (vigência por data, EC 141/2026), `0007_contrato_perfil_jornada`, `0008_documento_campos_autor`, `0009_contrato_proprio`, `0010_perfil_jornada_cadastro` (nome, sindicato e vigência da convenção), `0011_perfil_jornada_escopo` (convenção geral ou de um prestador) e `0012_pagina_texto_nativo` (`pagina.texto_nativo`, flag de página digital nativa extraída via PyMuPDF). O filtro de dados por organização (`app/escopo.py`) usa `lote.contrato_id`: ver "Autenticação".

Criar uma nova revisão (dentro do container, o arquivo gerado fica na imagem; copie-o para `migrations/versions/` do repositório):

```bash
docker compose run --rm migrate alembic revision -m "descricao curta"
```

Edite `upgrade()`/`downgrade()` com SQL e rebuild (`docker compose up -d --build`). Para aplicar manualmente: `docker compose run --rm migrate alembic upgrade head`; para voltar uma: `alembic downgrade -1`.

> **ATENÇÃO: quem já tem banco local criado pelo antigo `sql/schema.sql` (volume `pgdata` existente).** Antes do próximo `docker compose up`, rode **uma vez**:
>
> ```bash
> docker compose run --rm migrate alembic stamp head
> ```
>
> Isso apenas marca o baseline como aplicado, sem alterar tabelas nem dados. A alternativa é recomeçar do zero com `docker compose down -v` (apaga todos os dados locais). **Sem isso**, o serviço `migrate` falha com `relation "empresa" already exists` e, como a `api` e os workers só sobem depois que ele termina com sucesso, nenhum deles inicia.

Banco novo (volume vazio) não precisa de nada: o `migrate` cria o schema. O `sql/schema.sql` não existe mais; o schema vive em `migrations/versions/`.

Para recomeçar do zero:

```bash
docker compose down -v
```

O `-v` apaga os volumes: **todos os dados locais** (lotes, documentos, arquivos enviados e o cache de LLM) são perdidos. Para só parar os serviços, use `docker compose down` sem `-v`.

### 7. Reextrair campos de documentos antigos

Quando o prompt de extração muda (`VERSAO_PROMPT_EXTRACAO`, hoje `gemini-extracao-v4`, ou `VERSAO_PROMPT_EXTRACAO_TEXTO`, hoje `gemini-extracao-texto-v1`) ou um documento ficou sem extração, `scripts/reextrair_campos.py` reenfileira em `extrair_campos` os documentos em `classificado`, `revisado` ou `em_revisao` cuja extração gravada não é de uma das versões atuais ou não existe. **Por padrão é dry-run: só lista, não enfileira nada.**

```bash
docker compose exec api python scripts/reextrair_campos.py                 # dry-run: lista e conta por versão
docker compose exec api python scripts/reextrair_campos.py --lote 3 --limite 10   # dry-run, só o lote 3, até 10 documentos
docker compose exec api python scripts/reextrair_campos.py --lote 3 --limite 10 --executar   # enfileira de verdade
```

- `--lote ID` limita a um lote; `--limite N` limita a quantidade; `--executar` enfileira.
- **Cada documento enfileirado com `--executar` gasta uma chamada ao Gemini** (ou duas, se um documento com texto nativo acionar o fallback com imagem). Use `--lote` e `--limite` para controlar o custo.
- Só substitui campos de origem `gemini:*`. Campo corrigido por humano (origem `humano`) nunca é apagado.
- Saída de um dry-run real (2026-11-23, `--lote 1` de um banco de teste com 5 documentos sem extração):

```
versão atual do prompt: gemini-extracao-v4
documentos a reextrair: 5
  (sem extração): 5
ids: 1, 2, 3, 4, 5
dry-run: nada foi enfileirado (use --executar; cada documento gasta uma chamada ao Gemini)
```

### Frontend

A pasta `frontend/` é a interface (Vite + React + TypeScript + Tailwind v4), e o `docker-compose.yml` tem o serviço `frontend` (build com Nginx, porta `FRONTEND_PORT`, padrão 5173; `VITE_API_URL` e `VITE_API_PREFIX` entram como argumentos de build; `VITE_API_PREFIX` fica vazio, a API não tem prefixo). Pelo código em `frontend/src`, as telas são:

- login (com "manter conectado": o token vai para `localStorage` se marcado, senão `sessionStorage`) e aceite de convite (`/convite#<token>`, com o token no fragmento da URL: define nome e senha);
- documentos por tipo (pastas), upload de PDF, JPEG, PNG e TIFF com arrastar e soltar (o tamanho é validado antes de enviar), histórico de lotes vindo de `GET /lotes` e acompanhamento do processamento;
- revisão manual (fila, tipo sugerido, correção do tipo e dos campos extraídos) e visualizador com os dados lidos do documento;
- auditoria da folha de ponto e conformidade da empresa (modais);
- Convenções coletivas: lista, detalhe com a régua do dia, formulário (alterar, desfazer, mudança com data) e escolha da convenção de cada contrato;
- Organizações (só plataforma: tomadores, prestadores, contratos, empresa própria, convites), Terceirizadas (admin de tomador) e Equipe (admin de qualquer nível: usuários e convites).

O que aparece depende do nível e do papel (`frontend/src/utils/permissoes.ts`); para a empresa própria os textos de terceirização são trocados ("Seus documentos", "CNPJ da empresa"). Detalhes de desenvolvimento em `frontend/README.md`. A interface não tem testes automatizados (o CI roda só `npm run lint` e `npm run build`). A única avaliação dela até agora é a de um agente de IA, descrita em "Resultados"; para desenvolver fora do Docker, veja `frontend/.env.example`.

## Autenticação

O login usa a tabela `usuario` (níveis `plataforma`, `tomador` e `prestador`; papéis `admin` e `membro`). `usuario` no corpo do login é o `email` gravado (sem diferenciar caixa nem espaços nas pontas). Só entra quem está `ativo`, tem senha definida e, se for de tomador ou prestador, pertence a organização `ativa`; toda falha devolve o mesmo 401. As senhas ficam em hash scrypt (sal por senha, custo gravado no próprio hash; o login regrava hashes com custo antigo). `AUTH_SEGREDO` assina o token e `AUTH_EXPIRA_MIN` é a validade em minutos (padrão 480). Não há segredo padrão: sem `AUTH_SEGREDO`, `POST /auth/login` responde 503 e as demais rotas protegidas também negam acesso.

**Primeiro administrador:** `AUTH_USUARIO` e `AUTH_SENHA` agora servem **só** para criar o primeiro administrador. O serviço `migrate` do compose roda `python -m app.bootstrap_admin` depois do `alembic upgrade head`: se as duas variáveis estão definidas e não existe usuário com esse identificador, cria um usuário `plataforma`/`admin`; se já existe, não altera nada. **Trocar `AUTH_SENHA` depois não muda a senha de um usuário já criado.** Fora do Docker, rode o comando com as variáveis e `DATABASE_URL` no ambiente.

A cada requisição o usuário é relido no banco: desativá-lo (ou à sua organização) ou mudar seu papel vale na hora, e o nível e o papel que valem são os do banco, não os do token. Acesso aos dados (`app/escopo.py`, único ponto de decisão): **plataforma** vê e faz tudo; **tomador** só lê, e só lotes de contratos do seu tomador (ativos ou não, é o histórico); **prestador** lê e opera (upload, revisão, cancelar, reprocessar) só em lotes de contratos ativos do seu prestador, e no `POST /lotes` o `contrato_id` é obrigatório (422) e tem de ser contrato dele ativo (404). Recurso fora do escopo responde 404, igual ao inexistente; tomador recebe 403 em qualquer escrita sobre lotes e documentos; lote sem contrato é só da plataforma. Listagens (`/lotes`, `/documentos`, `/revisao`, `/busca`, `/contratos`) filtram no SQL e o stream de eventos segue o escopo do lote. As rotas de conformidade (`/empresas`, `/empresas/{cnpj}/conformidade`, `/lotes/{id}/conformidade`) valem para os três níveis, cada um com o seu escopo (ver "Organizações, contratos e convenções coletivas"). A criação e a ativação de tomador, prestador e contrato e o cadastro de empresa própria são só da plataforma; o cadastro de terceirizada é do admin do tomador (ou da plataforma); convites e a lista de usuários são do admin de cada organização (a plataforma vê todos); os perfis de jornada são da plataforma e do admin de empresa própria. `/tipos`, `/auth/me` e `GET /contratos` (filtrado) aceitam qualquer usuário logado. `GET /auth/me` devolve `id`, `email`, `nome`, `nivel`, `papel`, `tomador_id` e `prestador_id`. Tokens do formato anterior (emitidos antes do modelo de acesso) são recusados: é preciso entrar de novo. Ficam abertos só `GET /health`, `POST /auth/login`, `GET /convites/{token}` e `POST /convites/{token}/aceitar` (o token do convite é a credencial), `/docs` e `/openapi.json`.

Para obter o token (substitua pelos seus valores):

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"usuario":"SEU_USUARIO","senha":"SUA_SENHA"}' \
  localhost:8000/auth/login
# {"access_token":"...","token_type":"bearer","expira_em":"..."}

curl -H "Authorization: Bearer $TOKEN" localhost:8000/auth/me
```

O token é um JWT HS256 (claims `sub` = id do usuário, `nivel`, `papel`, `tomador_id`, `prestador_id`, `iat`, `exp`). No `/docs`, use o botão Authorize. Token em query string não é aceito, nem para a imagem da página: o cliente deve enviar o cabeçalho `Authorization`.

## Organizações, contratos e convenções coletivas

Conferido no código da `master` (commit `e14c311`), não só na documentação dos PRs.

**Níveis de acesso.** `plataforma` (opera o sistema), `tomador` (o cliente que contrata a terceirizada; só lê) e `prestador` (a empresa prestadora; envia e revisa os próprios lotes). Cada nível tem papel `admin` ou `membro`. Quem decide o que cada um vê é `app/escopo.py` (ver "Autenticação").

**Contrato.** O lote pertence a um contrato (tomador + prestador). A conformidade, a análise de ponto e o filtro de dados partem dele.

**Empresa solo = contrato próprio.** A empresa que não terceiriza é cadastrada pela plataforma em `POST /empresas-proprias`: o mesmo CNPJ vira tomador e prestador, com um contrato `proprio` entre eles e o convite do administrador. Uma regra única em `app/escopo.py` impede ligar o prestador de uma empresa própria a outro tomador (`POST /contratos` e `POST /terceirizadas` respondem com erro). O admin dela vê só os próprios dados, e a interface troca os termos de terceirização por "Seus documentos", "CNPJ da empresa" e "Empresa".

**Terceirizadas.** O admin do tomador cadastra a terceirizada em `POST /terceirizadas` (cria ou reaproveita o prestador do CNPJ, cria o contrato e, se o prestador ainda não tem acesso, o convite do administrador dele).

**Convenções coletivas (no código, "perfis de jornada").** Cada convenção tem nome, sindicato (opcional) e vigência (início e fim opcionais), e guarda só os parâmetros que diferem do Padrão (`clt_padrao`): os demais são herdados do Padrão, parâmetro a parâmetro. Escopo de cada uma:

- **Padrão:** o perfil CLT de referência, só leitura, visível a todos que leem perfis.
- **Geral:** marcada pela plataforma; visível a todos que leem perfis.
- **De um prestador:** pertence a um prestador; só ele (admin de empresa própria) e a plataforma a veem e editam. Geral e dono são exclusivos.

Cada contrato aponta para uma convenção (`PUT /contratos/{id}/perfil-jornada`, plataforma ou admin do contrato próprio) e o `worker_analise` usa a do contrato do lote; lote sem contrato usa o Padrão. A análise grava o nome e os valores efetivos usados. Trocar a convenção do contrato ou editá-la não refaz análises já gravadas: é preciso reprocessar o documento. A vigência cadastrada (`vigencia_inicio`/`vigencia_fim`) hoje só informa na tela se a convenção está vigente; a análise não deixa de usar uma convenção vencida. Admin de terceirizada (prestador que não é empresa própria) e tomador não veem a tela de convenções.

**Conformidade por escopo e pelo contrato do lote.** A empresa continua sendo a prestadora, identificada pelo CNPJ. O que muda com o contrato (`app/conformidade.py`): em lote com contrato, o documento sem CNPJ válido ou sem distinção entre prestadora e tomadora liga ao prestador do contrato (origem `contrato`), e um CNPJ extraído válido e diferente do contrato também liga ao prestador do contrato, com a divergência `cnpj_diferente_do_contrato`, que conta na Consistência. Lote sem contrato continua exigindo CNPJ extraído válido. O tomador vê o score de uma terceirizada calculado só com os documentos dos contratos dele; o prestador vê só a própria empresa; fora do escopo, 404. A razão social mostrada é a cadastrada no prestador, com a extraída mais comum como reserva.

**Fila.** Cada job tem até 3 tentativas, com espera antes da 2ª e da 3ª (`FILA_ESPERAS`, padrão 5 s e 30 s); depois vai para a `dlq`. O lote só vai para `erro` quando as tentativas se esgotam, não na primeira falha.

**Revisão humana com autor.** O revisor gravado em `POST /documentos/{id}/revisao`, `PATCH /documentos/{id}/tipo` e `PUT /documentos/{id}/campos` é o e-mail do usuário autenticado; o campo `revisor` do corpo é ignorado. Campo corrigido guarda o autor (`documento_campos.autor`, migração `0008`).

**Busca por texto.** `GET /busca?q=` usa a full-text search do PostgreSQL (`portuguese`) e devolve lote, página, documento, tipo, nome do arquivo, `nome_documento` (nome padronizado do documento), `pessoa`, `pagina_ini`/`pagina_fim` (a página dentro do documento é `pagina - pagina_ini + 1`) e o trecho com `<b>`. A tela de busca do frontend mostra o nome do documento, a pessoa e a página dentro do documento. Filtra pelo escopo do usuário; o trecho sai com CPF, RG e PIS mascarados (ver "Anonimização").

**Organizações e convites.** A plataforma cria tomador, prestador, contrato e empresa própria, e pode ativar ou desativar cada um (`PATCH .../{id}` com `ativo`). Convite é link de uso único (`POST /convites`, validade `CONVITE_VALIDADE_DIAS`): o banco guarda só o hash do token, e o token vem só na resposta da criação. O admin de cada organização convida colegas, lista e desativa usuários da própria organização. Um convite pendente pode ser **revogado** (`DELETE /convites/{id}`; convite já usado dá 409) ou **reemitido** (`POST /convites/{id}/reemitir`: revoga o não usado e cria outro igual, com link novo, numa transação). O aceite (`POST /convites/{token}/aceitar`) define nome e senha e já devolve o token de login.

## Endpoints

**Todas as rotas abaixo, exceto `GET /health`, exigem `Authorization: Bearer <token>`.** Os exemplos de `curl` da tabela omitem o cabeçalho por brevidade: acrescente `-H "Authorization: Bearer $TOKEN"`.

| Método e rota | Descrição | Exemplo |
|---|---|---|
| `GET /health` | Verifica Postgres e Redis | `curl localhost:8000/health` |
| `POST /lotes` | Envia PDF, JPEG, PNG ou TIFF (multipágina inclusive); imagens viram `original.pdf`. Arquivo inválido: 400. Campo de formulário opcional `contrato_id` vincula o lote a um contrato (404 se não existir; 409 se o contrato, o tomador ou o prestador estão inativos); sem ele o lote fica sem contrato. O mesmo arquivo (SHA-256) em contratos diferentes gera lotes diferentes; reenviar no mesmo contrato (ou sem contrato) devolve o lote existente, e um lote nunca muda de contrato | `curl -F "arquivo=@lote.pdf" localhost:8000/lotes` |
| `GET /lotes?estado=&contrato_id=&antes_de=` | Lista os lotes do escopo do usuário com resumo, filtros por `estado` e `contrato_id` (404 se o contrato está fora do escopo) e paginação por cursor (`proximo_cursor`) | `curl localhost:8000/lotes` |
| `GET /lotes/{id}` | Estado do lote, `contrato_id` e lista de documentos (intervalo, tipo, confiança, probabilidades) | `curl localhost:8000/lotes/1` |
| `GET /lotes/{id}/eventos` | Stream SSE (`text/event-stream`) de acompanhamento do lote: cada frame `data: {json}` traz o mesmo corpo de `GET /lotes/{id}` (com `ultimo_evento` e `historico_eventos`); linhas `: keepalive` entre os frames. O último frame traz também `"fim": true` e `"motivo"`: `finalizado` (lote `concluido`, sem documentos pendentes nem extração/análise pendentes), `erro` (lote em `erro`) ou `tempo_esgotado` (conexão aberta por 900 s, contados em tempo real). `?once=true` envia um único frame e fecha. Lote inexistente: 404 | `curl -N localhost:8000/lotes/1/eventos` |
| `POST /lotes/{id}/cancelar` | Cancela o processamento em andamento e devolve o lote. 404 se não existe; 409 se não há nada a cancelar (lote já finalizado) | `curl -X POST localhost:8000/lotes/1/cancelar` |
| `POST /lotes/{id}/reprocessar` | Reenfileira um lote em `erro` a partir do `original.pdf` e devolve o lote em `recebido`. 404 se não existe; 409 se o lote não está em `erro` ou tem documentos revisados; 400 se o `original.pdf` não está disponível | `curl -X POST localhost:8000/lotes/1/reprocessar` |
| `GET /documentos/{id}` | Documento com tipo, confiança, motivo de revisão e páginas (texto e `imagem_url`); também `campos` (extraídos, campo->valor), `pessoa` (`campos.nome` ou null), `nome_arquivo`, `n_paginas` e `processado_em` (criação do lote) | `curl localhost:8000/documentos/2` |
| `GET /documentos?contrato_id=&falhou=` | Documentos agrupados por tipo (`grupos`; `sem_tipo` para quem não tem); cada item traz também `campos`, `pessoa`, `nome_arquivo`, `n_paginas` e `processado_em`. cada item traz `contrato_id` (o do lote). `contrato_id` filtra pelo contrato do lote (404 se não existir); `falhou=true` só estado `erro`, `false` exclui | `curl "localhost:8000/documentos?falhou=false"` |
| `PATCH /documentos/{id}/tipo` | Corrige o tipo (`{"tipo"}`; `revisor` no corpo é ignorado, vale o e-mail do usuário autenticado) em qualquer estado exceto `segmentado` e `erro` (409); vira `revisado`; `tipo_original` guarda o primeiro tipo; dispara análise de ponto e extração como a revisão | `curl -X PATCH -H "Content-Type: application/json" -d '{"tipo":"aso"}' localhost:8000/documentos/1/tipo` |
| `DELETE /documentos/{id}` | 204. Apaga só a linha do documento: análise de ponto e campos extraídos caem em cascata; as páginas e o texto permanecem (`documento_id` NULL) e nenhum arquivo em disco é apagado. 409 se o lote está em andamento | `curl -X DELETE localhost:8000/documentos/1` |
| `GET /documentos/{id}/download` | Baixa o arquivo do documento com o nome padronizado; o `Content-Disposition` traz `filename` e `filename*` (RFC 6266/5987), então nomes com acento e aspas funcionam | `curl -OJ localhost:8000/documentos/1/download` |
| `GET /lotes/{lote_id}/paginas/{n}/imagem` | PNG da página | `curl -o p1.png localhost:8000/lotes/1/paginas/1/imagem` |
| `GET /busca?q=...&limite=20` | Full-text search (`portuguese`); devolve lote, página e trecho com `<b>`, mais `documento_id` (null se a página estiver órfã), `tipo` e `nome_arquivo` | `curl "localhost:8000/busca?q=contrato"` |
| `POST /tomadores` | Cria tomador (`{"nome", "cnpj"?}`); 201. CNPJ com ou sem pontuação, guardado com 14 dígitos e com os dígitos verificadores conferidos (422 se inválido). Nome repetido (sem diferenciar caixa nem espaços nas pontas) ou CNPJ repetido: 409 | `curl -H "Content-Type: application/json" -d '{"nome":"Tomadora S.A."}' localhost:8000/tomadores` |
| `GET /tomadores` | Lista os tomadores | `curl localhost:8000/tomadores` |
| `POST /prestadores` | Cria prestador (`{"cnpj", "razao_social"}`); 201. Mesma normalização e validação de CNPJ; CNPJ repetido: 409 | `curl -H "Content-Type: application/json" -d '{"cnpj":"11.222.333/0001-81","razao_social":"Prestadora Ltda"}' localhost:8000/prestadores` |
| `GET /prestadores` | Lista os prestadores | `curl localhost:8000/prestadores` |
| `POST /contratos` | Cria o contrato entre um tomador e um prestador (`{"tomador_id", "prestador_id", "vigencia_inicio"?, "vigencia_fim"?}`); 201. Par repetido: 409; tomador ou prestador inexistente: 404; `vigencia_fim` antes de `vigencia_inicio`: 422 | `curl -H "Content-Type: application/json" -d '{"tomador_id":1,"prestador_id":1}' localhost:8000/contratos` |
| `GET /contratos?tomador_id=&prestador_id=` | Lista os contratos (filtros opcionais); cada item traz `id`, `ativo`, as datas, o `perfil_jornada`, o nome e o estado do tomador e a razão social, o CNPJ e o estado do prestador, o bastante para montar um seletor de contrato | `curl "localhost:8000/contratos?tomador_id=1"` |
| `GET /perfis-jornada` | Plataforma e admin de empresa própria, cada um com o seu escopo. Convenções da análise de ponto: nome, sindicato, vigência, geral, se é o padrão, quantos parâmetros próprios e quantos contratos apontam para ela | `curl localhost:8000/perfis-jornada` |
| `GET /perfis-jornada/{perfil}` | Mesmo escopo da lista; fora dele, 404. `proprios` (o que o perfil guarda, com `vigente_desde`) e `efetivo` (o que a análise usa: próprios mais os herdados de `clt_padrao`); 404 se não existe | `curl localhost:8000/perfis-jornada/clt_padrao` |
| `PUT /perfis-jornada/{perfil}` | Plataforma (qualquer perfil) ou admin de empresa própria (só os dele). Cria o perfil ou substitui todos os seus parâmetros próprios (`{"parametros": [{"parametro", "valor", "base_legal", "vigente_desde"?}]}`). Informe só o que difere de `clt_padrao`; cada parâmetro informado substitui a linha do tempo inteira dele e precisa de um valor de base (`vigente_desde` nulo). Nome em minúsculas, dígitos e `_`. `clt_padrao`: 409; parâmetro desconhecido, repetido ou sem valor de base: 422 | `curl -X PUT -H "Content-Type: application/json" -d '{"parametros":[{"parametro":"jornada_semanal_min","valor":2640,"base_legal":"EC 141/2026, art. 9º"}]}' localhost:8000/perfis-jornada/adm_publica` |
| `PUT /contratos/{id}/perfil-jornada` | Plataforma ou admin do contrato próprio. Aponta o contrato para um perfil (`{"perfil": "..."}`); contrato ou perfil inexistente: 404. Vale para as análises feitas a partir daí | `curl -X PUT -H "Content-Type: application/json" -d '{"perfil":"adm_publica"}' localhost:8000/contratos/1/perfil-jornada` |
| `GET /revisao` | Fila de documentos `em_revisao`, com tipo sugerido e motivo; também `pagina_ini`, `pagina_fim`, `campos`, `pessoa`, `nome_arquivo`, `n_paginas` e `processado_em` | `curl localhost:8000/revisao` |
| `GET /tipos` | Tipos documentais `[{slug, nome, icone}]` na ordem da configuração (`TIPOS_INFO` em `app/config.py`), sem `desconhecido` | `curl localhost:8000/tipos` |
| `PUT /documentos/{id}/campos` | Corrige campos extraídos (`{"campos": {nome: valor ou null}}`; `revisor` no corpo é ignorado): valor grava com origem `humano`, `null` remove. Nome `^[a-z0-9_]{1,40}$`, valor não vazio até 500 caracteres, `campos` não vazio (422); 404 se não existe; qualquer estado. Devolve o documento | `curl -X PUT -H "Content-Type: application/json" -d '{"campos":{"nome":"Maria"}}' localhost:8000/documentos/1/campos` |
| `GET /documentos/{id}/analise-ponto` | Análise de risco da folha de ponto (Goal 6): marcações, divergências (tipo, data, minutos, base legal, evidência; `espelho_incompleto` traz `campos_ausentes`), perfil usado (`perfil_nome` e `perfil`), score por dimensão e score geral (máximo entre as dimensões), modelos e versões dos prompts | `curl localhost:8000/documentos/1/analise-ponto` |
| `GET /empresas` | Empresas prestadoras (CNPJ validado) com score geral de conformidade e classificação (Goal 7), no escopo do usuário (tomador: só documentos dos contratos dele) | `curl localhost:8000/empresas` |
| `GET /empresas/{cnpj}/conformidade` | Os três níveis (documento, tipo, geral), notas por critério, classificação, descontos com motivo e pendências | `curl localhost:8000/empresas/12.345.678/0001-95/conformidade` |
| `GET /lotes/{id}/conformidade` | Empresas encontradas no lote e documentos sem empresa, com o motivo | `curl localhost:8000/lotes/1/conformidade` |
| `POST /terceirizadas` | Admin do tomador (ou plataforma, com `tomador_id`): cria ou reaproveita o prestador do CNPJ, cria o contrato e, se o prestador ainda não tem acesso, o convite do admin dele (o token vem só nesta resposta) | ver `/docs` |
| `POST /empresas-proprias` | Só plataforma. Empresa solo: tomador e prestador do mesmo CNPJ, contrato `proprio` e convite do admin, numa transação; conflitos: 409 | ver `/docs` |
| `PATCH /tomadores/{id}`, `PATCH /prestadores/{id}`, `PATCH /contratos/{id}` | Só plataforma. Ativa ou desativa (`{"ativo": bool}`) | ver `/docs` |
| `POST /perfis-jornada` | Plataforma ou admin de empresa própria. Cria uma convenção a partir do nome (sindicato e vigência opcionais); o slug é gerado pelo servidor; só a plataforma envia `geral` e `prestador_id` | ver `/docs` |
| `POST /convites` | Cria o convite (link de uso único); o token vem só nesta resposta. Quem pode convidar quem: `app/escopo.py` | ver `/docs` |
| `GET /convites` | Convites: plataforma vê todos; admin de organização, os da própria; membro: 403 | `curl localhost:8000/convites` |
| `DELETE /convites/{id}` | Revoga convite pendente (204); usado: 409 | `curl -X DELETE localhost:8000/convites/1` |
| `POST /convites/{id}/reemitir` | Revoga o convite não usado e cria outro igual, com link novo (201) | `curl -X POST localhost:8000/convites/1/reemitir` |
| `GET /convites/{token}`, `POST /convites/{token}/aceitar` | Públicos (o token é a credencial). Consulta e aceite (`{"nome","senha"}`, devolve o token de login) | ver `/docs` |
| `GET /usuarios`, `PATCH /usuarios/{id}` | Lista usuários do escopo e ativa/desativa (`{"ativo": bool}`); admin só os da própria organização; desativar a si mesmo: 409 | `curl localhost:8000/usuarios` |
| `POST /documentos/{id}/revisao` | Corrige o tipo; o documento vira `revisado` e `tipo_original` guarda o tipo sugerido. 409 se o documento não está em revisão | ver abaixo |

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"tipo":"aso"}' \
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
| `FRONTEND_PORT` | `5173` | Porta do frontend no host |
| `VITE_API_URL` | `http://127.0.0.1:${API_PORT}` | URL da API que o frontend usa (fixada no build) |
| `VITE_API_PREFIX` | vazio | Prefixo das rotas da API no frontend (a API não usa prefixo) |
| `UPLOAD_MAX_MB` | `50` | Tamanho máximo do upload, em MB (413 acima) |
| `UPLOAD_MAX_PAGINAS` | `300` | Máximo de páginas por lote (422 acima) |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Origens do frontend permitidas pela API |
| `FILA_ESPERAS` | `5,30` | Espera, em segundos, antes de cada nova tentativa de um job (após a 1ª e a 2ª falha); a 3ª falha vai para a `dlq`. Vazia usa o padrão |
| `CONVITE_VALIDADE_DIAS` | `7` | Validade do link de convite, em dias |
| `GEMINI_ANALISE_MODEL` | `gemini-3.8-flash` | Modelo do Gemini na análise de folha de ponto |
| `CONF_AUTO` | `0.85` | Confiança mínima para classificação automática |
| `CONF_MIN` | `0.50` | Abaixo disso o tipo vira `desconhecido` e vai para revisão |
| `CLASSIFICADOR` | `jev` | `jev` (Jev + Gemini) ou `regras` (sem rede) |
| `OPENROUTER_API_KEY` | vazio | Chave do OpenRouter (Jev). Só no `.env` |
| `JEV_MODEL` | vazio | Modelo do Jev. Testado com `typesafe/jev-1.13` |
| `GEMINI_API_KEY` | vazio | Chave do Google AI Studio. Só no `.env` |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Modelo da segunda opinião e da extração de campos |
| `AUTH_USUARIO` | vazio | Identificador (e-mail) do primeiro administrador, criado por `python -m app.bootstrap_admin` se não existir |
| `AUTH_SENHA` | vazio | Senha inicial desse administrador. Só no `.env`. Trocá-la depois não muda a senha de um usuário já criado |
| `AUTH_SEGREDO` | vazio | Segredo que assina o JWT. Só no `.env`. Sem ele, o login responde 503 |
| `AUTH_EXPIRA_MIN` | `480` | Validade do token, em minutos |

Também podem ser ajustadas por ambiente (valores em `app/config.py`, não listadas no `.env.example` nem repassadas pelo `docker-compose.yml` atual, então exigem editá-lo): `SEG_SIM_BAIXO`, `SEG_SIM_ALTO`, `SEG_LLM_CONTINUA`, `SEG_LLM_ABRE`, `SEG_LLM_TRECHO`, `SEG_LLM_CABECALHO`, `SEG_RESIDUAL_MAX_ALNUM`, `SEG_RESIDUAL_CONTIDO`, `SEG_FECHO_REGEX`, `LLM_TIMEOUT`, `LLM_TENTATIVAS`, `LLM_ESPERA`. As respostas dos LLMs são cacheadas em disco (volume `cache_llm`).

## Estado atual

| Item | Situação | Observação |
|---|---|---|
| Goal 1: início e fim de cada documento | Medido | Cascata implementada (regras, TF-IDF, Jev na faixa ambígua, reconciliação); números em "Resultados". Não há correção de fronteiras na revisão |
| Goal 2: agrupamento de páginas | Parcial | Persistência de documentos e páginas e consulta por API prontas. Juntar e dividir documentos na revisão não existe. A UI Streamlit não foi implementada; a interface é o `frontend/` React |
| Goal 3: classificação por tipo | Medido | Jev + Gemini, classificador por regras e baseline TF-IDF + regressão logística (`scripts/baseline_tfidf.py`); números em "Resultados" |
| Goal 4: OCR pesquisável | Parcial | OCR e busca por texto no banco prontos. PDF pesquisável por documento não implementado: a busca é por texto no banco |
| Goal 5: confiança e revisão humana | Medido | Roteamento por limiares, `GET /revisao` e `POST /documentos/{id}/revisao`; `scripts/relatorio_cobertura.py` gera a curva. Limiares revistos com os dados de ajuste (ver "Resultados"). A tela de revisão está no `frontend/` |
| Goal 6: score de risco de ponto | Implementado | `worker_analise`, tabelas `perfil_jornada` e `analise_ponto`, `GET /documentos/{id}/analise-ponto`. Sem gabarito de divergências, então não há métrica de acurácia. Base legal conferida em 15/11/2026 no texto compilado do Planalto (CF, EC 141/2026 e CLT) e na Portaria MTP 671/2021 compilada. O perfil tem vigência por data (EC 141/2026) e a prorrogação noturna do art. 73, § 5º; decisões e pendências nas limitações |
| Goal 7: score de conformidade da empresa prestadora | Implementado | `worker_extracao`, tabela `documento_campos`, `GET /empresas`, `GET /empresas/{cnpj}/conformidade` e `GET /lotes/{id}/conformidade`. Sem gabarito de extração, então não há métrica de acurácia; prazo do ASO (NR-7) ainda por conferir. Escopo por nível e pelo contrato do lote |
| UI Streamlit | Não implementado | Substituída pelo `frontend/` React |
| `frontend/` | Implementado | Login, convite, upload, documentos por tipo, revisão manual, auditoria de ponto, conformidade, convenções coletivas, organizações, terceirizadas e equipe; serviço `frontend` no `docker-compose.yml`. Sem testes automatizados; avaliado só por um agente de IA (ver "Resultados") |
| Acesso por nível, empresa própria, convites e convenções por escopo | Implementado | Plataforma, tomador e prestador; conformidade e análise de ponto pelo contrato do lote; ver "Organizações, contratos e convenções coletivas". Sem medição de acerto: só testes automatizados e as avaliações descritas em "Resultados" |

## Anonimização

`app/anonimizacao.py` é determinístico (regex e heurísticas de linha; sem LLM, sem modelo).

**O que é mascarado e onde**

- Texto enviado a LLM (`anonimizar_texto`: `[CPF]`, `[RG]`, `[PIS]`, `[NASCIMENTO]`, `[NOME]`): a classificação do Jev, as duas fatias da pergunta de fronteira, o texto de OCR enviado ao Gemini na análise de ponto e a `analise_gemini` que vai ao Jev. As regras locais da segmentação (paginação, CNPJ, CPF, total geral, TF-IDF) usam o texto original, que não sai da máquina.
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

- As imagens das páginas enviadas ao Gemini (segunda opinião, análise de ponto e extração de páginas escaneadas ou em fallback) não são mascaradas, e a extração de campos (`app/extracao.py`) envia o texto sem anonimizar, porque precisa ler nome e CPF. Em páginas digitais nativas (`pagina.texto_nativo = true`) cujos campos essenciais já vêm completos no texto, a imagem da página não é enviada ao Gemini.
- O banco, o volume de arquivos (`/data`, com as imagens das páginas) e o cache de LLM (`/cache`) guardam dados reais. Não há hash nem cifragem. O cache guarda as respostas dos LLMs, e a da extração contém nome e CPF.
- Nomes visíveis na API (decisão acima).
- A heurística de nome (2 a 6 palavras capitalizadas numa linha, mais rótulos) não é garantia: erra em nomes de uma palavra só, em nomes quebrados de forma incomum pelo OCR e em lixo de OCR, e pode mascarar expressões capitalizadas que não estejam na lista de exclusão. Só foi ajustada em documentos sintéticos.
- Isto não é conformidade LGPD por si só.

## Limitações

- Os dados sintéticos são otimistas. A validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.
- O `docker-compose.yml` sobe réplicas dos workers (`worker_ocr_seg` 4, `worker_classify`, `worker_analise` e `worker_extracao` 2 cada) numa só máquina; não há teste de carga nem de escala em vários hosts.
- Autenticação: o login usa a tabela `usuario` e há convites e gestão de usuários (listar, ativar e desativar), mas não há troca nem recuperação de senha; sem limite de tentativas de login; sem revogação de token (ele vale até expirar; para invalidar todos, troque `AUTH_SEGREDO`); e sem HTTPS, que em produção precisa ficar a cargo de um proxy reverso. O token fica em `sessionStorage` no frontend, ou em `localStorage` se o usuário marcar "manter conectado".
- Migrações só em SQL cru (Alembic, sem models) e sem teste de upgrade a partir de bancos antigos além do baseline; quem tem banco criado pelo antigo `sql/schema.sql` precisa de `alembic stamp head` (ver seção 6).
- O CI (`.github/workflows/ci.yml`) roda os testes do backend e `lint` e `build` do frontend; o frontend não tem testes automatizados.
- Prazo do ASO: o prazo de 12 meses em `app/conformidade.py` é um valor de partida e **precisa ser conferido na NR-7**. O desconto por ASO vencido depende desse prazo.
- O Jev e o Gemini recebem texto (anonimizado, ver "Anonimização") e imagem de páginas dos documentos. Use `CLASSIFICADOR=regras` se o conteúdo não puder sair da máquina.
- A confiança do classificador por regras é uma heurística sem calibração, usada só para roteamento.
- O sistema apoia a auditoria e não substitui parecer jurídico.
- Score de risco de ponto (Goal 6): é apoio à auditoria, não parecer jurídico, e vale por folha (não há consolidado por funcionário). A convenção coletiva e o acordo de compensação podem alterar os limites do perfil padrão (CLT de referência): o Padrão não os considera, e a convenção só vale se for cadastrada como perfil ("Convenções coletivas") e ligada ao contrato do lote; o sistema não confere se o perfil cadastrado reproduz a convenção real. Acordo de compensação e banco de horas continuam sem tratamento. O ponto britânico é sinal de risco, não prova de fraude. As horas extras do dia e o total da semana contam a hora noturna reduzida (CLT art. 73, § 1º: 52min30s entre 22h e 5h valem 60 min), e o intervalo intrajornada vale pelo maior intervalo do dia, não pela soma (CLT art. 71, caput).
- Regras de jornada por data (Emenda Constitucional 141, de 16/10/2026; texto conferido em 15/11/2026 em planalto.gov.br): os parâmetros de `perfil_jornada` têm vigência (`vigente_desde`) e cada dia e cada semana da folha é avaliado pela regra da época. No perfil `clt_padrao`: duração semanal de 44 horas até 15/12/2026, 42 horas a partir de 16/12/2026 e 40 horas a partir de 16/12/2027 (EC 141, art. 6º); repouso semanal de 24 horas consecutivas (CLT art. 67) até 15/12/2026 e de 2 dias a partir de 16/12/2026 (CF art. 7º, XV). As datas ficam só no banco (migração `0006`). Decisões de projeto, que não estão no texto da emenda: (1) a semana vai de segunda a domingo e vale, para a semana inteira, a regra vigente no domingo, então a semana de 14 a 20/12/2026 já é avaliada com 42 horas e 2 dias de repouso; (2) "2 dias de repouso" é lido como 2 dias de calendário sem nenhum minuto de trabalho dentro da semana, que podem ser separados (a emenda não diz se são consecutivos nem define a janela); o dia em que termina uma jornada noturna da véspera não conta; só se conclui em semana com os 7 dias na folha. Não há regra automática para contratos com a administração pública (EC 141, art. 9º): eles ficam cobertos por um perfil próprio no contrato. Também não há regra automática para o regime compensatório por convenção ou acordo coletivo (CF art. 7º, § 2º) nem para os empregados do art. 8º da emenda.
- Perfil de jornada por contrato: cada contrato aponta para um perfil (`contrato.perfil_jornada`, padrão `clt_padrao`) e o `worker_analise` usa o perfil do contrato do lote; lote sem contrato usa `clt_padrao`. Um perfil próprio guarda só os parâmetros que diferem e herda o resto de `clt_padrao`; a herança é por parâmetro (o parâmetro redefinido substitui a linha do tempo inteira, inclusive as vigências da EC 141). A análise grava o nome (`perfil_nome`) e o perfil efetivo usado. A plataforma e o admin de empresa própria cadastram e associam convenções (API e tela "Convenções coletivas"); admin de terceirizada e tomador não têm acesso a elas, e o contrato de uma terceirizada só recebe uma convenção pela plataforma. Trocar o perfil do contrato ou editar um perfil não refaz as análises já gravadas: é preciso reprocessar o documento. Não há endpoint para apagar perfil, e um perfil sem linhas no banco faz a análise falhar (vai para a `dlq` e fica como `erro`).
- Prorrogação do trabalho noturno (CLT art. 73, § 5º: "Às prorrogações do trabalho noturno aplica-se o disposto neste capítulo"): o parágrafo não define a prorrogação. Critério usado (decisão de 16/11/2026, com a Súmula 60, II, e a OJ 388 da SDI-1 do TST como referência de entendimento; jurisprudência não conferida em fonte oficial): a parte depois das 5h só conta com a hora reduzida se a jornada cobriu todo o horário noturno, das 22h às 5h. Em código: (1) o empregado já estava trabalhando às 22h (a entrada pode atrasar até a tolerância de 5 minutos por marcação), (2) os intervalos entre as marcações são menores que o descanso entre jornadas (11 horas), senão é nova jornada, e (3) há trabalho depois das 5h. Contam: 22h-7h, 22h-2h e 3h-7h, 19h-7h (12x36; as horas entre 19h e 22h continuam diurnas) e 22h-5h e 6h-8h (a retomada depois de um intervalo curto é emenda da mesma jornada). Não contam: 23h-7h, 0h-7h e 4h-12h. O código não mede quanto da noite foi trabalhado depois das 22h, então uma jornada com intervalo muito longo dentro da noite ainda satisfaz o critério.
- Espelho de ponto incompleto (`espelho_incompleto`; Portaria MTP 671/2021, art. 84, texto compilado em 21/07/2026): o Gemini informa o tipo de registro e, para cada informação que o artigo lista (nome e CNPJ/CPF do empregador; nome, CPF, data de admissão e cargo/função do trabalhador; data de emissão e período do relatório; horário e jornada contratual; marcações; duração das jornadas), se ela aparece (`true`), não aparece (`false`) ou não pôde ser lida (`null`), sem copiar valores. A decisão é do código: só há divergência quando o documento é um espelho eletrônico e algum campo veio como `false`; campo não lido nunca conta como ausente, e folha manual ou cartão mecânico ficam como `nao_aplicavel`, porque o art. 84 trata do "Espelho de Ponto Eletrônico". CEI/CAEPF/CNO não é exigido ("caso exista"). O resultado fica em `totais.espelho`. Desde o `jev-ponto-v6` o código conta os campos ausentes (`campos_do_espelho_ausentes`) e envia a contagem ao Jev, que a considera na dimensão `registro` do score (níveis por faixa: 1 ou 2, 3 a 5, 6 ou mais campos ausentes). O Gemini recebe no máximo `PONTO_MAX_PAGINAS` páginas, então uma informação que só aparece depois disso pode vir como ausente.
- Ainda não tratados no ponto: intervalo intrajornada acima de 2 horas (CLT art. 71, caput), descanso semanal coincidindo com o domingo, escalas especiais (12x36) e banco de horas. A regra de contar o excesso inteiro quando a tolerância de 10 minutos é ultrapassada segue entendimento de jurisprudência, não o texto da lei. As versões novas dos prompts (`gemini-ponto-v4`, `jev-ponto-v6`) só foram exercitadas com mock nos testes automatizados; o efeito do `jev-ponto-v6` foi medido com Jev real em 2 folhas (ver "Resultados"), e o `gemini-ponto-v4` só no teste manual de 21/11.
- Convenções coletivas (limites conhecidos, registrados nos PRs): o downgrade da migração `0010` descarta a tabela de cadastro e, com ela, o nome, o sindicato e a vigência; um perfil sem parâmetros próprios existe só nessa tabela, então desaparece no downgrade (os parâmetros dos demais ficam). O downgrade da `0011` perde a marca de geral e o dono. Os perfis que já existiam antes da `0011` ficam "não gerais e sem dono": só a plataforma os vê até alguém marcá-los. Slugs legados só com `_` não foram tratados. O `PUT` não aceita lista de parâmetros vazia, então não dá para salvar um perfil existente desfazendo todas as mudanças.
- Completude por empresa (Goal 7): só verifica se existe ao menos um documento de cada tipo obrigatório para a empresa, não se cada funcionário tem o seu.

## Resultados

**Duas partes.** As seções de "Limiares" a "Tempos e filas" abaixo são de medições anteriores (feitas antes das mudanças de acesso, convenções e empresa própria); **não foram repetidas em 23/11/2026**, porque dependem do gerador `gerar_lotes.py` e dos conjuntos sintéticos (fora do repositório) e de chamadas reais ao Jev e ao Gemini. A seção "Rodada de 23/11/2026" traz o que foi rodado ou conferido nesta atualização do README.

Todos os números das seções anteriores vieram dos scripts de `scripts/`, rodados contra o sistema completo (com anonimização e login), com `CLASSIFICADOR=jev` (Jev `typesafe/jev-1.13`; Gemini só como segunda opinião, acionado 1 vez nos dois conjuntos medidos) e `CONF_AUTO=0.85`, `CONF_MIN=0.50`. **Os dados são sintéticos (gerador `gerar_lotes.py`, fora do repositório) e otimistas: a validação em documentos reais (scans ruins, rotações, manuscritos) ainda é necessária.** As amostras são pequenas; um erro a mais ou a menos muda bastante as taxas.

| Conjunto | Seed | Lotes | Documentos reais | Uso |
|---|---|---|---|---|
| ajuste | 101 | 5 | 30 | escolha dos limiares |
| treino | 202 | 20 | 159 | só o baseline TF-IDF |
| teste | 303 | 10 | 76 | medição final, enviado e medido uma única vez, depois de congelar código, prompts e limiares |
| ajuste2 | 505 | 15 | 116 | análise de erros e ajuste da segmentação (PR #82) |
| teste2 | 909 | 10 | 82 | medição final da segmentação do PR #82, gerado e medido uma única vez depois do merge |
| ajuste3 | 606 | 12 | 82 | segmentação em lote de uma só empresa (PR #87), gerador com `--prob-mesma-empresa 1.0` |
| teste3 | 707 | 10 | 93 | medição final da segmentação do PR #87 (uma empresa por lote), gerado e medido uma única vez depois do merge |

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

Para iterar na segmentação sem API nem banco, `scripts/avaliar_segmentacao_offline.py textos_ocr.json anotacoes.csv [--diagnostico]` roda `app.segmentacao.segmentar` direto sobre o OCR já extraído (`{lote: [texto por página]}`) e imprime as mesmas métricas; com `--diagnostico`, lista cada fronteira errada com a regra que decidiu, paginação, CNPJ, CPFs válidos, similaridade e a resposta do Jev. Precisa das dependências do projeto (rode dentro do container) e, fora do modo `CLASSIFICADOR=regras`, chama o Jev com cache.

O token vale `AUTH_EXPIRA_MIN` minutos. Sem ele, os scripts param com a mensagem "401 da API". Os IDs `L0001...` se repetem entre os conjuntos e o ID da API é outro, por isso o mapa `--lote ID_CSV:ID_API`.

### Limiares: regra e escolha

Regra definida antes de olhar o teste: a maior cobertura automática com precisão automática de pelo menos 0,95 no conjunto de ajuste; em empate, manter o valor atual. No ajuste (31 documentos previstos), a curva ficou em 93,5% automático e precisão 1,000 de `0,50` a `0,90`, e caiu para 90,3% em `0,95`. A curva não justifica mudança, então ficaram **`CONF_AUTO=0.85` e `CONF_MIN=0.50`**. Com cerca de 30 documentos e precisão 1,000 em todo o platô, isso não prova que 0,85 é ótimo, só que não há evidência para mudar.

### Segmentação (Goal 1)

Métricas por documento. Precisão e recall são das fronteiras (início de documento); "exatos" exige início e fim corretos.

**Versão atual (depois do PR #82)**, medida com `scripts/avaliar_segmentacao.py` contra o sistema completo em Docker (`CLASSIFICADOR=jev`, pergunta de fronteira `jev-fronteira-v3`):

| | Ajuste (5 lotes) | Ajuste2 (15 lotes) | Teste2 (10 lotes) |
|---|---|---|---|
| Documentos reais / previstos | 30 / 31 | 116 / 117 | 82 / 83 |
| Precisão das fronteiras | 0,962 | 0,990 | 0,986 |
| Recall das fronteiras | 1,000 | 1,000 | 1,000 |
| Documentos exatos | 29/30 (0,967) | 115/116 (0,991) | 81/82 (0,988) |

Antes do PR #82, nos mesmos conjuntos de ajuste, eram 28/30 e 110/116 exatos. Todos os erros eram cortes a mais, e todos passavam pela pergunta ao Jev. Eram de dois tipos: folha só de assinaturas no fim do contrato (4) e continuação da tabela da folha de pagamento com a paginação perdida no OCR (4). O PR mudou a pergunta (agora também recebe o cabeçalho da página anterior) e criou a regra de página residual (`SEG_RESIDUAL_*`). O erro que sobra no teste2 é um corte a mais no lote L0010. No teste2 a classificação acertou os 82 documentos (acurácia e F1 macro 1,000).

Ressalvas: o gerador nunca coloca dois documentos consecutivos da mesma empresa, que é o caso comum num lote real de uma só prestadora, e nos conjuntos de ajuste nenhuma fronteira real chegou a passar pela pergunta ao Jev. A regra de página residual pode fundir um documento real muito curto que repita as palavras da página anterior; os limites dela não foram validados em documento real.

**Mudança posterior à tabela acima: lote de uma só empresa.** O conjunto `ajuste3` (12 lotes, 82 documentos, uma empresa por lote, 59 pares vizinhos da mesma empresa) mostrou o que a ressalva previa: com a versão do PR #82 eram 86 previstos, precisão 0,919, recall 0,971 e 74/82 exatos, com duas fusões (fronteira real perdida). Causas, por contagem: Jev indeciso na continuação da tabela da folha de pagamento (3 cortes), contratos do mesmo modelo e de funcionários diferentes fundidos pela similaridade alta (1 fusão), folha nova fundida à anterior pelo Jev (1 fusão), CNPJ lido errado pelo OCR tratado como outra empresa (1 corte), página 2 de 2 girada e ilegível (1 corte) e página em colunas sem cabeçalho (1 corte). As regras novas são as de CPF, total geral, continuação esperada e CNPJ inválido, descritas na arquitetura. Medição com `scripts/avaliar_segmentacao_offline.py` (OCR já extraído, Jev com cache), só em conjuntos de **ajuste**, então não é métrica final. A mesma medição repetida com `scripts/avaliar_segmentacao.py` contra o sistema completo em Docker deu números idênticos:

| | Ajuste | Ajuste2 | Ajuste3 |
|---|---|---|---|
| Antes: previstos / precisão / recall / exatos | 31 / 0,962 / 1,000 / 29/30 | 117 / 0,990 / 1,000 / 115/116 | 86 / 0,919 / 0,971 / 74/82 |
| Depois: previstos / precisão / recall / exatos | 30 / 1,000 / 1,000 / 30/30 | 116 / 1,000 / 1,000 / 116/116 | 83 / 0,986 / 1,000 / 81/82 |

O erro que sobra no ajuste3 é um corte a mais (L0009, página lida em colunas, sem cabeçalho nem CNPJ). As regras foram escolhidas olhando estes três conjuntos, então os números acima são otimistas.

**Medição final (teste3, depois do PR #87)**: conjunto novo `teste3` (seed 707, 10 lotes, 93 documentos, uma empresa por lote, gerador com `--prob-mesma-empresa 1.0`), gerado e medido uma única vez depois do merge, com `scripts/avaliar_segmentacao.py` contra o sistema completo em Docker: 93 previstos, precisão das fronteiras 1,000, recall 1,000, **93/93 documentos exatos**; classificação 93/93 (F1 macro 1,000). A opção `--prob-mesma-empresa` foi acrescentada à cópia local do gerador, que continua fora do repositório; com o padrão 0 o gerador reproduz os conjuntos antigos. Continua sendo dado sintético: falta validar em documento real. Limites conhecidos: a regra do CPF só vale quando cada página tem exatamente um CPF legível (folha de ponto sem CPF e do mesmo modelo ainda depende da paginação ou do Jev, e similaridade alta sem CPF ainda continua sem perguntar); uma página 2 que só traga o CPF de outra pessoa (testemunha, dependente) seria cortada; uma página de resumo depois do total geral seria cortada; e a continuação esperada pode fundir uma folha de uma página a uma folha anterior cujo total o OCR perdeu, se o Jev não vetar (o documento sai marcado como ambíguo quando o Jev fica indeciso).

**Medição anterior (histórico)**, conjunto `teste` (seed 303), com a versão de antes das mudanças de CNPJ, paginação e do PR #82:

| | Ajuste (5 lotes) | Teste (10 lotes) |
|---|---|---|
| Documentos reais / previstos | 30 / 31 | 76 / 77 |
| Precisão das fronteiras | 0,923 | 0,896 |
| Recall das fronteiras | 0,960 | 0,909 |
| Documentos exatos | 26/30 (0,867) | 60/76 (0,789) |

No teste, os lotes L0001 (2/4 exatos), L0006 (5/10) e L0008 (4/11) concentram os erros; os outros sete lotes têm 4/5 ou mais. O mesmo `L0001` de 4 documentos reais virou 7 previstos.

**Mudança posterior à medição final.** Depois da medição final, a regra do CNPJ na segmentação mudou: sem paginação, dois CNPJs válidos pelos dígitos verificadores e diferentes abrem documento mesmo com similaridade alta (antes a similaridade alta decidia "continua" antes de olhar o CNPJ). As regras de paginação também mudaram depois da medição: "Página k de N" (k>1) só continua o documento quando é coerente com a última página paginada dele (mesmo N e k maior; caso contrário abre documento novo e marca ambíguo), e a paginação só é lida nas primeiras e últimas linhas da página (`SEG_PAG_LINHAS`), não em frases do corpo. Os números do conjunto de teste acima valem para a versão anterior; a versão atual foi medida no teste2 (tabela acima). No conjunto de **ajuste** (não é métrica final), a mesma medição foi repetida com a regra nova: antes, 30 reais / 31 previstos, precisão 0,923, recall 0,960, exatos 26/30; depois, 30 reais / 32 previstos, precisão 0,926, recall 1,000, exatos 28/30.

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

### Leitura híbrida (PyMuPDF): benchmark A/B local e extração no Gemini (`gemini-3.6-flash`)

Medição controlada A/B em 25/11/2026 (`--sem-cache`, diretórios de cache isolados, 0 cache hits, 0 retentativas; `GEMINI_MODEL=gemini-3.5-flash` roteado pela API para `gemini-3.6-flash`, `serviceTier=standard`) sobre **29 PDFs sintéticos / 30 páginas** (15 páginas digitais nativas + 15 páginas raster/escaneadas, cobrindo os 7 tipos documentais e 1 PDF misto de 2 páginas), comparando **Antes** (Poppler + Tesseract em 100% das páginas + PNG em todas as extrações) vs. **Depois** (PyMuPDF com `store_shrink(100)` + extração em cascata):

| Recorte medido | Tempo local (A→D) | CPU local (A→D) | Subprocessos (A→D) | Tokens entrada (A→D) | Saída + thoughts (A→D) | Custo est. 2026¹ (A→D) | Fallbacks | Divergências |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Lote local isolado (29 PDFs / 30 págs)** | `32,58 → 24,88 s` (**-23,6%**) | `33,49 → 24,86 s` (**-25,8%**) | `149 → 44` (**-70,5%**) | `78.253 → 76.859` | `33.735 → 46.340` | `US$ 0,1852 → US$ 0,2314` (`+25,0%`) | `6 / 15` | `4` *(ver abaixo)* |
| **7 PDFs nativos válidos** (`01_nativos_validos`) | `5,13 → 0,36 s` (**-93,0%**) | `5,16 → 0,36 s` (**-93,1%**) | `35 → 7` (**-80,0%**) | `15.758 → 8.231` (**-47,8%**, `IMAGE: 7.644 → 0`) | `8.645 → 10.165` (`+17,6%`) | `US$ 0,0442 → US$ 0,0443` (**+0,1%**) | `0 / 7` | **`0`** |
| **7 PDFs nativos com CNPJ/CPF inválidos** *(pior caso)* | `5,17 → 0,33 s` (**-93,6%**) | `5,20 → 0,33 s` (**-93,6%**) | `35 → 7` (**-80,0%**) | `15.759 → 22.122` (`+40,4%`) | `7.836 → 17.567` (`+124,2%`) | `US$ 0,0412 → US$ 0,0825` (**+100,1%**) | `6 / 7` | `1` *(equivalente)* |
| **14 PDFs escaneados/raster** (`pdf/` + `scans`) | `19,09 → 19,67 s` (`+3,0%`) | `19,15 → 19,67 s` (`+2,7%`) | `70 → 28` (**-60,0%**) | `42.489 → 43.322` (`+2,0%`) | `16.160 → 16.743` (`+3,6%`) | `US$ 0,0925 → US$ 0,0953` (`+3,0%`) | `N/A` | `3` *(2 acertos a mais no híbrido)* |
| **1 PDF misto (2 págs: 1 nativa + 1 scan)** | `1,73 → 1,51 s` (`-12,6%`) | `2,53 → 1,51 s` (**-40,3%**) | `9 → 2` (**-77,8%**) | `4.247 → 3.184` (`-25,0%`, `IMAGE: 1.092 → 0`) | `1.094 → 1.865` (`+70,5%`) | `US$ 0,0073 → US$ 0,0094` (`+28,7%`) | `0 / 1` | **`0`** |

*¹ Custo estimado na tabela pública vigente do `gemini-3.6-flash` até 31/12/2026 (`US$ 0,75 / 1M` entrada; `US$ 3,75 / 1M` saída + `thoughtsTokenCount`); a partir de 01/01/2027 os valores dobram (`US$ 1,50 / US$ 7,50`).*

**O que os dados comprovam — e ressalvas importantes:**

- **Ganho local comprovado (velocidade, CPU, RAM e processos):** no lote isolado de 29 PDFs (30 páginas), com `fitz.TOOLS.store_shrink(100)` ativo, o pico de RAM do worker Python caiu de **148,7 MB para 123,1 MB (-17,2%)** (antes do `store_shrink`, o cache padrão de 256 MB do MuPDF havia elevado o pico para 267,0 MB em 14 PDFs). Nos PDFs digitais nativos, pular o Tesseract reduziu tempo e CPU local em **93%** (~14× mais rápido) com **0 divergências** frente ao modo com imagem.
- **Custo financeiro no Gemini NÃO caiu sob `thinking` irrestrito:** embora os tokens de entrada tenham caído **47,8%** nos 7 nativos válidos (eliminando os `1.092` tokens fixos de imagem por página), o custo em dólares ficou em **empate técnico (`+0,1%`)**, porque os tokens de raciocínio (`thoughtsTokenCount`, cobrados a 5× o preço da entrada) responderam por >55% da conta e oscilaram para cima (`+20,4%`) nas chamadas só-texto. Além disso, quando o documento nativo contém CNPJ/CPF com dígito verificador inválido, o fallback faz uma 2ª chamada completa e **dobra o custo (`+100,1%`)**. A principal alavanca futura de redução de custo na API é limitar o `thinkingBudget` na extração estruturada.
- **Qualidade e outras etapas:** nos 29 PDFs, nenhum erro foi introduzido pelo modo híbrido (`0` divergências nos 7 nativos válidos e no PDF misto; nos scans, o híbrido acertou `data_admissao` em `recibo_ferias_scan.pdf` e `razao_social_prestadora` em `folha_pagamento.pdf` onde o fluxo anterior falhou). Ainda assim, a amostra é sintética (`N = 29` PDFs) e o efeito da leitura via PyMuPDF/MuPDF sobre segmentação (Goal 1), classificação (Goal 3) e busca em documentos reais de RH não foi remedido.

### Rodada de 23/11/2026

Três fontes, com alcances diferentes. Nenhuma substitui as medições acima.

**1. Scripts de avaliação, sem LLM, em 2 lotes pequenos.** Commit `e14c311`, stack do Compose construído desse commit, `CLASSIFICADOR=regras` (sem rede, sem Jev nem Gemini), 2 lotes sintéticos (`L0001`: 5 páginas e 5 documentos; `L0002`: 9 páginas e 5 documentos; 10 documentos no total, o mesmo gabarito `anotacoes.csv` do teste com LLM abaixo), enviados por `POST /lotes` sem contrato. Comandos, a partir da pasta com `anotacoes.csv`:

```bash
python scripts/avaliar_segmentacao.py anotacoes.csv --api http://localhost:8260 --lote L0001:1 --lote L0002:2
python scripts/avaliar_classificacao.py anotacoes.csv --api http://localhost:8260 --lote L0001:1 --lote L0002:2
python scripts/relatorio_cobertura.py anotacoes.csv --api http://localhost:8260 --lote L0001:1 --lote L0002:2
```

| Segmentação (por documento) | Reais | Previstos | Precisão das fronteiras | Recall das fronteiras | Exatos |
|---|---|---|---|---|---|
| `L0001` | 5 | 5 | 1,000 | 1,000 | 5/5 |
| `L0002` | 5 | 6 | 0,800 | 1,000 | 4/5 |
| Total | 10 | 11 | 0,889 | 1,000 | 9/10 (0,900) |

Classificação por regras de palavras-chave, nos 10 documentos do gabarito: **acurácia 0,800 e F1 macro 0,833**. Acertou `aso` (2/2), `folha_pagamento` (1/1), `holerite` (2/2), `recibo_ferias` (2/2) e `contrato_trabalho` (1/1) e errou as 2 `folha_ponto`, que saíram `desconhecido`. Só nos 9 documentos com segmentação exata: acurácia 0,778 e F1 macro 0,800. Por qualidade: boa 6/6, média 0/1, ruim 2/3.

Cobertura x precisão do classificador por regras (11 documentos previstos), saída do script: limiar 0,50 dá 72,7% automático com precisão 1,000 (8/11); 0,60 dá 63,6% (7/11); 0,70 dá 36,4% (4/11); de 0,80 a 0,95 dá 18,2% (2/11), sempre com precisão automática 1,000. Com 11 documentos isso não diz nada sobre os limiares do Jev (`CONF_AUTO` e `CONF_MIN`): a confiança do classificador por regras é uma heurística sem calibração.

Não rodados nesta rodada: `scripts/baseline_tfidf.py` (precisa dos lotes de treino e do `requirements-baseline.txt`), `scripts/avaliar_segmentacao_offline.py` (precisa do JSON de OCR dos conjuntos) e `scripts/avaliar_anonimizacao.py`. Os números dessas medições continuam sendo os das seções anteriores, com a fonte de cada uma ali.

**2. Teste ponta a ponta com LLM real, 21/11/2026 (verificado por um agente de IA independente, o agy Orchestrator, não por uma pessoa).** Jev e Gemini (`gemini-3.8-flash`) de verdade, 2 lotes sintéticos (`L0001`, contrato entre tomador e terceirizada; `L0002`, empresa própria), **10 documentos no total**. A amostra é muito pequena: serve para ver o fluxo funcionando, não para estimar taxa de acerto. O agente só leu a API e comparou com o gabarito; o roteiro, o script de conferência e o relatório ficam fora do repositório.

| Verificação | Resultado observado |
|---|---|
| Segmentação | 10/10 documentos com início e fim exatos (no `L0002`, os versos em branco foram absorvidos e a divisão a mais que ocorre sem LLM não apareceu) |
| Classificação | 10/10 tipos certos, confiança de 0,99 a 1,00, nenhum documento em revisão |
| Extração de campos | 23/23 nos campos do roteiro (nome, competência, tipo de exame, data do exame, início e admissão, férias) e 35/35 incluindo empresa e CPF mascarado, comparados com o gabarito |
| Empresa | Nenhum documento sem empresa; os 10 ligados pelo contrato do lote |
| Conformidade | Duas empresas com scores separados (25, provisório, e 50), ambas "Crítico", com descontos e pendências coerentes com os documentos; o ASO vencido gerou desconto. Sem gabarito de conformidade, então não é métrica de acerto |
| Análise de ponto | 2 folhas, 8 e 11 divergências (de intervalo intrajornada com data, minutos e base legal, CLT art. 71, mais `espelho_incompleto` em cada uma); totais de horas exatos; ponto britânico sem sinal. Mesmo `score_geral` (0,337) nas duas (antes do `jev-ponto-v6`). Modelos gravados: `gemini-3.8-flash` e `typesafe/jev-1.14-20261014` (prompts `gemini-ponto-v4` e `jev-ponto-v5`). Sem gabarito de divergências |
| Empresa própria, pelo admin dela | Aceita o convite, entra, vê só o próprio lote e a própria conformidade; os dados do outro lote respondem 404, igual a inexistente |

**Medição posterior do `jev-ponto-v6` (PR #124), com Jev real, em 23/11/2026, nas mesmas 2 folhas de ponto sintéticas** (3 campos ausentes no espelho em cada uma): a dimensão `registro` foi de 0,02 e 0,03 para 0,66 (nível 2, confiança 0,99), e o `score_geral` de cerca de 0,34 para cerca de 0,66. É uma amostra de 2 folhas, que mostra que a mudança chega ao score, não uma taxa de acerto; sem gabarito de divergências.

O agente registrou 5 problemas. Três foram tratados em commits de 23/11/2026, depois do teste, segundo o histórico, **sem repetir a chamada real ao LLM**: `modelo` e `versao_prompt` não apareciam nas rotas de documento (corrigido só em parte: `5a9c941` os expõe em `GET /documentos/{id}`, não na listagem nem em `GET /lotes/{id}`), a razão social mostrava o nome extraído do primeiro documento em vez da cadastrada (`b89aa0f`) e `data_termino` não era extraída em contrato por prazo determinado (`8c02bb9`). Dos outros dois, um continua sem correção conhecida: em 2 documentos a extração veio sem `razao_social_prestadora`, o que gerou pendência e um score individual diferente; e o `espelho_incompleto` (Portaria MTP 671/2021, art. 84) não pesava no score. Esse último foi tratado depois (PR #124, `jev-ponto-v6`; medição abaixo). Sobre os problemas corrigidos, a ressalva continua: só o `espelho_incompleto` foi remedido com Jev real.

**3. Testes de usabilidade com agente de IA (agy, modelo Orchestrator), duas rodadas em 23/11/2026.** É a avaliação de **um agente de IA**, não de usuários reais, e deve ser lida assim. Ele recebeu um roteiro com três papéis (operador da plataforma, dona de empresa solo e admin de terceirizada), executou as tarefas no navegador (desktop 1440x900 e celular 390x844) e deu notas de 0 a 10 com justificativa. Os dois lotes foram os mesmos (`L0001` e `L0002`).

| Papel | 1ª rodada | 2ª rodada (depois das correções) |
|---|---|---|
| Operador da plataforma | 7,0 | 7,0 |
| Empresa solo | 7,5 | 7,5 |
| Admin de terceirizada | 7,8 | 7,5 |
| **Nota geral** | **7,5** | **7,3** |

As notas **não são comparáveis estatisticamente**: é uma execução por rodada, de um único avaliador automático cuja nota pode variar sem que a interface mude, e os ambientes e os detalhes do roteiro não foram idênticos. A queda de 7,5 para 7,3 não indica piora nem melhora. O valor está na lista de achados:

- 1ª rodada, entre os mais graves: o link do convite se perdia ao sair da tela (sem reenviar nem revogar), o layout quebrava em 390 px e o campo "Base legal" era obrigatório sem aviso. Pelo histórico de PRs, os #119 a #122 trataram parte disso (reemitir e revogar convite, layout responsivo, textos); a 2ª rodada relatou zero rolagem horizontal no celular, e o "Base legal" obrigatório continuou, agora como achado de gravidade baixa.
- 2ª rodada, ainda abertos: a tela não permite corrigir tipo ou campo de um documento já classificado fora da fila de revisão (a API tem `PATCH /documentos/{id}/tipo` e `PUT /documentos/{id}/campos`); o cadastro de empresa própria fica dentro de "Contratos"; o admin de terceirizada não vê as convenções coletivas; o contrato exige digitar de novo o prestador já cadastrado; faltam o parecer do ASO e o valor líquido do holerite nos cartões; e o alerta de divergência de razão social não lista os documentos em conflito.
- Nenhum teste com pessoas reais foi feito.

### O que não foi medido

- Goals 6 e 7: sem gabarito de divergências nem de extração, então não há métrica de acurácia.
- Documentos reais; páginas giradas; efeito da anonimização sobre o Jev (sem comparação com e sem).
- Os valores das seções anteriores à rodada de 23/11/2026 valem para os conjuntos sintéticos descritos e não foram repetidos nela; a rodada tem só 10 documentos.
- Usabilidade com pessoas reais, acerto da extração fora dos 2 lotes do teste manual e o efeito de convenções coletivas reais no score de ponto.
- Taxa de fallback, economia financeira líquida e efeito da leitura nativa via PyMuPDF (e rasterização via MuPDF) sobre segmentação, classificação e extração em lotes reais de RH.
