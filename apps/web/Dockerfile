# syntax=docker/dockerfile:1

# Build context is the repo root (`docker build -f apps/web/Dockerfile .`).
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app

# 1) Workspace manifest + lockfile first for layer caching
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/

# 2) Install deps (only apps/web is a real package; packages/* has no manifest)
RUN corepack pnpm install --frozen-lockfile

# 3) Build the SPA. Empty base URL => same-origin requests proxied by nginx.
COPY apps/web apps/web
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN corepack pnpm --dir apps/web build

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 80
