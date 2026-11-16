# CIRCLE website deployment

The public offline Resonance Workbench is published at:

**https://topherchris420.github.io/circle/**

The site is a prerecorded, simulation-only demonstration. It does not access live sensors or provide the local Python workbench's backend.

## One-time GitHub Pages setting

The repository owner must enable GitHub Pages in the repository settings:

1. Open **Settings → Pages** for `topherchris420/circle`.
2. Under **Build and deployment**, select **GitHub Actions** as the **Source**.
3. Open **Actions → Demo (GitHub Pages)** and choose **Run workflow** (or push to `main`).
4. Verify that both **Build and verify offline workbench** and **Publish CIRCLE website** complete successfully, then open the URL above.

The workflow intentionally uses `actions/upload-pages-artifact` and `actions/deploy-pages`. A GitHub Actions job that only pushes `gh-pages` using `GITHUB_TOKEN` does **not** trigger a branch-based Pages build. Keeping an orphan `gh-pages` branch is unnecessary for this workflow.

## How it works

`.github/workflows/demo.yml` builds the static site using:

```sh
python tools/build_demo.py --output demo
```

It checks the entrypoint and required assets, uploads `demo/` as a Pages artifact, and deploys it to the `github-pages` environment.

Changes pushed to `main` rebuild the public demo; `workflow_dispatch` provides an explicit manual retry. GitHub Pages may need several minutes to make a successful deployment visible.

## Troubleshooting

- **404 but demo workflow is green:** Check **Settings → Pages**. The source must be **GitHub Actions**, not `gh-pages` or `main /docs`. Confirm the **Publish CIRCLE website** job actually ran and succeeded, not just a branch push.
- **Configure GitHub Pages fails:** Enable the site in **Settings → Pages**. The default `GITHUB_TOKEN` cannot enable Pages automatically when it is not already configured.
- **Deploy step fails:** Check the deployment job for missing Pages permissions, repository/environment restrictions, or an unconfigured site.
- **Page loads but assets fail:** Inspect the build's asset verification. The static files must be referenced relative to `/circle/`, not with root-absolute `/resonance` paths.

The offline demo is intentionally distinct from the local research workbench. To run experiments and generate new reports, follow the [README](../README.md) and run `python tools/run_workbench.py` locally.
