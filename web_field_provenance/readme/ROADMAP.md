- [ ] **Opt-in wizard for base fields.** Odoo blocks `ir.model.fields.write()`
  on `state='base'` fields, so `track_provenance` can't be toggled from the
  generic technical view today. Ship a small wizard
  (Settings → Technical → Field Provenance Setup) that picks
  (model, field) tuples and applies the flag via a SQL UPDATE +
  `registry.clear_cache()`. Tests already use this bypass.
- [ ] **provenance_selection** and **provenance_char** widget variants
  (current MVP only ships `provenance_m2o`).
- [ ] Pre-commit cascade banner: intercept the onchange RPC result in
  the OWL form controller and surface "Field X is about to change from
  A → B because Y changed" before commit. ProseMirror `filterTransaction`
  is the conceptual reference.
- [ ] Draft-time cascade log panel (chatter-adjacent) listing every
  field cascade with timestamp, prior value, new value, cause field.
- [ ] Undo toast (Linear-style) — let the cascade happen, then offer
  a 6-second window to revert just the overwritten field.
- [ ] Demo addon `web_field_provenance_sale` that wires `sale.order` +
  `account.move` fields touched by `sale_order_type` to the widget and
  applies the `_user_set` guard in the seven mirror computes.
- [ ] Upstream RFC to Odoo S.A.: expose `_user_set` on the ORM base
  class so this module becomes plumbing-only.
- [ ] **API / EDI integration** (sub-track — separate from the MVP):
  - Documented `_stamp_provenance(..., source='r', by='edi:<connector>')`
    hook for inbound EDI / XML-RPC writers. Connector modules call this
    when applying values on behalf of an upstream system so the badge
    attributes correctly.
  - Conflict policy on re-import: when an inbound EDI rewrites a
    `s=u` field, decide between "preserve user (block)", "override and
    log prior in chatter", or "override and re-stamp as `r=edi:...`".
    Per-integration setting.
  - Provenance serializer `_provenance_to_audit_dict` for outbound
    audit exports (UBL/Peppol BTG-65-equivalent "Originator Document
    Reference" semantics).
  - Bulk-import (`load()`, base_import) stamping with `b='import'` and
    optional batch identifier so audit can trace a row to a specific
    import job.
  - Benchmark JSON-column overhead at 100+ tracked fields per record;
    consider migrating to a `mail.tracking.value`-style external table
    if the inline column starts dominating query costs.
