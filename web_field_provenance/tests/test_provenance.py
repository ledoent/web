# Copyright 2026 Ledoweb (Dan Kendall)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from odoo.addons.base.tests.common import BaseCommon


class TestProvenance(BaseCommon):
    """Smoke tests for the provenance stamping + _user_set helper.

    Uses res.partner as a probe model because it's universally available.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field_comment = cls.env["ir.model.fields"]._get("res.partner", "comment")
        cls.field_comment.write({"track_provenance": True})

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

    def test_user_set_via_explicit_stamp(self):
        """When the provenance map records 'u', _user_set must return True
        regardless of the _origin comparison."""
        partner = self.env["res.partner"].create({"name": "Anchored"})
        partner._stamp_provenance_keys(["comment"], source="u")
        self.assertTrue(partner._user_set("comment"))

    def test_untracked_field_not_stamped(self):
        partner = self.env["res.partner"].create({"name": "Tracked Only"})
        prov = partner._provenance or {}
        self.assertNotIn(
            "name",
            prov,
            "Fields without track_provenance=True must not bloat the JSON map",
        )

    def test_cache_invalidated_on_flag_toggle(self):
        # The "comment" field is tracked from setUpClass; remove the flag
        # and confirm new writes no longer stamp.
        self.field_comment.write({"track_provenance": False})
        partner = self.env["res.partner"].create(
            {
                "name": "Post-Toggle",
                "comment": "no longer tracked",
            }
        )
        self.assertNotIn(
            "comment",
            (partner._provenance or {}),
            "After toggling track_provenance off, comment should not be stamped",
        )
        # Restore for any subsequent tests
        self.field_comment.write({"track_provenance": True})

    def test_web_read_emits_provenance(self):
        partner = self.env["res.partner"].create(
            {
                "name": "WebRead Probe",
                "comment": "anchored",
            }
        )
        rows = partner.web_read({"comment": {}, "name": {}})
        self.assertEqual(len(rows), 1)
        self.assertIn("_provenance", rows[0])
        self.assertEqual(rows[0]["_provenance"].get("comment"), "u")
