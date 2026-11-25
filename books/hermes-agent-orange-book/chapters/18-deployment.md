---
id: hermes-agent-orange-book/deployment
resource: hermes-agent-orange-book
title: "Deploy: From Sending Commands to Sending Installers"
part: "Part 6: Deployment, Security & Boundaries"
order: 18
section_label: "§18"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 83
    last: 88
extraction_status: machine-extracted
---

# Deploy: From Sending Commands to Sending Installers

*Deploy: From Sending Commands to Sending Installers*

Two months ago, installing Hermes meant knowing your way around the command line and editing yaml. Now you can download a desktop app, double-click to install, and open it like any chat app. That's the biggest leap in experience this release brings.

## First, let's clear up one point of confusion

A lot of people get stuck on the same spot the first time they read the Hermes docs: the word "deploy" means two different things here, and once you mix them up everything falls apart.

The first meaning is where the Hermes program itself lives. Your laptop? A $5 cloud server? A Docker container? Or pulled up declaratively with Nix?

The second meaning is which machine the agent runs its shell commands on. It needs to run `pip install` , run your scripts, touch the filesystem — where do those commands land? Locally? On a remote box you SSH into? A throwaway container?

These two layers are independent. You can perfectly well install Hermes on your own laptop while having all its commands run inside an isolated Docker container. The program lives locally, the hands and feet live in the container. The `terminal.backend` field in the config governs the second layer, not the first.

> Remember this: "where it's deployed" is the home of the Hermes process; "where the agent runs commands" is the job site where the agent does its work. There's only ever one home, but the job site can be swapped among six options. Below we'll first cover how to set up the home, then the six job sites.

## Three ways in, from easiest to hardest

There are now three paths to installing Hermes, matched to three kinds of people. I'll order them from lowest barrier to highest.

> Desktop App One-line Script Manual from Source

→ →

## Path one: Desktop App (brand new this release, lowest barrier)

This is the headline feature of this release, and the one I think deserves to be covered first. Hermes now ships an Electron desktop app, available on all three platforms: macOS, Linux, and Windows.

It's just an ordinary desktop application. Install it, open it, and you get a chat window — streaming replies, drag files into the conversation, paste images from your clipboard, a session list, a Cmd+K command palette, and a status bar where you can switch models directly. It updates itself in-app, so you don't have to worry about versions.

Why does this matter? Because it turns Hermes from "a command-line agent" into "an app you can just hand a friend the installer for." Before, if you wanted to get someone onto Hermes, you first had to teach them to set up the environment and type commands. Now you send them an installer, they double-click, and they're chatting. This is the single biggest drop in barrier yet.

## Path two: One-line install script (the default choice, for most people)

If the terminal doesn't scare you off, the one-line script is the fastest proper route. One command, all dependencies handled automatically.

```text
# Linux / macOS / WSL2 / Termux
curl -fsSL https:-/hermes-agent.nousresearch.com/install.sh | bash

# Native Windows (PowerShell, WSL2 no longer required)
iex (irm https:-/hermes-agent.nousresearch.com/install.ps1)
```

Here's a change that matters a lot to longtime users: Windows is finally natively supported. In the old days, Windows users had to wrestle with WSL2 before they could install Hermes. Now a single PowerShell line does it, and the installer will conveniently pull down a roughly 45MB portable MinGit, unpack it under your user directory, never touch the Git in your system, and require no admin rights. Hermes uses this bundled Git to run shell commands, clean and tidy. (The chat panel piece still needs WSL2, but the core install is now decoupled from it.)

The script installs the whole stack of dependencies — uv, Python 3.11, Node.js 22, ripgrep, ffmpeg — on its own, so you don't have to configure them one by one.

| 核 | 心 | 建议 |
| --- | --- | --- |

> For CI or controlled deployments, the installer has a few switches available: `--no-venv --skip-setup --skip-browser --no-skills` , and you can point the data directory anywhere with the `HERMES_HOME` environment variable. When installed as root, it automatically follows the FHS standard layout (code goes to `/usr/local/lib` , commands go to `/usr/local/bin` ), aligned with how Claude Code and Codex CLI do it, which also keeps Docker volume mounts tidier.

## Path three: Manual install from source (for developers)

If you want to read the source or modify Hermes itself, take this path.

```text
git clone https:-/github.com/NousResearch/hermes-agent.git
cd hermes-agent
./setup-hermes.sh # installs uv, builds the venv, installs all deps, symlinks the hermes
command
./hermes # auto-detects the venv, no need to source first
```

One thoughtful detail: `setup-hermes.sh` first figures out whether you're on a desktop/server or on Android Termux. On desktop it uses uv; on Termux it falls back to Python's built-in venv + pip, because uv isn't very reliable on Android. This fork is a hint at first-class mobile support — more on that shortly.

## Six terminal backends: the agent's job sites

Back to that second layer. `terminal.backend` decides where the agent runs its commands, and all six options are present in this release.

| Backend | Purpose | When to pick it |
| --- | --- | --- |
| `local` | Runs directly on the local machine (default) | Local development, least hassle, but agent commands land directly on your machine |
| `docker` | Isolated container | When you want to give the agent a sandbox, so a botched command can't hurt the host |
| `ssh` | Remote server | Commands run on a big remote box while Hermes itself stays local |
| `singularity` | HPC cluster | Running inside a high-performance computing cluster |
| `modal` | Serverless | Cost approaches zero when idle, spins up on demand |
| `daytona` | Serverless | Another serverless option |

The four container-style backends (docker / singularity / modal / daytona) share one set of resource limits, defaulting to 1 CPU core, 5GB of memory, and 50GB of disk, and they can persist the filesystem across sessions. One security default here is worth noting: the docker backend doesn't mount your current directory into the container by default ( `docker_mount_cwd_to_workspace: false` ), so the agent can't accidentally touch files in your workspace.

## Docker deployment: the recommended 24/7 setup

If you want to keep Hermes running long-term, Docker is the approach I recommend most. The official image is `nousresearch/hermes-agent:latest` , and the compose file structure is clean.

The Linux/mac `docker-compose.yml` brings up two services: a `gateway` (running the message gateway, hooking into Telegram, Discord, and so on) and a `dashboard` (the browser management panel). It uses host networking, and all state mounts onto a single volume — your `~/.hermes` directory. To migrate or back up, just copy that one directory.

```text
HERMES_UID=$(id -u) HERMES_GID=$(id -g) docker compose up -d
```

That UID/GID string up front maps the hermes user inside the container to your host identity, so the files it writes out are readable and writable by you. On Windows, Docker Desktop doesn't support host networking, so there's a separate official `docker-compose.windows.yml` that switches to explicit port mappings.

| 注意 |
| --- |

> The comments in this release's compose file spell out the security defaults very plainly — please follow them: ① the dashboard binds to `127.0.0.1` only by default, because it stores your API key, and exposing it raw to your LAN or the public internet without authentication is dangerous; for remote access, go through an SSH tunnel or an authenticated reverse proxy; ② the OpenAI-compatible API server is off by default, and to turn it on you must set both the host and a key — the key is mandatory; ③ don't bypass the image's ENTRYPOINT yourself, since skipping it misses the permission setup and supervision-tree wiring, and the gateway will break.

## The container got a new "house manager": s6-overlay

This is a real low-level change compared to the old version, worth a sentence to unpack.

The old container used tini as PID 1, and its job was simple: reap zombie processes so the container doesn't pile up dead ones. This release switches to s6-overlay, with `/init` as PID 1. It doesn't just reap zombies — it also supervises the main Hermes process, the dashboard, and each profile's gateway, restarting whichever one dies. This makes the multi-process stuff inside the container far more stable.

To avoid burning longtime users, it also leaves a symlink `/usr/bin/tini → /init` , so third-party orchestration templates still pointing at the old path (like certain hosting providers' one-click WebUI setups) won't break. This "swap the foundation but leave a compatibility shim" move is what a mature project should look like.

## $5 VPS: the old selling point hasn't aged, and it's written into the README's first line

An earlier edition of the orange book pushed one idea hard: you don't need an expensive machine — a $5-a-month VPS is enough to keep a 24/7 agent online. I was worried this release might water that down.

Turns out the official team wrote it straight into the first paragraph of the README: "Run it on a $5 VPS, a GPU cluster, or near-zero-cost serverless when idle. It's not tied to your laptop, and while it works in the cloud, you can chat with it from Telegram."

The logic is unchanged: when it's not running a local model, Hermes uses very little, so you stand up a `gateway run` on a VPS, hook it to Telegram or Discord, route the model through a cloud API, and the local box is just a thin relay. This release adds an even more cost-effective combo: run the gateway on the VPS and install the desktop App locally to connect to it remotely. The laptop only handles the pretty interface, while the heavy lifting and the API key live on that cheap remote box.

## Mobile: Termux is a first-class citizen

Here's something the old book didn't cover at all, and a spot where this release can surprise you: Hermes is officially supported on Android Termux — not "barely runs," but properly supported.

The installer detects the Termux environment itself, then switches to the adapted path: no uv (unstable on Android), using Python's built-in venv plus pip instead; it installs the dedicated `.[termux]` dependency set rather than the full package, because the full package drags in a pile of Android-incompatible audio dependencies. There's also a `constraints-termux.txt` that pins a batch of package versions, keeping this install path stable on Android.

A typical setup looks like this: run Termux on your phone and stand up a gateway hooked to Telegram. That turns that old Android phone in your pocket into a 24/7 personal agent server. I think this is an underrated use: a dusty old phone, even cheaper than a $5 VPS.

## Nix / NixOS: for the people who want reproducibility

If you're a NixOS user, or you just like declarative, reproducible deployments, this release fleshed out a complete Nix path that the old book barely mentioned.

It provides a complete flake, supporting all three platforms. Going further, there's a NixOS module ( `services.hermes-agent` ) that lets you pick between two forms: run it as a native systemd service, or run it as a container. The config is written directly in Nix as an attrset, with deep merging. There are also outside community contributors pushing this line, which tells you it's not some afterthought the official team tossed off.

## From "editing yaml" to "clicking a panel"

Finally, one change that isn't about installation but deeply affects the ops experience.

In the old version, to hook Hermes up to a new message channel, add an MCP server, or swap a credential, you had to SSH into the machine and hand-edit that 62KB `cli-config.yaml` . Get one indentation wrong and the whole thing won't start.

This release adds a browser management panel. Message channels, the MCP catalog, credentials, webhooks, memory, the gateway — all of it can be configured by point-and-click on a web page. You no longer have to SSH in and edit yaml just to hook up a new channel. For people who don't enjoy fiddling with config files, this is the line between "usable" and "pleasant to use."

> The through-line of this section: Hermes's deployment backends haven't really changed — still those same six job sites. What's genuinely been renovated is the "how you actually get to use it" layer — three new paths have grown out of it: the desktop App, the browser panel, and the remote thin client. Where you used to need to know how to send commands, now you can just send an installer. With the barrier dropped this far, the audience naturally widens a notch — from developers toward "every heavy AI user."
