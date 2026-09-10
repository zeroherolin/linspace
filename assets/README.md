# GeoIP snapshot

[manifest.json](manifest.json) records the compressed filename, raw size, and compressed/raw SHA256 hashes. Builds verify the gzip file, decompress it, then verify the approximately 18 MB raw snapshot before packaging it for Mihomo.

Raw SHA256:

```text
2bb7877d772191daa2cac46cf4c530b19fab76b5f870bc431d5767bc933a34d4
```

Builds use the pinned snapshot without downloading updates. The configured feed is MetaCubeX meta-rules-dat; the snapshot’s exact upstream commit and separate data license are not recorded. The project's MIT license does not relicense third-party data. Review provenance and checksums when [updating assets](../CONTRIBUTING.md#versions-and-release-validation).
