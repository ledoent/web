# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from odoo import api, fields, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    track_provenance = fields.Boolean(
        help="Surface a badge on the web client showing whether the value "
        "was set by the user or assigned by a computed default. "
        "Only meaningful on computed-writable fields "
        "(compute=..., store=True, readonly=False).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(v.get("track_provenance") for v in vals_list):
            self._invalidate_track_cache(records.mapped("model"))
        return records

    def write(self, vals):
        res = super().write(vals)
        if "track_provenance" in vals:
            self._invalidate_track_cache(self.mapped("model"))
        return res

    def unlink(self):
        models_affected = self.filtered("track_provenance").mapped("model")
        res = super().unlink()
        if models_affected:
            self._invalidate_track_cache(models_affected)
        return res

    def _invalidate_track_cache(self, model_names):
        """Drop the cached `_field_track_set`. Toggling `track_provenance` is
        a rare admin action so a full ormcache flush is acceptable; finer-
        grained invalidation isn't worth the API-stability risk against
        Odoo's private cache internals."""
        if model_names:
            self.env.registry.clear_cache()
