# Maven hosted and proxy repositories

[← README](../README.md) · [Detailed Maven behavior →](04-maven.md)

This guide starts with an empty Maven setup. It creates two Harbor projects:

| Project | Purpose | Client URL |
|---|---|---|
| `maven-hosted` | Publish and consume your packages | `https://harbor.example.com/maven/maven-hosted` |
| `maven-proxy` | Cache dependencies and plugins from Maven Central | `https://harbor.example.com/maven/maven-proxy` |

Keep these projects separate at first. It makes permissions and failures easier
to understand.

## Before starting

You need:

- a Harbor instance with Maven support,
- permission to create projects and registry endpoints,
- a Harbor account with push and pull access,
- Java and Maven.

Check the client tools:

```bash
java -version
mvn -version
```

Replace `harbor.example.com` in every example with your Harbor hostname.

If **Maven Central** is missing from the registry provider list, ask the Harbor
administrator to allow Maven in the registry provider list. The API may still
support Maven when the portal does not list it. The
[registry setup guide](02-harbor-setup.md) shows the API alternative.

If a `/maven/` URL returns the Harbor HTML page, ingress sent the request to the
portal. Ask the administrator to route `/maven/` to Harbor core.

## 1. Create a hosted project

1. Sign in to Harbor.
2. Open **Projects**.
3. Select **New Project**.
4. Enter `maven-hosted`.
5. Leave **Proxy Cache** disabled.
6. Select public or private access.
7. Create the project.

Use this repository URL:

```text
https://harbor.example.com/maven/maven-hosted
```

For a private project, add your account as a project member. Use **Developer**
for publish and pull access. Use **Guest** for pull-only access.

For automation limited to this project, create a project robot account instead.
Grant repository push and pull. Copy the exact robot username and secret when
Harbor displays them.

This guide later uses the same credential for two projects. Use one human account
that belongs to both projects, or a system robot with push and pull on
`maven-hosted` and pull on `maven-proxy`. A project robot belongs to one project.

## 2. Configure Maven credentials

Create `~/.m2/settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
  <servers>
    <server>
      <id>harbor-hosted</id>
      <username>${env.HARBOR_USERNAME}</username>
      <password>${env.HARBOR_PASSWORD}</password>
    </server>
  </servers>
</settings>
```

Set credentials without placing them in `pom.xml`:

```bash
export HARBOR_USERNAME='your-user-or-exact-robot-name'
export HARBOR_PASSWORD='your-password-or-robot-secret'
chmod 600 ~/.m2/settings.xml
```

Maven matches credentials by `<id>`. The server id must match the repository id
used below.

## 3. Publish a release

Need a sample package? Generate one with known coordinates:

```bash
mvn -B archetype:generate \
  -DgroupId=com.example \
  -DartifactId=demo \
  -Dversion=1.0.0 \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DarchetypeVersion=1.5 \
  -DinteractiveMode=false
cd demo
```

Add this block inside `<project>` in `demo/pom.xml`, before the closing
`</project>` tag:

```xml
<distributionManagement>
  <repository>
    <id>harbor-hosted</id>
    <name>Harbor releases</name>
    <url>https://harbor.example.com/maven/maven-hosted</url>
  </repository>
  <snapshotRepository>
    <id>harbor-hosted</id>
    <name>Harbor snapshots</name>
    <url>https://harbor.example.com/maven/maven-hosted</url>
  </snapshotRepository>
</distributionManagement>
```

Use a release version such as `1.0.0`, then publish:

```bash
mvn deploy
```

Expected result: `BUILD SUCCESS`. Harbor shows the package under
`maven-hosted`.

Release versions are immutable. If changed files are deployed again with the
same version, Harbor returns `409 Conflict`. Increase the version.

## 4. Publish a snapshot

Change the sample package's top-level version to one ending in `-SNAPSHOT`:

```bash
mvn versions:set -DnewVersion=1.1.0-SNAPSHOT -DgenerateBackupPoms=false
```

Publish it:

```bash
mvn deploy
```

Maven sends the snapshot to `<snapshotRepository>`. Consumers can request
`1.1.0-SNAPSHOT`; Maven resolves the current timestamped build.

## 5. Consume a hosted package

Create a separate consumer project. Run this from the directory that contains
`demo`:

```bash
cd ..
mvn -B archetype:generate \
  -DgroupId=com.example.consumer \
  -DartifactId=consumer \
  -Dversion=1.0.0 \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DarchetypeVersion=1.5 \
  -DinteractiveMode=false
cd consumer
```

Add these blocks inside `<project>` in `consumer/pom.xml`, before the closing
`</project>` tag. These coordinates match the release published above. For your
package, use its actual `groupId`, `artifactId`, and `version`.

```xml
<repositories>
  <repository>
    <id>harbor-hosted</id>
    <url>https://harbor.example.com/maven/maven-hosted</url>
  </repository>
</repositories>

<dependencies>
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>
```

Resolve it:

```bash
mvn dependency:resolve
```

Use a clean local cache when testing the repository itself:

```bash
mvn -Dmaven.repo.local="$(mktemp -d)" dependency:resolve
```

## 6. Create a Maven Central proxy

Harbor administrator:

1. Open **Administration → Registries**.
2. Select **New Endpoint**.
3. Select **Maven Central**.
4. Name it `maven-central`.
5. Use `https://repo.maven.apache.org/maven2`.
6. Test the connection.
7. Save the endpoint.

Create the proxy project:

1. Open **Projects**.
2. Select **New Project**.
3. Enter `maven-proxy`.
4. Enable **Proxy Cache**.
5. Select `maven-central`.
6. Select public or private access.
7. Create the project.

For a private proxy, add the account used earlier as a Guest, or grant proxy pull
to the same system robot.

Use this proxy URL:

```text
https://harbor.example.com/maven/maven-proxy
```

## 7. Route Maven through the proxy

Add a mirror to `~/.m2/settings.xml`. Keep the hosted server entry from the
earlier example.

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
  <mirrors>
    <mirror>
      <id>harbor-proxy</id>
      <name>Harbor Maven Central proxy</name>
      <url>https://harbor.example.com/maven/maven-proxy</url>
      <mirrorOf>*,!harbor-hosted</mirrorOf>
    </mirror>
  </mirrors>
  <servers>
    <server>
      <id>harbor-hosted</id>
      <username>${env.HARBOR_USERNAME}</username>
      <password>${env.HARBOR_PASSWORD}</password>
    </server>
    <server>
      <id>harbor-proxy</id>
      <username>${env.HARBOR_USERNAME}</username>
      <password>${env.HARBOR_PASSWORD}</password>
    </server>
  </servers>
</settings>
```

`mirrorOf` redirects dependencies and Maven plugins. The `!harbor-hosted`
exclusion keeps packages from that repository pointed at the hosted project.
Remove the exclusion when no hosted project is used.

`*` also redirects JitPack, vendor repositories, and other repositories declared
by dependencies. This proxy has only Maven Central as its upstream, so those
packages will not resolve. Add exclusions for repositories that must remain
direct, for example `*,!harbor-hosted,!jitpack`.

Credentials for `harbor-proxy` are unnecessary when the proxy project is public.

## 8. Test the proxy

Resolve a Maven Central package through Harbor with an empty local cache:

```bash
mvn -U -Dmaven.repo.local="$(mktemp -d)" dependency:get \
  -Dartifact=org.apache.commons:commons-lang3:3.17.0
```

Expected result:

1. Maven downloads from `harbor-proxy`.
2. Harbor fetches the package from Maven Central on the first request.
3. Package appears in the `maven-proxy` project.
4. Later requests can use the Harbor copy.

The local cache must be empty when testing. Otherwise Maven may return a local
file without contacting Harbor.

## Common errors

| Error | Likely cause | Fix |
|---|---|---|
| `401 Unauthorized` | Missing credentials or mismatched server id | Check environment variables and make ids match |
| `403 Forbidden` while reading | Account lacks pull permission | Grant Guest or robot pull access |
| `403 Forbidden` while deploying | Account lacks push permission | Grant Developer or robot push access |
| `404 page not found` | Wrong project URL, missing package, or proxy miss | Check `/maven/<project>` and test upstream |
| HTML returned instead of a POM | `/maven/` reached Harbor portal | Fix ingress routing to Harbor core |
| `409 Conflict` | Release version already contains different files | Publish a new version |
| Cached “not found” result | Maven stored an earlier failure | Retry with `mvn -U` or use a clean local cache |
| TLS trust error | Maven does not trust Harbor certificate | Install the Harbor CA in the Java truststore; do not disable TLS checks |

## Next

- [Detailed Maven behavior](04-maven.md): metadata, checksums, immutability, and known proxy behavior
- [Harbor setup](02-harbor-setup.md): API provisioning and keyless GitHub Actions authentication
- [Pipeline](06-pipeline.md): publish Maven, npm, and images from CI
