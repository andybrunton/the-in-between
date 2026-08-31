# The In-Between

Math-driven curve and joint behaviour between your existing controls — portable recipes with live demos and optional Maya wiring.

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
