# Copyright 2025 Quartile (https://www.quartile.co)
# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Web Form Banner",
    "version": "18.0.1.2.0",
    "category": "Web",
    "author": "Quartile, Ledoweb, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/web",
    "license": "AGPL-3",
    "depends": ["web"],
    "data": [
        "security/ir.model.access.csv",
        "views/web_form_banner_rule_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web_form_banner/static/src/js/*.esm.js",
            "web_form_banner/static/src/scss/*.scss",
        ],
    },
    "demo": ["demo/web_form_banner_rule_demo.xml"],
    "installable": True,
}
