# Jose Antonio Charles, Professional Portfolio

Portfolio site for Jose Antonio Charles, M.S. Chemical Engineer specializing in process safety, hazard analysis, and process simulation.

Static HTML/CSS/JS, no build step.

## Structure

- `index.html`: the whole site, one page with these sections:
  1. Hero: elevator pitch, View Projects / Download Resume buttons, LinkedIn and email, key metrics
  2. Project case studies in Challenge / Approach / Result form, with a category filter
  3. Skills matrix, each row tied to where it was applied
  4. Experience timeline
  5. About, education, and engineering philosophy
  6. Contact form and direct links
- `css/style.css`: styles (responsive, print styles included)
- `js/script.js`: mobile nav, active-section highlight, project filter, contact form
- `assets/docs/Jose_Antonio_Charles_Resume.pdf`: resume download, exported from the master resume in
  `OneDrive/Personal Projects/Engineering_Mass_Apply/Resume_Cover Letter_CV/Jose Charles Resume.docx`
- `assets/img/`: project figures (APEX closed-loop plot comes from `Personal Projects/Process Simulation Software/examples/plots/`)
- `portfolio/index.html`: redirect from the old portfolio sub-page to `#projects`

## Contact form

GitHub Pages has no backend, so the form opens the visitor's email app with the message filled in.
To receive submissions directly instead, create a free Formspree form and change the form's `action`
to the Formspree URL, then remove the submit handler at the bottom of `js/script.js`.

## Updating content

- New project: copy one `<article class="case">` block in `index.html`. Set `data-cat` to one or more of
  `safety design mfg software` so the filter picks it up.
- New resume: re-export the master resume to PDF and overwrite `assets/docs/Jose_Antonio_Charles_Resume.pdf`.
- Only publish employer work at a non-confidential level; no proprietary drawings, P&IDs, or data.

## Hosting: GitHub Pages at joseantoniocharles.com

- Repo: `github.com/charlesantoniojose-byte/joseantoniocharles.com` (public, branch `main`)
- `CNAME` tells GitHub Pages to serve the site at `joseantoniocharles.com`; `.nojekyll` skips Jekyll processing.
- DNS at the registrar:
  - `A` records for `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
  - `AAAA` records for `@`: `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`
  - `CNAME` record for `www`: `charlesantoniojose-byte.github.io`
- In the repo, Settings > Pages: source `main` / `(root)`, custom domain `joseantoniocharles.com`, then tick
  **Enforce HTTPS** once the certificate is issued.
- To publish changes: commit and `git push`. The site updates in about a minute.
