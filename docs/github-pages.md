# CIRCLE website deployment

The CIRCLE website is published at:

**https://topherchris420.github.io/circle/**

| Page | What it is | Source |
| --- | --- | --- |
| `/circle/` | The research site: the question, method, one recorded session drawn from its own data, recorded results (including failures), consent, hardware status, and boundaries | [`site/`](../site) |
| `/circle/workbench.html` | The offline Resonance Workbench, replaying the same prerecorded session | [`models/workbench_assets/resonance/`](../models/workbench_assets/resonance) |
| `/circle/first-light.html` | First Light: real phone-camera recordings, the live camera path, and the optical phantom | [`site/`](../site) |
| `/circle/first-light-phantom.html` | The known-input optical phantom First Light measures | [`site/`](../site) |

The research site and workbench are prerecorded simulation demos, with no local Python backend. First Light additionally offers public real phone-camera recordings and an experimental live camera path, which the authors have not yet physically tested. Every number on the research site is either drawn at load time from the recorded session (`demo-data.js`) or quoted from the README's recorded results; update both together.

## One-time GitHub Pages setting

The repository owner must enable GitHub Pages in the repository settings:

1. Open **Settings → Pages** for `topherchris420/circle`.
2. Under **Build and deployment**, select **GitHub Actions** as the **Source**. Not **Deploy from a branch**: see the 2026-11-16 incident below.
3. Open **Actions → Demo (GitHub Pages)** and choose **Run workflow** (or push to `main`).
4. Verify that both **Build and verify website and offline workbench** and **Publish CIRCLE website** complete successfully. The publish job's last step, **Verify the public site is this build**, fetches the live site and fails unless it is this commit's build.

You can tell the setting is right when pushes to `main` no longer start a **pages build and deployment** run in the Actions tab, and the publish job no longer shows a *GitHub Pages source* warning.

## Incident, 2026-11-16: the README replaced the site

From commit `fdcfd04` the public URL served GitHub's default Jekyll rendering of `README.md` (title *CIRCLE | circle*), and `workbench.html`, `first-light.html`, and every stylesheet, script, and image returned 404 or 503. Every workflow was green.

**Cause.** The Pages source was still **Deploy from a branch** (`main`, root). Each push to `main` therefore started two deployments: this repository's **Demo (GitHub Pages)** and GitHub's automatic **pages build and deployment**, which runs Jekyll over the repository root. The public URL serves whichever finishes last. For `fdcfd04` the CIRCLE deployment finished at 18:30:10 UTC and the Jekyll one at 18:30:19, and the live `last-modified` header was 18:30:15. Earlier pushes had happened to finish in the other order, which is why the site looked healthy until then.

**Fix.** Set the source to **GitHub Actions** (above) and re-run **Demo (GitHub Pages)**. That removes the second deployment. Independently of the setting, the workflow now:

- waits for any branch-mode Pages build of the same commit to finish, so the CIRCLE deployment always goes last, and warns while the source is wrong;
- writes `circle-deploy.json` (the commit and run) into the site, checks the built site under `/circle/` before upload, and checks the **live** site after deploying, failing unless it serves this commit's build;
- is backed by **Website health** (`.github/workflows/site-health.yml`), which checks the public site every six hours and on demand.

## Checking the live site

```sh
python tools/check_live_site.py
python tools/check_live_site.py https://topherchris420.github.io/circle/ --expect-commit "$(git rev-parse origin/main)"
```

It fetches every page (`/`, `workbench.html`, `first-light.html`, `first-light-phantom.html`) and every script, stylesheet, image, and frame they load, and reports anything that is not a non-empty 200, anything loaded from another origin, and any page that is not the CIRCLE build (for example the Jekyll README). It uses only the standard library. Exit status 0 means healthy.

The workflow intentionally uses `actions/upload-pages-artifact` and `actions/deploy-pages`. A GitHub Actions job that only pushes `gh-pages` using `GITHUB_TOKEN` does **not** trigger a branch-based Pages build. Keeping an orphan `gh-pages` branch is unnecessary for this workflow.

## How it works

`.github/workflows/demo.yml` builds the static site using:

```sh
python tools/build_demo.py --output demo
```

It copies `site/` to the root, writes the workbench to `workbench.html`, checks every entrypoint and its required assets, stamps the build with its commit, serves it locally under `/circle/` and checks it with `tools/check_live_site.py`, uploads `demo/` as a Pages artifact, waits out any branch-mode Pages build, deploys it to the `github-pages` environment, and finally checks the live site.

Changes pushed to `main` rebuild the public demo; `workflow_dispatch` provides an explicit manual retry. GitHub Pages may need several minutes to make a successful deployment visible.

## Troubleshooting

- **The site shows the README (title *CIRCLE | circle*) and other pages are 404:** the Pages source is **Deploy from a branch** and GitHub's Jekyll build won the race. See the incident above. Set the source to **GitHub Actions**, then re-run **Demo (GitHub Pages)**.
- **Verify the public site is this build fails:** read its list of problems. A commit mismatch in `circle-deploy.json` means another deployment replaced this one or the CDN had not caught up within ten minutes. Re-run the workflow once, then check **Settings → Pages**.
- **404 but demo workflow is green:** Check **Settings → Pages**. The source must be **GitHub Actions**, not `gh-pages` or `main /docs`. Confirm the **Publish CIRCLE website** job actually ran and succeeded, not just a branch push.
- **Configure GitHub Pages fails:** Enable the site in **Settings → Pages**. The default `GITHUB_TOKEN` cannot enable Pages automatically when it is not already configured.
- **Deploy step fails:** Check the deployment job for missing Pages permissions, repository/environment restrictions, or an unconfigured site.
- **Page loads but assets fail:** Inspect the build's asset verification. The static files must be referenced relative to `/circle/`, not with root-absolute `/resonance` paths.

The offline demo is intentionally distinct from the local research workbench. To run experiments and generate new reports, follow the [README](../README.md) and run `python tools/run_workbench.py` locally.
