# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from odoo import fields, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    track_provenance = fields.Boolean(
        help="Surface a badge on the web client showing whether the value "
        "was set by the user or assigned by a computed default. "
        "Only meaningful on computed-writable fields "
        "(compute=..., store=True, readonly=False).",
    )
