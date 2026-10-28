# Example tap: internal tools served by Harbor

`Formula/acme-hello.rb` installs a tool your organisation builds itself. The
formula lives in git; the binary lives in the private Harbor OCI project
`internal-tools`. See [08-homebrew.md](../docs/08-homebrew.md#5-publish-your-own-tools).

`brew tap` needs a git repository root, so copy this directory into its own
repository on your git server (by convention named `homebrew-<tap>`):

```bash
brew tap acme/tools https://git.internal/acme/homebrew-tools
brew install acme/tools/acme-hello
```

The formula points at `8gcr.container-registry.dev`, where
`internal-tools/acme-hello:1.0.0` was pushed on 2026-10-28.
