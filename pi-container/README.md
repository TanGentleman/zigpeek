# Pi in an Apple container

Run the [Pi](https://pi.dev) coding agent on OpenRouter inside an Apple
[`container`](https://github.com/apple/container) VM, with a GitHub token for one repo.

```text
Mac                                    container VM (one per run, deleted on exit)
~/.config/pi-container/env  ── env ──► OPENROUTER_API_KEY, GITHUB_TOKEN
~/code/your-repo            ── mount ► ~/code/your-repo          (default)
volume pi-clone-owner-repo  ── mount ► /work/repo                (--clone)
volume pi-agent-home        ── mount ► /root/.pi/agent           Pi settings + sessions
```

The image has tools only: Pi, git, gh, ripgrep, fd, Zig 0.17.0 and
[zigpeek](https://github.com/TanGentleman/zigpeek) (a standalone binary, no Python). Keys
come from the env file each time a container starts. git gets the token from `gh`, only for
`github.com`.

## Setup

You need macOS 26 on Apple silicon. Run once:

```bash
brew install container
container system start          # answer Y to install the default kernel
```

Then, from this folder:

```bash
mkdir -p ~/.config/pi-container
printf 'OPENROUTER_API_KEY=\nGITHUB_TOKEN=\n' > ~/.config/pi-container/env
chmod 600 ~/.config/pi-container/env
open -e ~/.config/pi-container/env       # paste the keys after =, no quotes

container build -t pi-agent:local .      # under a minute
./run.sh check you/your-repo             # validates both keys, costs nothing
```

`check` prints your OpenRouter credit limit and usage, `Logged in to github.com`, and the
repo's `HEAD`. It exits non-zero if either key fails.

## Use

```bash
alias pic=/path/to/pi-container/run.sh   # add to ~/.zshrc

cd ~/code/your-repo
pic                                  # Pi on this folder; edits land on your Mac
pic pi --continue                    # resume this folder's last session
pic bash                             # shell with the same keys and mount
pic --clone you/your-repo            # Pi on a clone that exists only in a volume
```

Inside Pi, type `/model` to pick a model (`:free` models cost nothing) and `/quit` to exit.

## Keys

- **GitHub:** create a fine-grained token with access to **only your repo**, **Contents** and
  **Pull requests** set to Read and write, and a short expiry. Without the Workflows
  permission, pushes that change `.github/workflows/` are rejected.
- **OpenRouter:** set a credit limit on the key.
- **Commits:** for Pi to commit as you, add `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`,
  `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` to the env file.

## Limits

- Pi and every command it runs can read both keys and reach any website. The token's
  single-repo scope and the credit limit are what limit the damage. To keep the real key
  away from the agent and allow traffic only to openrouter.ai, use
  [OpenShell](https://docs.nvidia.com/openshell/latest/tutorials/run-pi-with-openrouter).
- Pi runs as root inside the VM, which is not root on your Mac. Running as root avoids
  Apple's root-owned mounts and volumes.
- `run.sh` won't mount `~` or `/`. `--clone` keeps work in a volume until you `git push`.
  `container volume list` and `container volume delete <name>` manage the volumes.
- `PI_CPUS` (default 4) and `PI_MEMORY` (default 4G) size the VM. Apple's default is 1G.
- To upgrade, rebuild with `--build-arg PI_VERSION=…` or `--build-arg ZIG_VERSION=…`.
