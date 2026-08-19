# syntax=docker/dockerfile:1

# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21 AS build

# .mvn/settings.xml mirrors every dependency AND plugin through the registry, which is
# what this repo is demonstrating. The image build defaults to the mirror-less settings
# so `docker build` works for anyone with no registry account; CI switches it to
# .mvn/settings.xml once its preflight confirms the Maven endpoint answers.
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

# Falls back the way the pipeline's own Maven job does. A reachable endpoint is not
# proof it can serve a whole dependency tree, and without this the image build is the
# one place a degraded proxy cache fails the run outright instead of degrading.
#
# The jar is renamed here rather than copied by name below: CI sets the version from
# the run number before packaging, so any name with a version in it is wrong by the
# time the runtime stage runs.
RUN mvn -s "${MAVEN_SETTINGS}" -B package -DskipTests \
 || { echo "resolve through ${MAVEN_SETTINGS} failed, retrying against Maven Central"; \
      mvn -s .mvn/settings-upstream.xml -B package -DskipTests; } \
 && mv target/todo-api-*.jar target/app.jar

# ---- runtime stage ----
FROM eclipse-temurin:21-jre-alpine

RUN addgroup -S app && adduser -S -G app app
USER app

WORKDIR /app
COPY --from=build /build/target/app.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
