# zigpeek is Python; freeze it into one executable so the final image has no Python.
FROM python:3.12-slim-bookworm AS zigpeek
ARG ZIGPEEK_VERSION=0.5.1
RUN apt-get update && apt-get install -y --no-install-recommends binutils \
    && pip install --no-cache-dir "zigpeek==${ZIGPEEK_VERSION}" "pyinstaller==6.*" \
    && printf 'import sys\nfrom zigpeek.cli import main\nsys.exit(main())\n' > /tmp/entry.py \
    && lib="linux-$(uname -m)" \
    && wt="$(python -c 'import os, wasmtime; print(os.path.dirname(wasmtime.__file__))')" \
    && pyinstaller --onefile --name zigpeek --collect-all zigpeek --collect-all wasmtime \
        --add-binary "$wt/$lib/_libwasmtime.so:wasmtime/$lib" \
        --distpath /out --workpath /tmp/build --specpath /tmp/build /tmp/entry.py

FROM node:24-bookworm-slim
ARG PI_VERSION=1.4.0
ARG ZIG_VERSION=0.17.0
ARG ZIG_PUBKEY=RWSGOq2NVecA2UPNdBUZykf1CCb147pkmdtYxgb3Ti+JO/wCYvhbAb/U

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl fd-find git jq minisign ripgrep xz-utils \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}"

RUN name="zig-$(uname -m)-linux-${ZIG_VERSION}" && cd /tmp \
    && curl -fsSLO "https://ziglang.org/download/${ZIG_VERSION}/${name}.tar.xz" \
    && curl -fsSLO "https://ziglang.org/download/${ZIG_VERSION}/${name}.tar.xz.minisig" \
    && minisign -Vm "${name}.tar.xz" -P "${ZIG_PUBKEY}" \
    && tar -xJf "${name}.tar.xz" -C /opt && rm "${name}".tar.xz* \
    && ln -s "/opt/${name}/zig" /usr/local/bin/zig

COPY --from=zigpeek /out/zigpeek /usr/local/bin/zigpeek
RUN mkdir -p /root/.agents/skills/zigpeek && printf '%s\n' \
    '---' \
    'name: zigpeek' \
    'description: Look up Zig stdlib APIs and @-builtins with the zigpeek CLI instead of guessing. Run `zigpeek info` first.' \
    '---' \
    'Run `zigpeek info` before writing or reviewing Zig. It explains search, get and builtins.' \
    > /root/.agents/skills/zigpeek/SKILL.md

# gh hands GITHUB_TOKEN to git for github.com only; SSH remotes are rewritten to HTTPS so it applies.
RUN git config --system credential.https://github.com.helper '!gh auth git-credential' \
    && git config --system url.https://github.com/.insteadOf git@github.com: \
    && git config --system --add url.https://github.com/.insteadOf ssh://git@github.com/ \
    && git config --system safe.directory '*'

ENV PI_SKIP_VERSION_CHECK=1 GH_NO_UPDATE_NOTIFIER=1
WORKDIR /workspace
CMD ["pi"]
