# zigpeek-offline

Data wheel for [`zigpeek`](https://github.com/TanGentleman/zigpeek)'s
`[offline]` extra. Ships a prefetched `sources.tar` + `langref.html`
bundle so `uv tool install 'zigpeek[offline]'` works with no network at
first run.

The bundle is downloaded from `ziglang.org` at wheel-build time by the
hatch hook in `hatch_build.py`. Released in lockstep with `zigpeek`
(pin: `==X.Y.Z`).

The bundled version is `master` (Zig 0.17-dev), so the wheel ships a
snapshot of whatever master docs were current when it was built. Run
`zigpeek prefetch --refresh` to pull newer master docs past the snapshot.
