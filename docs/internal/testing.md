# Internal testing only

The public README and default deployment path require a resolved, filed domain with complete homepage details. `--internal-test` permits test inputs such as an empty filing number or a reserved example domain. It does not configure a different TLS mode. Never distribute an internal-test release as a production release.

## Default configuration on an internal host

From the repository root, use the same configuration filename as the normal workflow, but pass the internal flag to commands that read it:

```sh
./linspace configure --internal-test
./linspace urls --internal-test
sudo ./linspace deploy --internal-test --local
./linspace verify --internal-test --local
```

Choose the actual internal hostname, a clearly labeled site name, and your public input files. The filing number may be empty in this mode. This is the workflow used by the internal home checkout at `/root/linspace` on `aliyunECS`; its configuration is `/root/linspace/local/site.json`. Omit sudo in a root session.

## Separate test profile

To keep another profile, use `--config` consistently:

```sh
./linspace configure --config local/site.internal.json --internal-test
./linspace build --config local/site.internal.json --internal-test
sudo ./linspace deploy --config local/site.internal.json --internal-test --local
./linspace verify --config local/site.internal.json --internal-test --local
```

The wizard copies a selected public key to the shared `local/ssh.pub` path. If profiles need different keys, keep distinct public-key files and set their paths manually in each JSON file. Use repository-relative or explicit absolute paths in saved configuration so a later sudo command reads the same files.

## TLS and verification

`--local` overrides DNS resolution for that request, connecting to `127.0.0.1` with the configured hostname. It still validates the TLS certificate. It neither changes public DNS records nor proves external reachability or filing approval. An example domain can be used for offline builds; a live HTTPS check still needs a valid certificate/trust setup for its hostname. Diagnose certificate failures through Caddy's logs rather than reporting a skipped check as a pass.

For an extracted internal server bundle, use:

```sh
sudo bash linspace --internal-test --local
python3 verify.py --local
```

## Adoption and later production use

For an older single-site linspace installation, add `--adopt-existing` only after inspecting its Caddyfile. The deployer creates a managed-state snapshot. Existing token hashes and channel data are preserved. A legacy plaintext token is not automatically located or copied; new token files are created on first generation or explicit rotation.

The separate `linspace-mihomo-target.tar.gz` bundle supports target-side tests while the public site is unavailable. Its README documents the pinned local GeoIP option; engine downloads remain online. Do not install a proxy on the web host merely to publish its scripts.

Once filing and public reachability are ready, rerun `./linspace configure` with the actual approved website name and complete filing number, then deploy and verify without `--internal-test` or `--local`. Pass the same `--config` path if you use a named profile.

The [historical validation record](validation-2026-09-09.md) and [configurable-deployment record](deployment-v2-validation.md) describe specific earlier test sessions, not guarantees for later revisions.
