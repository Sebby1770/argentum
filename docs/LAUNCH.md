# Commercial launch checklist

The code and public site are launch-ready foundations, not proof that external
accounts or legal/commercial setup exist.

## Before merging to `main`

- Review the proposed `AUD 900` setup and `AUD 249/month` support prices.
- Confirm actual availability and written terms before accepting an engagement.
- Read `BRAND-RISK.md` and make an informed naming decision.
- Enable **GitHub Pages → GitHub Actions** in repository settings.
- Confirm the public URL is `https://sebby1770.github.io/argentum/`; update
  canonical, social, sitemap, and robots URLs if a custom domain is chosen.
- GitHub project Pages cannot control the shared origin-level
  `https://sebby1770.github.io/robots.txt`. The project ships
  `/argentum/robots.txt`; use a custom domain rooted at this site if an
  origin-level crawler policy is required.
- Keep `assets/site-config.json` empty to run without analytics. If a Google
  Analytics ID is later added, verify the consent prompt and privacy notice.
- Replace the GitHub avatar only with a real image Sebastian approves and can
  publish; do not label the current abstract avatar as a team photo.
- Preserve and review `SOCIAL_PREVIEW.md` whenever the social/hero asset changes.
- If an earlier Studio run created `data/feed.json`, rotate any credential it
  contained and remove that legacy file after confirming the new per-user
  config works. Version 1.5 no longer reads or writes it.

## First package release

The project currently makes no claim that a GitHub or package-index release
exists. The release dry-run workflow builds and checks artifacts but never
publishes them.

1. Run the complete test matrix and `release-dry-run` workflow.
2. Inspect the wheel and install it into a clean environment; smoke-test Studio.
3. Reserve and configure the PyPI project through PyPI's current trusted-
   publishing flow, using this repository and the final workflow/environment.
4. Create release notes from `CHANGELOG.md` and publish only with the owner's
   explicit approval.
5. After a release is visibly available, update install copy from source-clone
   instructions to the verified package command.

## Honest evidence

- Do not add reviews, customer logos, case studies, credentials, benchmarks, or
  response claims without evidence and permission.
- Keep the positioning explicit: open-source derivatives analytics and a local
  research Studio for education, model exploration, and prototyping.
- Outputs are estimates. Argentum is not a broker, data provider, validated
  risk system, or substitute for independent model validation.
