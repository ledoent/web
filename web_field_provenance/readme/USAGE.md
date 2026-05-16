## 1. Opt-in a field for provenance tracking

In Settings → Technical → Database Structure → Fields, find the field you
want tracked and tick **Track Provenance**. Or programmatically:

```python
self.env["ir.model.fields"]._get("account.move", "invoice_payment_term_id")\
    .write({"track_provenance": True})
```

## 2. Preserve user values inside an override compute

In modules that layer overrides on Odoo core computes (e.g.
`sale_order_type`), guard the recompute on the new helper:

```python
@api.depends("sale_type_id")
def _compute_invoice_payment_term_id(self):
    # Records the user has explicitly touched are excluded from super().
    preserved = self.filtered(
        lambda m: m._user_set("invoice_payment_term_id"),
    )
    super(AccountMove, self - preserved)._compute_invoice_payment_term_id()
    for move in (self - preserved).filtered("sale_type_id.payment_term_id"):
        move.invoice_payment_term_id = move.sale_type_id.payment_term_id
```

## 3. Render the badge in views

Replace the field's view tag:

```xml
<field name="invoice_payment_term_id" widget="provenance_m2o"/>
```

A small icon appears next to the field:

* **Green gear** — the value came from a default or compute. It may
  change if upstream fields change.
* **Pencil** — the user has anchored this value. Recompute cascades
  will respect it.

Clicking the icon promotes the current value to user-anchored.
