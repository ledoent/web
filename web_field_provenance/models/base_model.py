# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""Provenance machinery for computed-writable fields.

Two ideas implemented here:

1.  Per-field "did the user set this?" probe — `_user_set(fname)` — based on
    `record._origin`. Cheap, no schema cost, available to every model.

2.  Per-field provenance map — a transient JSON column `_provenance` that
    records which fields were last written by a user vs. assigned by a
    compute. Only populated for fields whose `ir.model.fields.track_provenance`
    flag is set. The web client reads this map and renders a small badge
    next to opted-in fields (system gear vs. user pencil), Salesforce/SAP
    style.

The two paths cooperate: in compute methods, callers can guard with
`if self._user_set('payment_term_id'): return` to preserve manual values
during recompute cascades. The provenance map then lights up the badge so
the user sees the system gave way to their choice.
"""

from odoo import api, fields, models

# Marker key for provenance values. Kept short to keep the JSON column
# compact when many fields opt in.
_USER = "u"
_SYSTEM = "s"


class Base(models.AbstractModel):
    _inherit = "base"

    _provenance = fields.Json(
        string="Field Provenance",
        help="Per-field provenance map: {field_name: 'u'|'s'}. "
        "'u' = user-supplied, 's' = system-assigned (compute/default).",
        copy=False,
    )

    # ------------------------------------------------------------------
    # Helper API consumed by computes / wizards / tests
    # ------------------------------------------------------------------
    def _user_set(self, fname):
        """Return True if `fname` was set by the user, not by a compute.

        Resolution order:
          1. If a provenance map exists and records 'u' for this field,
             trust it (explicit, persisted).
          2. Else fall back to `_origin` comparison: if the current value
             differs from the DB-saved value AND is non-falsy, treat as
             user-touched (transactional dirty bit).
          3. Otherwise False.

        The compute-cascade-preserve pattern looks like:

            @api.depends("sale_type_id")
            def _compute_invoice_payment_term_id(self):
                preserved = self.filtered(
                    lambda m: m._user_set("invoice_payment_term_id"),
                )
                super(AccountMove, self - preserved)._compute_invoice_payment_term_id()
        """
        self.ensure_one()
        prov = self._provenance or {}
        if prov.get(fname) == _USER:
            return True
        origin = self._origin
        if origin and origin[fname] and self[fname] != origin[fname]:
            return True
        return False

    # ------------------------------------------------------------------
    # ORM hooks — stamp provenance on writes
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._stamp_provenance_from_vals(vals_list, source=_USER)
        return records

    def write(self, vals):
        # Snapshot incoming user-driven field names BEFORE write so we
        # can distinguish them from cascade-recompute writes performed
        # inside super().write() via the ORM's compute pass.
        user_keys = [k for k in vals if self._field_tracks_provenance(k)]
        res = super().write(vals)
        if user_keys:
            self._stamp_provenance_keys(user_keys, source=_USER)
        return res

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _field_tracks_provenance(self, fname):
        """Cheap cache: is this field opted in via ir.model.fields.track_provenance?"""
        if fname.startswith("_") or fname not in self._fields:
            return False
        # Lookup is bound to the registry — avoid round-trip on every write.
        return bool(
            self.env["ir.model.fields"]._get(self._name, fname).track_provenance
        )

    def _stamp_provenance_from_vals(self, vals_list, source):
        for rec, vals in zip(self, vals_list, strict=False):
            keys = [k for k in (vals or {}) if rec._field_tracks_provenance(k)]
            if keys:
                rec._stamp_provenance_keys(keys, source=source)

    def _stamp_provenance_keys(self, keys, source):
        for rec in self:
            current = dict(rec._provenance or {})
            for k in keys:
                current[k] = source
            # Bypass the public write() to avoid infinite recursion.
            rec.sudo().with_context(prevent_provenance_stamp=True)._write(
                {
                    "_provenance": current,
                }
            )

    # ------------------------------------------------------------------
    # Expose provenance to the web client via read()
    # ------------------------------------------------------------------
    def read(self, fields=None, load="_classic_read"):
        """Inject `_provenance` into reads if the client asked for any
        tracked field. The OWL widget consumes this map to render a badge.
        """
        result = super().read(fields=fields, load=load)
        if not result:
            return result
        wants_provenance = fields is None or any(
            f != "_provenance" and self._field_tracks_provenance(f) for f in fields
        )
        if not wants_provenance:
            return result
        # Re-fetch _provenance for every read row we didn't already include.
        if fields is not None and "_provenance" not in fields:
            ids = [r["id"] for r in result]
            extra = {
                r["id"]: r["_provenance"]
                for r in super().read(
                    fields=["_provenance"],
                    load=load,
                )
                if r["id"] in ids
            }
            for row in result:
                row["_provenance"] = extra.get(row["id"]) or {}
        return result
