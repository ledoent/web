# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
"""Provenance machinery for computed-writable fields.

Two ideas implemented here:

1.  Per-field "did the user set this?" probe — `_user_set(fname)` — based on
    `record._origin`. Cheap, no schema cost, available to every model.

2.  Per-field provenance map — a JSON column `_provenance` that records
    which fields were last written by a user vs. assigned by a compute.
    Only populated for fields whose `ir.model.fields.track_provenance`
    flag is set. The web client reads this map and renders a small badge
    next to opted-in fields (system gear vs. user pencil), Salesforce/SAP
    style.

The two paths cooperate: in compute methods, callers can guard with
`if record._user_set('payment_term_id'): continue` to preserve manual
values during recompute cascades. The provenance map then lights up the
badge so the user sees the system gave way to their choice.
"""

from odoo import api, fields, models, tools

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
             user-touched (transactional dirty bit). NewId records expose
             ``_origin`` pointing at the persisted record; regular records
             return ``self`` for ``_origin`` so the comparison naturally
             yields False outside an active transaction.
        """
        self.ensure_one()
        prov = self._provenance or {}
        if prov.get(fname) == _USER:
            return True
        origin = self._origin
        if (
            origin
            and origin is not self
            and self[fname]
            and origin[fname] != self[fname]
        ):
            return True
        return False

    # ------------------------------------------------------------------
    # ORM hooks — stamp provenance on user writes
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if records._field_track_set():
            records._stamp_provenance_from_vals(vals_list, source=_USER)
        return records

    def write(self, vals):
        # Skip the stamping path entirely when called from our own
        # provenance bookkeeping or when no tracked field is in vals.
        if self.env.context.get("_prov_skip"):
            return super().write(vals)
        tracked = self._field_track_set()
        user_keys = [k for k in vals if k in tracked]
        res = super().write(vals)
        if user_keys:
            self._stamp_provenance_keys(user_keys, source=_USER)
        return res

    # ------------------------------------------------------------------
    # Modern web client entry points — surface _provenance alongside
    # tracked fields. Form views in 18.0 call web_read / web_search_read;
    # the legacy read() override is kept for backwards compatibility but
    # is rarely the hot path.
    # ------------------------------------------------------------------
    def web_read(self, specification):
        result = super().web_read(specification)
        if not result or not self._field_track_set():
            return result
        # Only emit the map when the client asked for a tracked field.
        if not any(name in self._field_track_set() for name in specification):
            return result
        prov_by_id = {r.id: (r._provenance or {}) for r in self}
        for row in result:
            row["_provenance"] = prov_by_id.get(row.get("id"), {})
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @api.model
    @tools.ormcache("self._name")
    def _field_track_set(self):
        """Cached set of field names on this model that opt-in via
        `ir.model.fields.track_provenance=True`. Invalidated when an
        `ir.model.fields` row toggles the flag (see ir_model_fields.py).
        """
        return frozenset(
            self.env["ir.model.fields"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("track_provenance", "=", True),
                ]
            )
            .mapped("name")
        )

    def _stamp_provenance_from_vals(self, vals_list, source):
        tracked = self._field_track_set()
        for rec, vals in zip(self, vals_list, strict=False):
            keys = [k for k in (vals or {}) if k in tracked]
            if keys:
                rec._stamp_provenance_keys(keys, source=source)

    def _stamp_provenance_keys(self, keys, source):
        for rec in self:
            current = dict(rec._provenance or {})
            for k in keys:
                current[k] = source
            rec.with_context(_prov_skip=True).write({"_provenance": current})
