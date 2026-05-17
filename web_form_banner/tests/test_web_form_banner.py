# Copyright 2025 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFieldsViewGetPartnerBanner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Rule = cls.env["web.form.banner.rule"]
        cls.rule_name = cls.env.ref("web_form_banner.demo_rule_partner_name_length")
        cls.rule_email = cls.env.ref("web_form_banner.demo_rule_partner_email_missing")
        cls.rule_tag = cls.env.ref("web_form_banner.demo_rule_partner_tag_missing")
        cls.rule_client_side = cls.env.ref(
            "web_form_banner.demo_rule_partner_client_side"
        )
        # Disable all but the partner-name-length demo rule so the sibling-
        # position assertion in test_position_relative_to_sheet remains
        # exact (any other active rule on res.partner would inject a second
        # banner before <sheet> and shift the indexes).
        cls.rule_email.active = False
        cls.rule_tag.active = False
        cls.rule_client_side.active = False
        cls.partner_form_view = cls.env.ref("base.view_partner_form")
        cls.p_len3 = cls.Partner.create({"name": "Bob"})  # 3
        cls.p_len12 = cls.Partner.create({"name": "Yoshi Tashiro"})  # 12
        cls.p_len22 = cls.Partner.create({"name": "Professor Charles Xavier"})  # 22

    def _get_arch_tree(self, model, view):
        res = model.get_view(view_id=view.id, view_type="form")
        return etree.fromstring(res["arch"])

    def _find_banner_node(self, tree, rule):
        """Find the injected placeholder node for the rule."""
        xpath = f"//div[@data-rule-id='{rule.id}' and contains(@class,'o_form_banner')]"
        nodes = tree.xpath(xpath)
        self.assertTrue(nodes, "Expected banner node injected in the form arch.")
        return nodes[0]

    def _get_sibling_indexes(self):
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        banner_node = self._find_banner_node(tree, self.rule_name)
        targets = tree.xpath(self.rule_name.target_xpath)
        self.assertTrue(targets)
        target = targets[0]
        parent = target.getparent()
        self.assertIsNotNone(parent)
        # Banner and sheet should share the same parent
        self.assertIs(parent, banner_node.getparent())
        siblings = list(parent)
        return siblings.index(target), siblings.index(banner_node)

    def _code(self, rule):
        return (rule.message_value_code or "").strip()

    def test_injected_once_with_expected_attrs(self):
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        banner_node = self._find_banner_node(tree, self.rule_name)
        # Basic attributes from the server injection
        self.assertEqual(banner_node.get("data-model"), "res.partner")
        self.assertEqual(banner_node.get("role"), "status")
        # Class list includes the expected CSS classes
        classes = (banner_node.get("class") or "").split()
        for required in ("o_form_banner", "alert", "o_invisible_modifier"):
            self.assertIn(required, classes)
        # Ensure it's not duplicated
        all_banners = tree.xpath("//div[contains(@class,'o_form_banner')]")
        self.assertEqual(len(all_banners), 1)

    def test_position_relative_to_sheet(self):
        self.rule_name.position = "before"
        i_target, i_banner_node = self._get_sibling_indexes()
        self.assertEqual(
            i_banner_node,
            i_target - 1,
            "Banner should be inserted immediately before <sheet>",
        )
        self.rule_name.position = "after"
        i_target, i_banner_node = self._get_sibling_indexes()
        self.assertEqual(
            i_banner_node,
            i_target + 1,
            "Banner should be inserted immediately after <sheet>",
        )

    def test_not_injected_on_unrelated_model(self):
        Company = self.env["res.company"]
        view = self.env.ref("base.view_company_form")
        res = Company.get_view(view_id=view.id, view_type="form")
        tree = etree.fromstring(res["arch"])
        self.assertFalse(tree.xpath("//div[contains(@class,'o_form_banner')]"))

    def test_contains_expected_messages_and_severities(self):
        code = (self.rule_name.message_value_code or "").strip()
        self.assertIn("This partner's name is very long!", code)
        self.assertIn("This partner's name is a bit long.", code)
        self.assertRegex(code, r"['\"]danger['\"]", "Missing 'danger' literal")
        self.assertRegex(code, r"['\"]warning['\"]", "Missing 'warning' literal")

    def test_banner_visibility_and_content(self):
        # Short name: no banner
        out = self.Rule.compute_message(
            self.rule_name.id, "res.partner", self.p_len3.id
        )
        self.assertFalse(out.get("visible"))
        # Medium name: warning banner
        out = self.Rule.compute_message(
            self.rule_name.id, "res.partner", self.p_len12.id
        )
        self.assertTrue(out.get("visible"))
        self.assertEqual(out.get("severity"), "warning")
        self.assertIn("bit long", out.get("html", ""))
        # Long name: danger banner
        out = self.Rule.compute_message(
            self.rule_name.id, "res.partner", self.p_len22.id
        )
        self.assertTrue(out.get("visible"))
        self.assertEqual(out.get("severity"), "danger")
        self.assertIn("very long", out.get("html", ""))

    def test_inactive_rule_returns_hidden(self):
        # Flip active off just for this check
        self.rule_name.active = False
        try:
            out = self.Rule.compute_message(
                self.rule_name.id, "res.partner", self.p_len22.id
            )
            self.assertFalse(out.get("visible"))
        finally:
            self.rule_name.active = True

    def test_compute_message_dynamic_simple_field(self):
        self.rule_email.active = True
        out = self.Rule.compute_message(
            self.rule_email.id, "res.partner", self.p_len3.id, form_vals={"email": ""}
        )
        self.assertTrue(out.get("visible"))
        self.assertIn("This partner is missing email!", out.get("html"))
        out = self.Rule.compute_message(
            self.rule_email.id,
            "res.partner",
            self.p_len3.id,
            form_vals={"email": "test@example.com"},
        )
        self.assertFalse(out.get("visible"))

    def test_compute_message_dynamic_m2m(self):
        self.rule_tag.active = True
        tag = self.env["res.partner.category"].create({"name": "test tag"})
        out = self.Rule.compute_message(
            self.rule_tag.id,
            "res.partner",
            self.p_len3.id,
            form_vals={"category_id": []},
        )
        self.assertTrue(out.get("visible"))
        self.assertIn("Tag is missing!", out.get("html"))
        out = self.Rule.compute_message(
            self.rule_tag.id,
            "res.partner",
            self.p_len3.id,
            form_vals={"category_id": [tag.id]},
        )
        self.assertFalse(out.get("visible"))

    # ------------------------------------------------------------------
    # Client-side mode (18.0.1.2.0+)
    # ------------------------------------------------------------------
    def _make_client_rule(self, **overrides):
        defaults = {
            "name": "Client-side test",
            "model_id": self.env.ref("base.model_res_partner").id,
            "target_xpath": "//sheet",
            "position": "before",
            "severity": "warning",
            "client_side": True,
            "client_condition": "customer_rank > 0 and not email",
            "message_is_html": True,
            "message": "Customer <strong>${name}</strong> needs an email.",
        }
        defaults.update(overrides)
        return self.Rule.create(defaults)

    def test_client_side_arch_uses_invisible_attribute(self):
        """Client-side rules emit a self-contained <div invisible='...'/>
        with no o_form_banner placeholder marker class."""
        rule = self._make_client_rule()
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        nodes = tree.xpath(f"//div[@data-rule-id='{rule.id}']")
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        self.assertEqual(node.get("data-client"), "1")
        invisible = node.get("invisible")
        self.assertIsNotNone(invisible)
        self.assertIn("customer_rank", invisible)
        self.assertIn("email", invisible)
        self.assertIn("alert-warning", node.get("class") or "")
        # No placeholder marker class — the JS RPC machinery filters by
        # data-client and would never refresh this div anyway.
        self.assertNotIn("o_form_banner", node.get("class") or "")

    def test_client_side_var_sugar_expands_to_field_tag(self):
        """``${field_name}`` placeholders rewrite to reactive ``<field/>``."""
        rule = self._make_client_rule()
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        node = tree.xpath(f"//div[@data-rule-id='{rule.id}']")[0]
        field_tags = node.xpath(".//field[@name='name']")
        self.assertTrue(
            field_tags,
            "Expected ${name} to expand into a reactive <field name='name'/>",
        )

    def test_client_side_text_message_escapes_and_breaks_lines(self):
        """Non-HTML messages are escaped and newlines become ``<br/>``."""
        rule = self._make_client_rule(
            message_is_html=False,
            message="Line one <evil>\nLine two ${name}",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        node = tree.xpath(f"//div[@data-rule-id='{rule.id}']")[0]
        rendered = etree.tostring(node, encoding="unicode")
        self.assertIn("&lt;evil&gt;", rendered)
        self.assertIn("<br/>", rendered)
        self.assertIn('<field name="name"/>', rendered)

    def test_client_side_missing_condition_rejected(self):
        from odoo.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._make_client_rule(client_condition=False)

    def test_client_side_malformed_condition_rejected(self):
        from odoo.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._make_client_rule(
                client_condition="state == 'draft' and (",  # unbalanced paren
            )

    def test_client_side_injects_hidden_field_for_missing_reference(self):
        """A client_condition referencing a field NOT in the form arch
        must trigger an invisible <field/> sibling injection — otherwise
        py.js raises 'Name X not defined' at render time and crashes any
        browser test that opens the form.

        We use 'lang' here because it's on res.partner but is NOT in the
        base partner form view (it's added by various locale modules).
        """
        rule = self._make_client_rule(
            client_condition="lang and not email",
            message_is_html=True,
            message="Contact has lang but no email",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        # The banner div should exist (sanity) and the injection should
        # also have added a hidden <field name="lang"/> sibling somewhere
        # in the arch.
        self.assertTrue(tree.xpath(f"//div[@data-rule-id='{rule.id}']"))
        lang_tags = tree.xpath("//field[@name='lang' and @invisible='True']")
        self.assertTrue(
            lang_tags,
            "Expected an invisible <field name='lang'/> sibling to be "
            "injected so py.js can resolve 'lang' in the banner's "
            "invisible= expression. Without this, the form crashes.",
        )

    def test_client_side_does_not_inject_for_already_declared_field(self):
        """If the form arch already loads a field, don't duplicate it."""
        # 'name' is always on res.partner form view (it's the record's
        # display field). Our message uses ${name} which already creates
        # a <field name="name"/>, and the condition references it too.
        # We should NOT see a duplicate invisible <field name="name"/>.
        self._make_client_rule(
            client_condition="name and not email",
            message_is_html=True,
            message="Contact ${name} has no email",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        invisible_name_tags = tree.xpath("//field[@name='name' and @invisible='True']")
        self.assertFalse(
            invisible_name_tags,
            "Should not inject an invisible <field name='name'/> when the "
            "form arch already loads name through the title widget or "
            "message ${name} substitution.",
        )

    def test_client_side_skips_pyjs_reserved_names(self):
        """Names like ``True``, ``len``, ``context_today`` are py.js
        builtins, not fields. They must never become injected ``<field/>``
        tags (which would crash with 'no field named X')."""
        self._make_client_rule(
            client_condition="not email and bool(name) and True",
            message_is_html=True,
            message="${name} has no email",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        self.assertFalse(
            tree.xpath("//field[@name='True']"),
            "py.js reserved name 'True' must not become a <field name='True'/>",
        )
        self.assertFalse(
            tree.xpath("//field[@name='bool']"),
            "py.js builtin 'bool' must not become a <field name='bool'/>",
        )

    def test_client_side_handles_quoted_string_literals(self):
        """Single quotes inside the condition (e.g. comparing against a
        string literal) must survive XML attribute serialization. An
        earlier f-string-based arch builder broke on
        ``state == 'draft'`` because the inner quote terminated the
        ``invisible='...'`` attribute mid-expression."""
        # Use a state-style comparison. Even though res.partner doesn't
        # have a `state` field by default, the assertion is that the
        # arch SERIALIZES correctly — auto-injection still skips `state`
        # because it isn't on the model.
        rule = self._make_client_rule(
            client_condition="name and lang == 'en_US'",
            message_is_html=True,
            message="${name} has lang en_US",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        banner = tree.xpath(f"//div[@data-rule-id='{rule.id}']")[0]
        invisible = banner.get("invisible") or ""
        self.assertIn(
            "'en_US'",
            invisible,
            "The single-quoted string literal must round-trip through "
            "the arch — got: " + invisible,
        )
        # And the arch must still be parseable as XML when serialized,
        # which is implicit by the time we got `banner` back.

    def test_client_side_position_after(self):
        """Banner with position='after' lands as a sibling AFTER the
        target xpath node, not before."""
        rule = self._make_client_rule(position="after")
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        banner = tree.xpath(f"//div[@data-rule-id='{rule.id}']")[0]
        sheet = tree.xpath("//sheet")[0]
        parent = sheet.getparent()
        idx_sheet = list(parent).index(sheet)
        idx_banner = list(parent).index(banner)
        self.assertGreater(
            idx_banner,
            idx_sheet,
            f"Banner at index {idx_banner} should be after sheet at "
            f"index {idx_sheet}",
        )

    def test_client_side_multiple_rules_share_injected_fields(self):
        """Two client-side rules on the same model + same missing-field
        reference must result in exactly ONE hidden <field/> injection,
        not duplicates. The injection tracker preserves invariants for
        subsequent rules in the iteration."""
        # Both rules reference `lang` (not in base partner form view).
        self._make_client_rule(
            name="rule-A",
            client_condition="lang == 'en_US'",
            message="A",
        )
        self._make_client_rule(
            name="rule-B",
            client_condition="lang and not email",
            message="B",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        lang_tags = tree.xpath("//field[@name='lang' and @invisible='True']")
        self.assertEqual(
            len(lang_tags),
            1,
            "Two rules both referencing `lang` should share one hidden "
            "injected field, not duplicate it.",
        )

    def test_client_side_rejects_dotted_var_sugar(self):
        """``${partner_id.email}`` would expand to
        ``<field name="partner_id.email"/>`` which is invalid Odoo form
        arch. The regex must NOT match dotted names — they get left as
        literal text in the message instead of a broken field tag."""
        rule = self._make_client_rule(
            client_condition="email",
            message_is_html=True,
            message="Contact <strong>${partner_id.name}</strong> wants email",
        )
        tree = self._get_arch_tree(self.Partner, self.partner_form_view)
        banner = tree.xpath(f"//div[@data-rule-id='{rule.id}']")[0]
        rendered = etree.tostring(banner, encoding="unicode")
        # The dotted form must NOT have produced a <field/> tag.
        self.assertNotIn(
            'name="partner_id.name"',
            rendered,
            "Dotted ${X.Y} must not generate <field name='X.Y'/> — "
            "doing so emits invalid Odoo form arch.",
        )
        # And the original text should still be visible (literal "${...}")
        self.assertIn("partner_id.name", rendered)
