## 1. Opt-in a field for provenance tracking

In Settings → Technical → Database Structure → Fields, find the field
and tick **Track Provenance**. (For fields declared in Python — most
fields you'll want to track — the UI write is blocked by Odoo's
base-field protection; the documented workaround is a small admin
wizard, see ROADMAP.)

Programmatically (e.g. in a `post_init_hook` of a downstream module):

```python
self.env.cr.execute(
    "UPDATE ir_model_fields SET track_provenance = TRUE "
    "WHERE model = %s AND name = %s",
    ("sale.order", "payment_term_id"),
)
self.env.registry.clear_cache()
```

## 2. Preserve user values inside an override compute

In modules that layer overrides on Odoo core computes
(e.g. `sale_order_type`), guard the recompute on the new helper:

```python
@api.depends("type_id")
def _compute_payment_term_id(self):
    # Records the user has explicitly touched are excluded from super().
    preserved = self.filtered(lambda r: r._user_set("payment_term_id"))
    super(SaleOrder, self - preserved)._compute_payment_term_id()
    for order in (self - preserved).filtered("type_id.payment_term_id"):
        order.payment_term_id = order.type_id.payment_term_id
```

## 3. Attribute cascade / rule / EDI writes correctly

When a non-user writer (a compute cascade, an EDI inbound, an import
loader) sets a value, call `_stamp_provenance` so the badge attributes
the value to the correct source instead of the env user:

```python
order._stamp_provenance(
    ["payment_term_id"],
    source="r",
    by="sot.cascade",                 # stable writer identifier
    rule="Sale Order Type cascade",   # optional human-readable label
)
```

The badge will then render the green-cog (rule) icon and the hover
tooltip will read "Set by *Sale Order Type cascade*".

## 4. Render the badge in views

Replace the field's view tag:

```xml
<field name="payment_term_id" widget="provenance_m2o"/>
```

A small icon appears next to the field with three states:

* **Grey outline** — *default*: field is still at its initial value.
  No entry exists in the provenance map; the badge falls back to
  `record.create_date` for the tooltip.
* **Green cog** — *rule / cascade / EDI*: the value was set by
  server-side logic (`_stamp_provenance` called with `source="r"`).
  Tooltip names the writer.
* **Pencil** — *user*: the user has anchored this value. Recompute
  cascades that consult `_user_set` will respect it.

Clicking the icon promotes the current value to user-anchored. The
server sanitizes the click (forces `b = env.user.login`, drops any
client-supplied rule provenance) — there is no path for a malicious
client to spoof the writer identity.

## 5. Inspect provenance programmatically

```python
order._user_set("payment_term_id")        # True/False
order._provenance_for("payment_term_id")  # {state, label, by?, rule?, when}
```

The dict form is what the OWL widget renders; it's also useful for
golden-output tests of cascade flows.
