# zigpeek-offline-data

Companion data wheel for [`zigpeek`](https://github.com/TanGentleman/zigpeek).
Ships a prefetched `sources.tar` + `langref.html` bundle so that

```sh
uv tool install 'zigpeek[offline]'
```

works with no network at first run.

The bundle is downloaded from `ziglang.org` at wheel-build time by the
hatch hook in `hatch_build.py`. End users only see the data files; they
never run the hook.

Released in lockstep with `zigpeek`; pin matches exactly (`==X.Y.Z`).
