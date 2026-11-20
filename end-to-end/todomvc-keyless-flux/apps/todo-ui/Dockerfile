# syntax=docker/dockerfile:1

# CI sets this to the todomvc multi-project, so base images come through Harbor's
# Docker Hub proxy cache under the same URL as the app images.
ARG BASE_REGISTRY=docker.io/library

FROM ${BASE_REGISTRY}/node:22-alpine AS build
WORKDIR /app
# Empty: the bundle calls /api on its own origin and nginx forwards it to the API.
ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE
# .npmrc resolves every package through the todomvc-npm proxy cache, which is public.
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM ${BASE_REGISTRY}/nginx:alpine
# The nginx image renders /etc/nginx/templates/*.template with envsubst at start.
ENV API_UPSTREAM=http://todo-api:8080
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
