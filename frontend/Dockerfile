# Stage 1: Build da aplicação React + Vite
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=http://127.0.0.1:8000
ARG VITE_API_PREFIX=
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_API_PREFIX=${VITE_API_PREFIX}

RUN npm run build

# Stage 2: Servidor Nginx leve para servir o SPA
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

RUN printf 'server {\n\
    listen 80;\n\
    server_name _;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

