// harbor-sa-credential-provider is a kubelet image credential provider
// (KEP-4412). The kubelet mints a token for the pulling pod's service account,
// with the audience set in the CredentialProviderConfig, and passes it in on
// stdin. Harbor accepts that token as the Basic password of a federated robot,
// so the provider only has to hand it back paired with a username.
package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"
)

type request struct {
	Image               string `json:"image"`
	ServiceAccountToken string `json:"serviceAccountToken"`
}

type authConfig struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type response struct {
	Kind          string                `json:"kind"`
	APIVersion    string                `json:"apiVersion"`
	CacheKeyType  string                `json:"cacheKeyType"`
	CacheDuration string                `json:"cacheDuration,omitempty"`
	Auth          map[string]authConfig `json:"auth"`
}

func main() {
	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fail("decode request: %v", err)
	}
	if req.ServiceAccountToken == "" {
		fail("no serviceAccountToken in request; is tokenAttributes set in the CredentialProviderConfig?")
	}
	host := strings.SplitN(req.Image, "/", 2)[0]
	resp := response{
		Kind:         "CredentialProviderResponse",
		APIVersion:   "credentialprovider.kubelet.k8s.io/v1",
		CacheKeyType: "Registry",
		Auth:         map[string]authConfig{host: {Username: "jwt", Password: req.ServiceAccountToken}},
	}
	// Caching the credential past the token's expiry would make later pulls 401.
	if exp, ok := expiry(req.ServiceAccountToken); ok {
		if d := time.Until(exp) - time.Minute; d > 0 {
			resp.CacheDuration = d.Round(time.Second).String()
		}
	}
	if err := json.NewEncoder(os.Stdout).Encode(resp); err != nil {
		fail("encode response: %v", err)
	}
}

func expiry(token string) (time.Time, bool) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return time.Time{}, false
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return time.Time{}, false
	}
	var claims struct {
		Exp int64 `json:"exp"`
	}
	if json.Unmarshal(raw, &claims) != nil || claims.Exp == 0 {
		return time.Time{}, false
	}
	return time.Unix(claims.Exp, 0), true
}

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}
