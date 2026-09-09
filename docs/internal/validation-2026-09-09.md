# Validation and deployment record — 2026-09-09

**Historical record: this session preceded the configurable deployer. Paths, counts, token handling, and homepage placeholders below describe that earlier build. Use the [current README](../../README.md) and [internal testing guide](testing.md) for current commands.**

The project was built and tested against the operator-designated web host `aliyunECS` and the `zhoulin_fl` container reached through `h20-141`. This record describes the build deployed during that test session. The web host's domain registration was still pending. No Git commit or push was made during this work.

## Local repository checks

| Check | Result |
| --- | --- |
| Offline build on macOS / Python 3.9.6 | Passed |
| Syntax checks | Six Python files and 22 shell files passed at validation time |
| JSON, documentation links, bundle checksums, and archive contents | Passed |
| Stash Unix-socket protocol suite | Six tests passed |
| Repeated builds with the same runtime | Both release archives were byte-identical |
| Git state | Changes left unstaged and uncommitted; MIT license retained |

The protocol suite covers all channels and replacement, UTF-8/NUL rejection without overwriting the old content, exact size boundaries, empty files, clear, method/path limits, and chunked requests.

## Web host: aliyunECS

The existing host used Caddy 2.11.4 and Python 3.10.12. Its SSH public key, all three mihomo scripts, and GeoIP already existed. The mihomo scripts and data already matched the project sources. Claude settings, the homepage, stash routes, and stash services were missing.

The deployment preserved the existing public key, backed up the old site and Caddyfile, republished the verified mihomo bundle, installed the shared Claude settings, added the homepage example, replaced the sole site block with the current Caddyfile, and installed stash with its socket activation and Caddy authentication fragment.

Verification used `curl --resolve linspace.xyz:443:127.0.0.1` on the host with normal TLS certificate validation. This confirmed local HTTPS behavior without relying on public access during filing.

| Check | Result |
| --- | --- |
| All 16 deployed public files | Matched the repository build both on disk and through HTTPS |
| Caddyfile | Matched the repository configuration |
| Homepage, public scripts/key/settings, and GeoIP | Expected 200 responses and media types |
| HTTP redirect | 308 to HTTPS |
| Claude installer route | 302 to `https://claude.ai/install.sh` |
| Unlisted route | 404 |
| Unauthenticated stash write | 401 |
| Caddy configuration and systemd unit validation | Passed |
| Caddy and stash socket | Active |
| Stash end-to-end checks through Caddy | 34 checks passed |
| Stash deployment rerun | Preserved the existing token hash and fragment |
| Stash channel state after testing | All eight channels empty |

The 34 stash checks include uploads and public reads for all eight channels, missing and wrong tokens, invalid UTF-8 and NUL rejection, exact 1 MiB acceptance, excess-size rejection, chunked rejection, the channel-0 alias, authenticated clear, and absent reads after clear. Read responses were also checked for `text/plain`, `no-store`, and `nosniff`.

The initial stash token was generated during deployment and saved as `/root/.config/linspace/stash-token` on the web host, with mode 0600 inside a mode-0700 directory. It was not copied into the repository or printed in the review record. A root-only deployment log also contains the installer's original one-time output.

Backup and operation records on the web host:

```text
/root/linspace-review-20260909/backup/
/root/linspace-review-20260909/stash-test-report.json
/root/linspace-review-20260909/systemd-validation.log
/root/linspace-review-20260909/deployment-complete
/var/backups/linspace-files.Xoi35q/
```

## Target: h20-141 / zhoulin_fl

The designated container runs Ubuntu 24.04.3 on x86_64, as root, with host networking and an existing managed mihomo v1.19.27 process. A brief stop was used to capture a consistent private configuration/cache backup, then the process was restarted before reinstall testing.

| Check | Result |
| --- | --- |
| Local-bundle installer with `--geoip-file` | Passed |
| Existing configuration and private node bytes after reinstall | Unchanged |
| Mirror download and pinned engine checksum | Passed through `gh-proxy.com` |
| Import the existing six private nodes from local YAML | Passed; values and order retained |
| Configuration and private node bytes after subscription import | Still identical to the original snapshot |
| Restart and process status | Passed; managed process running |
| Live HTTPS through `127.0.0.1:7890` | HTTP 200 from `https://www.google.com` |
| SSH key format and import permissions | Passed in an isolated temporary authorization file |
| Existing Claude executable | `/root/.local/bin/claude --version` returned `2.1.266` |
| Existing Claude settings | Exact match with the project settings hash |

The direct GitHub download first timed out after approximately 180 seconds. Its subsequent curl retry was explicitly terminated to exercise the unmodified installer's fallback path. The installer then downloaded through `https://gh-proxy.com/`, verified the pinned compressed checksum, and completed successfully. This was a targeted test of a child download process; no source changes or system networking changes were used.

The installed amd64 engine's SHA256 was:

```text
ab33dead65aaa95bc03b722f155d95f1003ac00517de6726e9b8d56ef9bbec92
```

The container's noninteractive PATH did not include `~/.local/bin`, so the existing Claude executable was checked by its full path. Its configuration was already current and was not replaced. The official installer was not rerun, and interactive Claude authentication was not tested. SSH key import was checked in an isolated file; no account's live `authorized_keys` was changed and no new SSH login was attempted.

Private backups and logs remain inside the container under `/root/linspace-review-20260909/`, mode 0700. The private subscription log contains node names and is retained only there. The backup includes the previous engine, management files, configuration, proxy definitions, and a stopped-process cache snapshot. The subscription program also created its usual private backup under `/var/lib/mihomo/backup-*`.

## Operator step at the time

At this stage, the homepage contained `YOUR_REGISTERED_SITE_NAME` and `YOUR_ICP_FILING_NUMBER` placeholders. The current deployer generates the page from the selected site JSON instead; complete its approved details and use the current production workflow after filing. These historical tests established local host behavior, not public availability or registration approval.
