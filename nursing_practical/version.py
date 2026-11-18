# ClinOva release version. The frontend's package.json carries the same number:
# both repos are released and tagged together (see RELEASING.md in the
# frontend repo). Change it with `npm run version:set <x.y.z>` from the
# frontend, not by hand, so the two never drift apart.
__version__ = "1.0.0-rc.1"
