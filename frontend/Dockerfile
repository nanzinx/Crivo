FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
# O endereço do backend entra no build: o Next grava os redirecionamentos de /api/* nesse momento
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S crivo && adduser -S crivo -G crivo
COPY --from=build --chown=crivo:crivo /app/.next/standalone ./
COPY --from=build --chown=crivo:crivo /app/.next/static ./.next/static
COPY --from=build --chown=crivo:crivo /app/public ./public
USER crivo
EXPOSE 3000
CMD ["node", "server.js"]
