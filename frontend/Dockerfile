# foghorn frontend — Next.js standalone server behind Caddy.
#
# BACKEND_URL is needed at BUILD time (next.config.ts's /api rewrite bakes
# it into the standalone bundle) and again at runtime; compose passes the
# in-network backend address for both. In production Caddy routes /api/*
# straight to the backend, so the rewrite only serves as a fallback.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG BACKEND_URL=http://backend:8100
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

ARG BACKEND_URL=http://backend:8100
ENV BACKEND_URL=$BACKEND_URL
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

EXPOSE 3000
CMD ["node", "server.js"]
