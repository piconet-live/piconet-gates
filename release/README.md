# release: the launcher's releases (private)

How a Piconet release is made, from the game build to the installer and the update feed on GitHub. Since 0.5.0 Beta
(the owner, 2026-10-25) players install the launcher with Setup and it updates itself with
[Velopack](https://velopack.io) from the GitHub releases of
[piconet-live/piconet-launcher](https://github.com/piconet-live/piconet-launcher). The public repositories hold no
server address and no release tooling: this script is where a stack's address goes into a launcher, and where a
release is uploaded.

## One command

```
STACK=A release/release.sh v050 --list          # the steps; nothing is started
STACK=A release/release.sh v050                 # the build, the copy, the installer, the feed: nothing uploaded
STACK=A release/release.sh v050 --from pack     # after a stop: go on at that step
STACK=A RELEASE=1 release/release.sh v050 --from upload    # the owner's word: publish it
```

Run it from these gates checked out where the runner's `port/setup/pins.tsv` says (`REPO_GATES`, `port/gates`), with
the service and the launcher checked out beside the runner (`REPO_SERVICE`, `REPO_LAUNCHER`: `../piconet-service`,
`../piconet-launcher`). The runner and the launcher must be clean, at the commits being released: the run records
both, with the stack, the kind and the channel, in `W/release/NAME/commits`, and stops before any step if a checkout
moved.

| Step | What it runs | Leaves |
|---|---|---|
| `build` | the runner's `port/build/build.sh NAME` (`PROFILE` and `PORT_PYTHON`, a Windows `python.exe` with keystone, as it takes them): the targets of the runner's CMake superbuild (preset `windows`) in order, the game folder and a staged launcher, made with no stack (the build gets no `STACK`, `STACK_ADDRESS` or `KIND`: the stack goes in at `package`) | `W/port/bundle-NAME`, `game-NAME`, `runner-NAME`, `W/work/mod-cg-NAME` |
| `package` | the runner's `port/build/package.sh` with `STACK`, `STACK_ADDRESS` (`stacks.py address STACK` in the service) and `KIND=public` | the player copy, checked, in `W/release/NAME/copy/dist` |
| `installer` | the copy laid out as the installed folder: the launcher's folder (`app/`) at the top, `recomp/` and `source/` beside it, the copy's marker (`portable-copy.txt`) replaced by `installed-copy.txt` (both named in the launcher's `Install.cs`) | `W/release/NAME/installer` |
| `previous` | `vpk "[win]" download github`: the newest release's full package, for the delta | `W/release/NAME/releases` |
| `notes` | this version's section of `PATCH-NOTES.md` in the docs (`DOCS`, else `../piconet-docs` beside the runner): the section under `## Version VERSION · build ... (date)`, its heading left out. Refused when there is none or it is empty: the "Next build (not released)" heading takes the build's name when it is handed out, before this step | `W/release/NAME/notes.md`, printed in the step's log |
| `pack` | `vpk "[win]" pack`: pack id `Piconet.Launcher`, the copy's version, main program `Launcher.App.exe`, the app's icon, the splash shown while Setup installs (`release/splash.png`, the BETA badge), channel `beta`, and the portable zip; signed only with `SIGN=azure` | `releases/`: the Setup program (expected `Piconet.Launcher-beta-Setup.exe`), the portable zip (`Piconet.Launcher-beta-Portable.zip`), the full and delta packages, `releases.beta.json`, `assets.beta.json` (what upload sends) |
| `upload` | `vpk "[win]" upload github --publish`, the token from `TOKEN_FILE`, by default `~/.config/fzgx/github-token-classic` (the fine-grained `github-token` gets 403): **only with `RELEASE=1`**; otherwise it prints the command | a release `vVERSION` on piconet-live/piconet-launcher, at the launcher's commit |
| `site` | `release/site.py`: in the site's checkout (`SITE`, else `../piconet-site` beside the runner; refused with changes not committed), the version's notes page `src/content/notes/X-Y-Z.md` (the same section of `PATCH-NOTES.md`, its date from the heading, a summary and highlights drafted from the first sentences of the notes' first bullets; a page there already is kept) and `src/data/release.json` (the GitHub link to the Setup, its size, SHA-256). Nothing is committed: read the draft, edit the summary and highlights, then commit, merge and deploy the site after the upload. A test build skips it | the two files changed in the site's checkout |

Each step's log is `W/release/NAME/logs/NN-step.log`; `steps.tsv` has each step's status, seconds and time.
`--from STEP` goes on at a step when every step before it ended well in this run. The monorepo's progress file and
its stop handling (`scripts/progress.sh`, `end_started.py`) did not come over in the split: a run that is stopped
with Ctrl+C ends the step in front, and a step that started games or builds may leave them to end by themselves.

**The portable zip** (since 0.5.2) is Velopack's: the installed folder as Setup lays it out (`Update.exe`, a
`Piconet Launcher.exe` that starts the launcher, the package's files in `current/`), with Velopack's `.portable` at its
top. Unzipped anywhere, it updates itself from the same feed as an installed launcher, and keeps its data in `data/`
beside `current/` (the launcher's `Install.cs`: `installed-copy.txt` in the libraries' folder and `.portable` above it),
since every update replaces `current/` whole. Checked with a trial pack of v051's installer folder (2026-10-28): the zip
holds `.portable`, the stub, `Update.exe` and `current/installed-copy.txt`, and `assets.beta.json` lists it as
"Portable", which upload sends with Setup. A launcher before 0.5.2 in that zip would keep its data in the player's own
folder: never pack the zip from an older launcher.

The installer differs from the player copy by the one marker file, and by the top-level program and read-me it
leaves out: everything package.py refuses in a copy (game data, a person's name, a link, a launcher not made for the
stack, a part whose manifest does not match) is refused before the installer exists.

## Where the launcher reads its updates

The launcher reads the feed through GitHub's "latest release" download link,
`https://github.com/piconet-live/piconet-launcher/releases/latest/download/releases.beta.json`, with Velopack's plain
web source (`Launcher.App/Updates.cs`, `Branding.UpdateFeed`). That link is served by GitHub's file servers, not its
API: no rate limit, no token in the launcher. Velopack's GitHub source asks the API, which allows 60 requests an
hour from one address without a token (one LAN party would use that up), and a token cannot ship in a public
program. What follows from it:

- **The release's text is its patch notes** (`notes`, then `vpk pack --releaseNotes`): upload puts them on the GitHub
  release, which is public, and the launcher's update can show them. So a released section of `PATCH-NOTES.md` is
  written for players: plain lines, no person named.
- **Never upload a release as a pre-release or a draft** (`--pre`, or without `--publish`): "latest" is the newest
  release that is neither, so players would not see it. The beta is a channel, not a pre-release.
- **The feed of the newest release is the only one read.** A player one version behind gets the delta; a player
  further behind finds no delta chain there and downloads the full package (Velopack does that by itself).
- **One channel per release.** If a second channel comes (a stable one beside beta), both channels' files must be
  in the newest release, or the feed moves elsewhere (another repository, or a static host).
- **Taking a release back**: delete the release (or mark it a pre-release) on GitHub: "latest" falls back to the one
  before. Launchers that already updated stay on it (no downgrade); fix forward with a new version.

The version is the launcher's (`VersionPrefix` in its `net/Directory.Build.props`, as the copy's record has it). Each
release must have a higher version than the one before, or no launcher updates to it.

## The first release

There is no earlier release to make a delta from: `FIRST_RELEASE=1` makes the step `previous` download nothing.
Players of the unzipped copies (0.4.0 and earlier) install with Setup, then use **Bring over an older copy…** (the
first screen, or Settings, Launcher) to copy their settings, tag, replays, memory card and prepared game files into
`%LOCALAPPDATA%\fzgx-launcher`; their old folder is left as it was.

## Signing

Off by default; Windows' SmartScreen warns at an unsigned Setup.exe ("Windows protected your PC", More info, Run
anyway). The owner's plan (2026-10-25): a company first, then Azure Artifact Signing (formerly Trusted Signing).
`SIGN=azure` signs every program vpk packs and Setup.exe through `SIGN_TEMPLATE`, which vpk runs with `{{file}}` in
place of the files' paths. The default template is the .NET Foundation's `sign` tool (it runs on Linux:
`dotnet tool install -g sign --prerelease`), with three placeholders to fill in from the Azure portal:

| Variable | What |
|---|---|
| `AZURE_SIGN_ENDPOINT` | the account's region endpoint, `https://REGION.codesigning.azure.net` |
| `AZURE_SIGN_ACCOUNT` | the Artifact Signing account's name |
| `AZURE_SIGN_PROFILE` | the certificate profile's name (public trust) |

The login is the Azure CLI's (`az login`) or a service principal's (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
`AZURE_CLIENT_SECRET`). The script refuses `SIGN=azure` while a placeholder is left. Before the first signed
release, check the `sign` tool's subcommand and option names against its current help, and sign one test file.

## Not tested yet

Written 2026-10-25 under the owner's rule of one final test pass: none of the steps from `installer` on has run.
Checked on 2026-10-25: GitHub's `releases/latest/download/FILE` link answers with the query Velopack's web source
adds (`?arch=x64&os=win&rid=...`): a 302 to the release's own download and a 200 for the file. To check in that pass:
vpk's cross-packing for Windows from WSL (`"[win]"`), the Setup program's exact name, the delta from a downloaded release,
Setup on a clean Windows user, an update from one release to the next (the launcher's left column says "Update
ready", "Restart to update" puts it in), the update refused while a game runs, and "Bring over an older copy" on a
0.4.0 copy.
