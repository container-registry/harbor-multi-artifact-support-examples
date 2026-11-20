# syntax=docker/dockerfile:1

# CI sets this to the todomvc multi-project, so base images come through Harbor's
# Docker Hub proxy cache under the same URL as the app images.
ARG BASE_REGISTRY=docker.io/library

FROM ${BASE_REGISTRY}/maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY .mvn/ .mvn/
COPY src/ src/
# .mvn/settings.xml mirrors every dependency and plugin through the todomvc-maven
# proxy cache. The project is public, so the build needs no credential.
# The jar is renamed because CI sets the version per run before packaging.
RUN mvn -s .mvn/settings.xml -B package -DskipTests \
 && mv target/todo-api-*.jar target/app.jar

FROM ${BASE_REGISTRY}/eclipse-temurin:21-jre-alpine
RUN addgroup -S app && adduser -S -G app app
USER app
WORKDIR /app
COPY --from=build /build/target/app.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
