# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
{
    "name": "Web Field Provenance",
    "summary": "Track and surface whether a field value came from the user "
    "or from a computed/derived default, SAP-style.",
    "category": "Tools",
    "version": "18.0.1.0.0",
    "author": "Ledoweb, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/web",
    "depends": ["web"],
    "data": [
        "views/ir_model_fields_views.xml",
    ],
    "demo": [
        "demo/web_field_provenance_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_field_provenance/static/src/**/*",
        ],
    },
    "maintainers": ["dkendall"],
    "auto_install": False,
    "installable": True,
}
