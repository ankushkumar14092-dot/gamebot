# CAMBC Gemini match agent

This container polls CAMBC for finished ranked matches, saves match statistics
and reviews, then asks Gemini to produce evidence-backed reports. Reports
are written to `matches/ai-agent/batches/`. For at most one new loss per sync,
the workflow can request a minimal source-code fix and benchmark an isolated
candidate on the loss map from both team sides. Candidate source is kept on a
separate local Git branch. The incumbent source is never promoted and no live
submission is made automatically; a passing candidate requires human review
and explicit approval. A small local benchmark cannot guarantee that future
matches will be won.

## Configure

1. Put your Gemini API key in the root `.env` as `GEMINI_API_KEY=...`. The
   `.env` file is ignored by git. Never put the key in `compose.yaml` or commit it.
2. Review the model and team settings in `.env`. The defaults select
   `gemini-3.8-flash`, team `decrest`, and ranked
   matches. Set `CAMBC_TEAM_ID` to the right team UUID if needed.
3. On Linux, set `PUID` and `PGID` to the IDs returned by `id -u` and `id -g` if
   the default container user cannot write to the mounted `matches/` folder.

## First start

Build the image and create persistent match storage:

```sh
mkdir -p matches
docker compose build
```

Authenticate the CAMBC CLI inside the container. Follow the CLI's login prompt
in the terminal; its home and workspace state are saved in named Docker volumes
and survive container rebuilds:

```sh
docker compose run --rm match-agent cambc login
```

Run one sync and one analysis as a smoke check:

```sh
docker compose run --rm match-agent python tools/fireworks_match_agent.py --once
```

Then start the continuously polling service:

```sh
docker compose up -d
docker compose logs -f match-agent
```

Stop it with `docker compose down`; match reports and the CAMBC login volumes
remain. `docker compose down -v` also deletes the saved CAMBC login state.

## Operations

- Polling defaults to every 300 seconds. Set `POLL_INTERVAL_SECONDS` to change
  it (minimum 30 seconds).
- `CAMBC_LIMIT` bounds the number of recent matches inspected each poll (1–100).
- The AI analyzes one match per request, up to five requests per poll, and
  queues any remaining backlog for later polls. The default generation budget
  is 8,000 tokens per request; actual Gemini usage is billed by token.
- The agent downloads statistics only, avoiding replay bundle bandwidth. Existing
  local replay files remain available to the review scripts.
- Gemini calls use bounded retries and honor `Retry-After` or Gemini retry-delay
  data, with a maximum of six attempts and a five-minute wait per retry.
- Candidate experiments are bounded to one loss per sync by default. Use
  `--max-experiments 0` with `tools/sync_online_matches.py` to disable them.
- A benchmark-passing candidate's report contains the verified `cambc bundle`
  and `cambc submit` command forms. Do not run the submission command until
  you have reviewed the source and benchmark and explicitly approved it.
- Agent state and reports live under `matches/ai-agent/`; source review data
  lives under `matches/online-reviews/`. Both remain on the host and are ignored
  by git.
- View service status with `docker compose ps`. Restart after editing `.env` with
  `docker compose up -d --force-recreate`.
- CAMBC login sessions expire. If syncing reports an authentication error, run
  `docker compose run --rm match-agent cambc login` again.

## Hosting

Docker Compose is the portable deployment target. To run continuously after
your laptop is shut down, deploy this repository on an always-on Linux host with
Docker Compose, copy the `.env` there through a secret-safe channel, then run
the first-start commands. Keep the `.env` file and CAMBC Docker volume private.

## Run in the background on macOS

For this Mac, a LaunchAgent keeps the poller running after VS Code closes and
starts it again at the next login. The Mac must remain awake and connected; this
is not an always-on cloud deployment.

```sh
mkdir -p matches/ai-agent "$HOME/Library/LaunchAgents"
cp deploy/com.gamebot.fireworks-match-agent.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.gamebot.fireworks-match-agent.plist"
launchctl print "gui/$(id -u)/com.gamebot.fireworks-match-agent"
```

View logs in `matches/ai-agent/launchd.log` and `matches/ai-agent/launchd-error.log`.
Stop and remove the service with:

```sh
launchctl bootout "gui/$(id -u)/com.gamebot.fireworks-match-agent"
rm "$HOME/Library/LaunchAgents/com.gamebot.fireworks-match-agent.plist"
```
