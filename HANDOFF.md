# Passagem do projeto: Document AI Factory

Leia primeiro o `CLAUDE.md`, que é a especificação e as regras de trabalho. O `README.md` explica como rodar e traz os números medidos (seção Resultados).

**Regras principais:** PRs pequenos contra `master`, commits de até ~800 linhas, sem assinatura nos commits, o `CLAUDE.md` diz só backend por enquanto, mas há um frontend React na `master` (ver Decisões em aberto), chaves só no `.env` (o repositório é público) e nenhuma métrica sem script rodado.

## Estado da `master`

O `docker-compose.yml` no commit `645f3f4` define 8 serviços: `postgres`, `redis`, `api`, `worker_ocr_seg`, `worker_classify`, `worker_analise`, `worker_extracao` e `frontend`. A subida dos serviços em banco novo foi conferida no commit `0f497ff` (7 serviços, ainda sem o `frontend`), e não foi repetida no `645f3f4`. No `645f3f4`, em 2026-11-11, `372 passed, 1 skipped` com `CLASSIFICADOR=regras`, sem rede, rodando **fora do Docker** (Postgres e Redis locais, Python 3.13). Pelo `git log`, os merges vão dos PRs #1 a #16 e #18 a #23, #25, #26, #28, #29, #32, #34, #35, #36, #38, #39 e #40 (não consegui verificar PRs abertos).

| Parte | Situação | O que falta |
|---|---|---|
| Goal 1: separação de documentos | Medido | Números no README; sem correção de fronteiras na revisão |
| Goal 2: agrupamento e consulta | Parcial | Juntar e dividir documentos na revisão |
| Goal 3: classificação Jev + Gemini | Medido | Baseline existe (`scripts/baseline_tfidf.py`); números no README. Conjunto sintético não separa Jev de baseline (F1 1,000 nos dois) |
| Goal 4: OCR e busca | Parcial | PDF pesquisável por documento |
| Goal 5: roteamento e revisão | Medido | Limiares mantidos em 0,85 e 0,50 pela curva do ajuste (ver README) |
| Goal 6: risco da folha de ponto, por folha | Implementado | Conferir a base legal; sem gabarito de divergências |
| Goal 7: conformidade da empresa prestadora | Implementado | Conferir a extração; prazo do ASO na NR-7 |
| Upload de PDF, JPEG, PNG e TIFF | Pronto | HEIC e várias imagens por lote estão fora |
| UI | Implementada (React) | `frontend/` com login, upload, documentos por tipo, revisão manual, auditoria de ponto e conformidade da empresa; serviço `frontend` no compose. A UI Streamlit do `CLAUDE.md` não existe. Sem testes automatizados |

## O que falta, em ordem

1. **Medição concluída (uma única vez):** o baseline existe, foi treinado só no `treino` e os números do `ajuste` e do `teste` estão no README. O `teste` (seed 303) foi usado; não ajuste nada a partir dele nem o meça de novo. Qualquer nova medição precisa de um conjunto novo (outra seed).
2. **Validar em documentos reais:** os lotes sintéticos são otimistas, e o F1 1,000 do teste não discrimina Jev e baseline.
3. **Conferir a base legal no texto oficial:** caput do art. 71, NR-7 (os 12 meses do ASO são provisórios), Portaria MTP 671/2021, CF art. 7º e Súmula 338 do TST. A conferência da CLT foi feita em um resumo automático, não no texto literal.
4. **Segmentação:** no teste, 60/76 documentos exatos; os erros se concentram em poucos lotes (README).
5. **Se sobrar tempo:** PDF pesquisável e correção de fronteiras. Pela ordem de cortes do `CLAUDE.md`, são os primeiros a sair.

## Dados de teste

O gerador `gerador_sintetico.zip` foi enviado pelo Emmanuel, e outra versão está sendo feita. Ele não está no repositório, e a orientação é não reescrevê-lo.

| Conjunto | Comando | Tamanho | Uso |
|---|---|---|---|
| Ajuste | `python gerar_lotes.py --saida ajuste --n-lotes 5 --seed 101` | 36 páginas | Regras, prompts e limiares |
| Treino | `python gerar_lotes.py --saida treino --n-lotes 20 --seed 202` | 204 páginas | Baseline |
| Teste | `python gerar_lotes.py --saida teste --n-lotes 10 --seed 303` | 97 páginas | Medição final, **já usado** (não reutilizar) |

- Os lotes gerados não estão no repositório (estavam em uma pasta temporária que não existe mais). É preciso gerá-los de novo com o gerador, com o `requirements.txt` dele e o `poppler-utils`.
- Cada conjunto tem seu `anotacoes.csv` e um `documentos.jsonl` com os metadados, que ainda não foi usado e pode servir de gabarito para a extração do Goal 7.
- Os nomes `L0001`, `L0002` e assim por diante se repetem em cada pasta, e o ID na API é outro. Use `--lote ID_CSV:ID_API` nos scripts.
- O `L0001.pdf` recebido já foi usado para ajustes e não pode entrar na medição final. Os `L0002` e `L0003` do gabarito colado na conversa não foram gerados.

## Como medir

Com o `.env` preenchido e os serviços no ar, defina `API_TOKEN` (token de `POST /auth/login`; ver README, seção Resultados) e envie cada lote em `POST /lotes` e anote o ID devolvido.

```bash
python scripts/avaliar_segmentacao.py anotacoes.csv --api http://localhost:8000 --lote L0001:1
```

```bash
python scripts/avaliar_classificacao.py anotacoes.csv --api http://localhost:8000 --lote L0001:1
```

```bash
python scripts/relatorio_cobertura.py anotacoes.csv --api http://localhost:8000 --lote L0001:1
```

## Números antigos (históricos)

Os números finais estão no README. Os abaixo são só o histórico do `L0001`, de 15 páginas, **que foi usado para ajustes. Não são métricas finais.**

| | Antes das correções | Depois |
|---|---|---|
| Documentos previstos / reais | 12 / 9 | 11 / 9 |
| Precisão das fronteiras | 0,727 | 0,800 |
| Recall das fronteiras | 1,000 | 1,000 |
| Documentos exatos | 8/9 | 8/9 |

O F1 macro foi 1,000 em 9 documentos, o que não diz nada sobre o classificador em geral.

## Problemas conhecidos

- **Documento sem paginação:** o das páginas 10 a 13 do `L0001` ainda vira 3 documentos, marcados para revisão. O Jev fica incerto, porque recebe o fim da página, que em tabela é só número. Enviar o cabeçalho deve ajudar; meça no conjunto de ajuste.
- **Possível sobreajuste ao `L0001`:** `SEG_BRANCO_MAX_ALNUM=12` e a regra do CNPJ.
- **Páginas giradas:** o gerador gira 2% das páginas, e o sistema não corrige isso.
- **Worker frágil:** um job malformado na fila derruba o worker, sem política de reinício.
- **Extração lenta:** a fila `extrair_campos` termina depois do lote, então as empresas aparecem aos poucos em `GET /empresas`.
- **Completude por empresa:** só verifica se existe um documento de cada tipo, não por funcionário.
- **Sem CI.** O schema é versionado com Alembic (`migrations/`, serviço `migrate`); bancos criados pelo antigo `sql/schema.sql` precisam de `alembic stamp head` uma vez (README, seção 6).
- **Autenticação mínima:** `app/routers/auth/`, login em `POST /auth/login` com JWT e um único administrador (`AUTH_USUARIO`, `AUTH_SENHA`, `AUTH_SEGREDO`); sem papéis nem revogação de token (ver README, "Limitações").

## Decisões em aberto

- **S3:** não implementado. Os arquivos ficam no volume `dados`. Recomendação: manter até a demo; depois, usar chaves estáveis por lote e montar as pastas por empresa e tipo a partir do banco.
- **Dimensão indeterminada do score de ponto:** só marca `requer_revisao`, sem entrar em `/revisao`.
- **Tolerância de 10 min no intervalo:** não é aplicada; precisa ser conferida.
- **Ordem de cortes:** os Goals 6 e 7 não têm posição definida.
- **Frontend:** houve commits direto na `master`. Alinhar com o time, porque o combinado era só backend e passar por PR.
- **`CLAUDE.md` desatualizado:** ainda diz "por enquanto, só backend" e cita a UI Streamlit e o serviço `ui`, mas a `master` tem o frontend React e o serviço `frontend` no compose. O `CLAUDE.md` não foi alterado; o time precisa decidir se o frontend React substitui o Streamlit e atualizar o arquivo.

## Pontos de atenção

- `.env` local já tem as chaves. Nunca exiba nem commite esse arquivo. Com `CLASSIFICADOR=jev`, texto e imagens vão para OpenRouter e Google.
- Toda mudança de schema exige `docker compose down -v`, que apaga os dados locais. Há vários worktrees em `.claude/worktrees/`, cada um com projeto Compose e volumes próprios; confirme o projeto antes de rodar, e remova os que não forem mais necessários.
- Toda implementação com Jev segue a skill `building-with-typesafe-jev`.
- O gemini-3.5-flash é atendido como `gemini-3.6-flash`; o sistema registra o modelo que respondeu.
