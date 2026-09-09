# Pinned GeoIP data

[manifest.json](manifest.json) identifies the bundled GeoIP snapshot by filename,
uncompressed size, and SHA256 hashes for both compressed and uncompressed data.
The repository stores it as gzip to avoid checking in an approximately 18 MB
uncompressed file. The offline build validates the compressed checksum,
decompresses the asset, and validates its checksum and size before adding it to
the public site and release bundle.

The uncompressed SHA256 is:

```text
2bb7877d772191daa2cac46cf4c530b19fab76b5f870bc431d5767bc933a34d4
```

The snapshot is pinned and is not updated during a build. Its manifest is the
local integrity record. The baseline configuration names the MetaCubeX
meta-rules-dat GeoIP feed, but the exact upstream commit and a separate data
license for this snapshot have not been established. The project's MIT license
does not establish a new license for third-party data.

For asset and version update steps, see [Contributing](../CONTRIBUTING.md).
