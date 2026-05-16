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
