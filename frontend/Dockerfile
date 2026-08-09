# Frontend: build do Vite servido por nginx estático.
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
# Sem lockfile no primeiro build; `npm install` cria um, e o commit dele depois
# torna os builds reproduzíveis.
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
