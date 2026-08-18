# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app

# Baked into the bundle at build time; Vite has no runtime config.
ARG VITE_API_BASE=http://localhost:8080
ENV VITE_API_BASE=$VITE_API_BASE

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
