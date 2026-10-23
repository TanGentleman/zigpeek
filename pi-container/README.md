# Pi in an Apple container

Run [Pi](https://pi.dev) on OpenRouter inside an Apple [`container`](https://github.com/apple/container)
VM. The VM has no route to the internet. A proxy on your Mac is the only way out, and it
allows GitHub plus OpenRouter and nothing else.

```text
Mac
├── ~/.config/pi-container/env          both keys, mode 600, never mounted into the VM
├── proxy.py on 127.0.0.1:8888
│     GitHub .............. tunnel
│     openrouter.ai ....... the proxy adds the real key
│     anything else ....... refused
└── container VM, deleted when Pi exits. Host-only network (no internet route)
      OPENROUTER_API_KEY    the placeholder sk-or-v1-placeholder, not your key
      GITHUB_TOKEN          your token. git sends it inside TLS, so the proxy cannot add it for you
      your project          mounted at the same path, or a private clone with --clone
      pi-agent-home         Pi's settings and sessions
```

The image is tools only: Pi, git, gh, ripgrep, fd, Zig 0.17.0, and zigpeek. Nothing in the
Dockerfile enforces the network. Pi runs as root in the VM, so a firewall rule or a proxy
variable inside the image can be removed. The host-only network cannot.

## Setup

macOS 26, Apple silicon, and Python 3.11 or newer (`brew install python` if `python3` is missing):

```bash
brew install container
container system start          # answer Y to install the default kernel

# once, and again after every reboot. This also turns off iCloud Private Relay.
sudo container system dns create host.container.internal --localhost 203.0.113.113
```

From this folder:

```bash
mkdir -p ~/.config/pi-container
printf 'OPENROUTER_API_KEY=\nGITHUB_TOKEN=\n' > ~/.config/pi-container/env
chmod 600 ~/.config/pi-container/env
open -e ~/.config/pi-container/env       # paste the keys after =, with no quotes

container build -t pi-agent:local .
./run.sh check you/your-repo
```

`check` starts the proxy, confirms the container has the OpenRouter placeholder rather than
your key, prints the key's credit limit, checks GitHub, and checks that `example.com` and a
direct connection are refused. It spends no OpenRouter credits.

## Use

```bash
alias pic=/path/to/pi-container/run.sh    # full path, in ~/.zshrc

cd ~/code/your-repo
pic                      # Pi. Edits land on your Mac
pic pi --continue
pic bash
pic --clone you/your-repo
```

`/model` picks an OpenRouter model (`:free` costs nothing). `/quit` exits and deletes the VM.
Do not run `/login`. That would save a real key into the Pi settings volume.

`run.sh proxy` runs the proxy in the foreground. `run.sh proxy-stop` stops the one `run.sh`
started. A normal `pic` starts it in the background if it is not already up. Refusals are
logged in `~/.config/pi-container/proxy.log`.

## Keys

The env file stays on the Mac. `run.sh` refuses to start unless it is mode 600.

- **OpenRouter** stays in that file. The proxy puts it on the request. The container only has
  `sk-or-v1-placeholder`. Set a credit limit on the key. The container can still spend it,
  by asking the proxy to call OpenRouter, but it cannot read the key.
- **GitHub** is passed into the container. git and `gh` send it inside TLS to github.com, and
  a tunnel proxy cannot see or add that header. Make it a fine-grained token for **one repo**,
  with Contents and Pull requests set to Read and write, Workflows left off, and a short expiry.
  The proxy will not open a connection to any host except GitHub, so the token cannot be sent
  anywhere else. It can still be written into a prompt, which OpenRouter then sees.
- **Commits:** add `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, and
  `GIT_COMMITTER_EMAIL` to the env file.

Pi's install ping and `gh` telemetry are turned off. `pi.dev` is not reachable anyway.

## Limits

- The proxy allows `github.com`, `api.github.com`, `codeload.github.com`,
  `objects.githubusercontent.com`, `raw.githubusercontent.com`, `uploads.github.com`,
  and `openrouter.ai`. Package registries, `ziglang.org`, and everything else are refused.
- The container can still open connections to your Mac, because that is what host-only
  networking is. The proxy listens on 127.0.0.1 only.
- `run.sh` will not mount `~` or `/`. `--clone` keeps the repo in a volume until you `git push`.
  `container volume list` shows `pi-agent-home` and any clone volumes.
- `PI_CPUS` (default 4) and `PI_MEMORY` (default 4G) size the VM.
- Rebuild with `--build-arg PI_VERSION=…` or `--build-arg ZIG_VERSION=…` to upgrade tools.
  The network lock is in `run.sh` and `proxy.py`, so a rebuild is not needed for that.
