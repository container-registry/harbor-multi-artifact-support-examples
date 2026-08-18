# syntax=docker/dockerfile:1

# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21 AS build

# .mvn/settings.xml mirrors every dependency AND plugin through the registry, which is
# what this repo is demonstrating. The image build defaults to the mirror-less settings
# so `docker build` works for anyone; CI switches it to .mvn/settings.xml once its
# preflight confirms the registry's Maven endpoint is reachable.
#
# If you force the mirrored settings while that endpoint is NOT routed to core, Maven
# saves the web UI's HTML as a .pom and fails with:
#   Non-parseable POM ...: Expected root element 'project' but found 'html'
# See docs/00-environment.md.
ARG MAVEN_SETTINGS=.mvn/settings-upstream.xml

WORKDIR /build

# Copy the poms before the sources. This only orders the COPY layers; the single
# RUN below is still invalidated by any source edit, so dependencies are
# re-resolved on every source change. Splitting the resolve into its own RUN would
# fix that, at the cost of relying on dependency:go-offline, which under-resolves
# for some plugins. For a demo build the simpler form is the better trade.
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
