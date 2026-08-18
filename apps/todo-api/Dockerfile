# syntax=docker/dockerfile:1

# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21 AS build

# The settings file carries a mirrorOf=* entry, so the Harbor Maven proxy must be
# reachable for this stage to resolve anything at all. There is no "fall back to
# central" switch: pointing MAVEN_SETTINGS at an empty/absent file is not a working
# escape hatch, because Maven then also loses the <server> credentials. If the proxy
# is down, build with a settings file that omits the mirror instead.
ARG MAVEN_SETTINGS=.mvn/settings.xml

WORKDIR /build

# Copy the poms first so the dependency layer is cached independently of the sources.
COPY pom.xml .
COPY .mvn/ .mvn/
COPY src/ src/

RUN mvn -s "${MAVEN_SETTINGS}" -B package -DskipTests

# ---- runtime stage ----
FROM eclipse-temurin:21-jre-alpine

RUN addgroup -S app && adduser -S -G app app
USER app

WORKDIR /app
COPY --from=build /build/target/todo-api-0.1.0.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
