# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app

# Baked into the bundle at build time; Vite has no runtime config.
ARG VITE_API_BASE=http://localhost:8080
ENV VITE_API_BASE=$VITE_API_BASE

# .npmrc points at the registry, which is the point of this repo. The image build
# defaults to the upstream registry so `docker build` works for anyone; CI passes the
# registry URL once its preflight confirms the npm endpoint is reachable.
ARG NPM_REGISTRY=https://registry.npmjs.org

COPY package.json package-lock.json .npmrc ./
RUN npm ci --registry="$NPM_REGISTRY"

COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
