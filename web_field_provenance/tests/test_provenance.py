# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from odoo.addons.base.tests.common import BaseCommon


class TestProvenance(BaseCommon):
    """Smoke tests for the provenance stamping + _user_set helper.

    Uses res.partner as a probe model because it's universally available.
    We opt-in `comment` to track_provenance and exercise the read/write
    paths. The compute-cascade preserve pattern is covered in a separate
    integration suite once the demo addon ships.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field = cls.env["ir.model.fields"]._get("res.partner", "comment")
        cls.field.write({"track_provenance": True})

    def test_create_stamps_user(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Provenance Test",
                "comment": "manual note",
            }
        )
        self.assertEqual(
            (partner._provenance or {}).get("comment"),
            "u",
            "Field set in create() should be stamped as user-supplied",
        )
        self.assertTrue(partner._user_set("comment"))

    def test_write_stamps_user(self):
        partner = self.env["res.partner"].create({"name": "No Comment"})
        self.assertFalse((partner._provenance or {}).get("comment"))
        partner.write({"comment": "user-typed"})
        self.assertEqual(
            (partner._provenance or {}).get("comment"),
            "u",
            "Subsequent user write() should overwrite provenance to 'u'",
        )

    def test_user_set_falls_back_to_origin(self):
        partner = self.env["res.partner"].create({"name": "X", "comment": "A"})
        new = partner.new(origin=partner)
        new.comment = "B"
        self.assertTrue(
            new._user_set("comment"),
            "Transient edit should be detected via _origin comparison even "
            "without an explicit provenance stamp",
        )

    def test_untracked_field_not_stamped(self):
        partner = self.env["res.partner"].create({"name": "Tracked Only"})
        prov = partner._provenance or {}
        self.assertNotIn(
            "name",
            prov,
            "Fields without track_provenance=True must not bloat the JSON map",
        )
