# Configurable deployment validation

The configurable deployment workflow was checked on 2026-09-09. This is a maintainer record; the public README assumes the operator already has a resolved and ICP-filed domain.

## Local checks

- Production-format configuration was created through the actual noninteractive CLI, then previewed without host changes.
- The build was exercised with two different reserved test domains, optional SSH publishing enabled and disabled, HTML-sensitive display text, and invalid hostname/key/filing inputs.
- Release manifests rejected tampered and unlisted files. Repeated builds produced identical archives in the same runtime.
- The extracted server bundle's actual entry point was run repeatedly in dry-run mode. Python bytecode caches are disabled so execution does not invalidate a release's file manifest.
- Caddy main-file integration preserves unrelated blocks, reuses existing top-level import globs, and requires explicit adoption of the older single-site layout.
- Backup restoration was checked for file contents, permissions, newly introduced files, and the previous release pointer.
- The six existing stash protocol tests passed. The suite contained 20 tests at the time of this validation.
- For the existing internal hostname, generated mihomo install/sub/restart bytes remained identical to the previous working scripts.

## Internal host integration

The self-contained server bundle was transferred to the authorized `aliyunECS` host and verified with its archive checksum. The old single-site layout was adopted with `--internal-test --local --adopt-existing`.

The full command installed the release, created the managed Caddy import and state file, validated Caddy/systemd definitions, activated the socket/service, and passed HTTPS checks via loopback with normal certificate validation.

A temporary marker was uploaded to an initially empty channel 7. Repeated deployment preserved the entire Caddy fragment, token hash, and marker. An actual rollback restored the old layout while retaining that channel content. Redeployment adopted the old layout again and passed HTTPS verification. Both `/ssh/key.pub` and the compatibility alias `/ssh/linz.pub` returned the same existing public key. The marker was then removed only if its contents still matched the test payload; the original channel state was restored.

The verified existing token value was copied from the operator's legacy private location to `/etc/linspace/stash-token`, with mode 0600. Its value was not changed or included in a build or log intended for sharing.

Host records are under `/root/linspace-v2-review-20260909/`; managed deployment snapshots are under `/var/backups/linspace/`. The earlier deployment record remains in [the historical log](validation-2026-09-09.md).

## Later deployment from the home checkout

A subsequent session cloned the GitHub repository into `/root/linspace` on `aliyunECS`. Since the project changes were still uncommitted, the clone at initial commit `a6574bd03e59f1cc316d10ca2f21402cd333cf90` was overlaid with the 51 current source files and checked against a source inventory. No commit or push was made.

The existing domain, public key, and published Claude settings were selected through `./linspace configure --non-interactive --internal-test`. The resulting configuration was saved at `local/site.json`. From that checkout, `./linspace check`, the deployment dry-run, deployment, and explicit loopback HTTPS verification all passed. Twenty tests ran on the server; the public key, Claude settings, token value, and stash content hashes matched their pre-deployment values.

The deployment record is `/root/linspace/local/deployment-result.json`, with additional records under `/root/linspace-home-deploy-20260909/`. The uncommitted overlay must be reconciled before pulling a later published revision; preserve the ignored `local/` configuration and inputs. This paragraph records that session's state, not the current Git status of any future checkout.

## Limits

These integration tests used an existing Debian/Ubuntu host with Caddy 2.11.4, not a newly provisioned blank VM. The missing-Caddy path follows the official apt installation procedure and the initial-config branch is unit-tested. Public access through a completed filing was not tested on this internal hostname. Production-mode configuration and generation were tested locally; a real public domain remains the operator's prerequisite.

A warning about an unrelated `snapd.service` directive was emitted by the host's systemd verifier; the managed units validated successfully. No unrelated service configuration was changed.
