# Chronodux Documentation Website

Static documentation site for Chronodux 0.1.0.

## Preview locally

From the repository root:

```bash
python -m http.server 8000 --directory docs
```

Open http://localhost:8000.

## Publish with GitHub Pages

1. Open repository **Settings → Pages**.
2. Select **Deploy from a branch**.
3. Select branch `main` and folder `/docs`.
4. Save and wait for deployment.

Expected project-site URL: https://cyberdeep-corp.github.io/Chronodux/

## Files

- `index.html` — documentation content and examples.
- `assets/style.css` — responsive styling.
- `assets/docs.js` — mobile navigation, active section, and code-copy controls.

Keep documentation aligned with the package implementation when the public API changes.
