class AcmeHello < Formula
  desc "Internal tool published to Harbor"
  homepage "https://git.internal/acme/acme-hello"
  url "https://8gcr.container-registry.dev/v2/internal-tools/acme-hello/blobs/sha256:230b49fcbb8f7ffb703c315e84665b4a0a4403201e3a8ca906fbf6ef01889845",
      using: CurlGitHubPackagesDownloadStrategy
  version "1.0.0"
  sha256 "230b49fcbb8f7ffb703c315e84665b4a0a4403201e3a8ca906fbf6ef01889845"

  def install
    bin.install "acme-hello"
  end

  test do
    assert_match "1.0.0", shell_output("#{bin}/acme-hello")
  end
end
