# The In-Between

Math-driven curve and joint behaviour between your existing controls — portable recipes with live demos and a Maya companion tool.

## Maya companion tool (2026)

Unified PySide6 UI for all six behaviours — multiple rigs per scene and exportable joint chains.

**Quick install:** drag `tools/maya/install_shelf.py` or `tools/maya/install_in_between.mel` into the Maya viewport. That adds an **In-Between** button to your current shelf (no path setup required).

**Manual run:**

1. Add `tools/maya` to your Maya script path, or run `tools/maya/run_in_between.py` from the Script Editor.
2. `import run_in_between; run_in_between.show()`
3. Pick behaviour, start/end transforms, optional parent groups, build.

## Local preview

This site loads card HTML via `fetch()`, so use a local server (not `file://`):

- **VS Code:** Live Server on `index.html`
- **Python:** `python -m http.server 8080` then open `http://localhost:8080`

## Publish on GitHub Pages (free, public repo)

1. Create a new **public** repository on GitHub named `the-in-between` (or any name).
2. Push this folder to it (see below).
3. On GitHub: **Settings → Pages**
4. **Build and deployment → Source:** Deploy from a branch
5. **Branch:** `main` (or `master`), folder **`/ (root)`**
6. Save. After 1–2 minutes your site is live at:

   `https://<your-username>.github.io/the-in-between/`

## Push from VS Code

1. **File → Open Folder** → this `the-in-between` folder
2. Source Control → **Initialize Repository**
3. Stage all → commit: `Initial commit: The In-Between site`
4. **Publish Branch** → create repo on GitHub (choose **Public**)
5. Enable Pages (steps above)

## Push from GitHub Desktop

1. **File → Add local repository** → select this folder
2. If prompted, create a repository here
3. Commit with message `Initial commit: The In-Between site`
4. **Publish repository** → Public
5. Enable Pages on github.com (steps above)

## Updating the site

Edit files here (or copy updates from `ab-maya-scripts/sites`), commit, and push. Pages redeploys automatically.
