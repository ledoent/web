Track and surface whether a field value was set by the user, assigned
by a rule/cascade/integration, or is still at its default — Salesforce/
SAP-style field provenance for Odoo.

Solves the OCA-wide bug class where `compute=..., store=True, readonly=False`
("computed-writable") fields silently overwrite manual user overrides
when an upstream dependency changes and the compute re-fires through
`super()`. Provides:

1. A persistent per-record provenance map (`_provenance`) that records,
   for every opted-in field, **how** it got its current value. Three
   states:
   - **default** — no entry. The field is still at the value it had on
     creation. We never stamp the default state, which keeps the JSON
     column compact.
   - **rule / cascade / EDI** — `{s:"r", b:<writer-id>, t:<unix>, r:<label>}`.
     Set by server-side cascade code via `_stamp_provenance(source="r", …)`.
   - **user** — `{s:"u", b:<login>, t:<unix>}`. Set by a regular user
     write. Stamped automatically by the ORM hook.
2. A reusable `_user_set(fname)` helper that compute methods consult to
   gate `super()` on real user intent rather than chain-residual values.
3. A `_stamp_provenance(keys, source, by, rule=None, when=None)` public
   API for cascade methods, EDI connectors, and import loaders to
   attribute their writes correctly.
4. A `_provenance_for(fname)` helper returning the badge tooltip dict
   (also useful as a golden-output target in tests).
5. An OWL `provenance_m2o` widget that renders a small badge next to
   opted-in fields with three icons:
   - grey outline = default
   - green cog = rule
   - pencil = user
   Hovering shows the writer and timestamp. Clicking promotes the value
   to user-anchored; the server sanitizes the client payload so writer
   identity cannot be spoofed.

This module is plumbing. To surface the badge on a specific field, set
`track_provenance=True` on its `ir.model.fields` record (see USAGE) and
replace the view tag with `widget="provenance_m2o"`.
