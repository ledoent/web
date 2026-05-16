Track and surface whether a field value was set by the user or assigned
by a computed/derived default — Salesforce/SAP-style field provenance for
Odoo.

Solves the OCA-wide bug class where `compute=..., store=True, readonly=False`
("computed-writable") fields silently overwrite manual user overrides
when an upstream dependency changes and the compute re-fires through
`super()`. Provides:

1. A persistent per-record provenance map (`_provenance`) that records
   which fields were last set by a user vs. assigned by a compute.
2. A reusable `_user_set(fname)` helper for compute methods to gate
   `super()` on real user intent rather than chain-residual values.
3. An OWL `provenance_m2o` widget that renders a small badge next to
   opted-in fields: green gear icon = derived default, pencil = user
   override. Clicking the badge anchors the value as user-supplied.

This module is plumbing. To surface the badge on a specific field, set
`track_provenance=True` on its `ir.model.fields` record and replace the
view tag with `widget="provenance_m2o"`.
