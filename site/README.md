# EviDocs — Site de Exposição

Página estática de apresentação (SPA) do **EviDocs**, construída com Vite, React, TypeScript e Tailwind CSS v4.

## Como rodar localmente

```bash
cd site
npm install
npm run dev
```

## Build e deploy (Vercel)

```bash
npm run build
```

Na Vercel, configure o **Root Directory** do projeto como `site`. O arquivo `vercel.json` já inclui o rewrite SPA (`/(.*) -> /index.html`).
