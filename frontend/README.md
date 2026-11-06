# Frontend - AI Doc Factory

Este é o frontend da aplicação **AI Doc Factory**, uma plataforma para processamento, classificação e análise de conformidade de documentos utilizando Inteligência Artificial.

## 🏗️ Arquitetura e Organização

O projeto segue uma arquitetura modular com separação rigorosa de responsabilidades, facilitando a manutenção e escalabilidade.

### Estrutura de Pastas

- `src/pages`: Componentes que representam as telas principais da aplicação (HomePage, CategoryPage, ManualReviewPage).
- `src/components`: Componentes de UI reutilizáveis e modulares (Header, Cards, Modais, etc.).
- `src/services`: Camada de comunicação técnica. Contém o `api.ts` para chamadas ao backend.
- `src/hooks`: Lógica de estado e efeitos encapsulada para reutilização.
- `src/utils`: Funções puras, formatadores e processamentos independentes.
- `src/data`: Dados de inicialização e mocks para desenvolvimento.
- `src/types.ts`: Definições de interfaces e tipos globais (TypeScript).

## 🛠️ Tecnologias Principais

- **React + Vite**: Framework e ferramenta de build.
- **TypeScript**: Tipagem estática para maior segurança no desenvolvimento.
- **Tailwind CSS**: Estilização baseada em utilitários para UI responsiva.
- **Lucide React**: Biblioteca de ícones.

## 📐 Convenções do Projeto

### Estilo de Código
- **Separar Lógica de UI**: Sempre que possível, mova lógicas complexas para hooks ou serviços.
- **Componentes Funcionais**: Preferência total por componentes funcionais com Hooks.
- **Path Aliases**: Utilização de `@/` para facilitar imports organizados (configurado no `tsconfig`).

### Design & UX
- **Profundidade**: Uso de sombras multi-camadas (efeito "elevado") e cards com bordas arredondadas.
- **Responsividade**: Interfaces fluidas que se adaptam do desktop ao mobile.
- **Simulação Física**: Visualização de documentos inspirada em formatos reais (A4).

## 🚀 Integração com Backend

A comunicação é feita via `fetch` centralizada em `src/services/api.ts`.
As variáveis de ambiente são gerenciadas via arquivo `.env`:

- `VITE_API_URL`: Endereço do servidor backend (ex: http://127.0.0.1:8000).
- `VITE_API_PREFIX`: Prefixo das rotas (vazio por padrão: a API não usa prefixo).

O login usa `POST /auth/login`; o token fica em `sessionStorage` e `authFetch` o envia em todas as chamadas.

## 📝 Scripts Disponíveis

- `npm run dev`: Inicia o servidor de desenvolvimento.
- `npm run build`: Gera o build de produção otimizado.
- `npm run lint`: Executa a verificação do linter.
