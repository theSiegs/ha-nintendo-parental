# Upstreaming plan

Each fix in this repository is a separate commit and is meant to become its
own pull request against `home-assistant/core`
(`homeassistant/components/nintendo_parental_controls`). No pull requests or
issues have been opened yet.

To build a core PR from a commit: cherry-pick it onto core `dev`, move the
files back to `homeassistant/components/nintendo_parental_controls` and
`tests/components/nintendo_parental_controls`, switch test imports back to
`homeassistant.components...`, drop the `translations/en.json` change (core
generates it), and update `quality_scale.yaml` and the documentation in
`home-assistant.io` where noted.

## Candidate pull requests
