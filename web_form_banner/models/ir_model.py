# Copyright 2025 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import ast
import logging

from lxml import etree

from odoo import api, models

_logger = logging.getLogger(__name__)


# Reserved names py.js exposes (or that look like names but aren't fields).
# Anything matching this set is NOT promoted to an injected hidden <field>.
_PYJS_RESERVED = frozenset(
    {
        "True",
        "False",
        "None",
        "uid",
        "context",
        "context_today",
        "today",
        "len",
        "bool",
        "min",
        "max",
        "set",
        "list",
        "dict",
        "str",
        "int",
        "float",
        "abs",
        "round",
        "sum",
        "any",
        "all",
        "datetime",
        "time",
        "relativedelta",
    }
)


class _FieldNameCollector(ast.NodeVisitor):
    """Collect identifier roots from a py.js-compatible expression.

    For ``state == 'draft' and partner_id.email`` returns
    ``{'state', 'partner_id'}`` — only the leftmost name in a dotted
    chain matters since the ORM auto-loads relational sub-fields.
    """

    def __init__(self):
        self.names = set()

    def visit_Name(self, node):
        self.names.add(node.id)
        # Don't generic_visit — Name has no children worth visiting.

    def visit_Attribute(self, node):
        # Walk down to the leftmost Name and add only that root.
        v = node
        while isinstance(v, ast.Attribute):
            v = v.value
        if isinstance(v, ast.Name):
            self.names.add(v.id)
        # Intentionally do not generic_visit — we've already captured
        # what we need; recursing would double-count via visit_Name.


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != "form" or not res.get("arch"):
            return res
        current_view_id = view_id or res.get("id")
        if not current_view_id:
            return res
        rules = (
            self.env["web.form.banner.rule"]
            .sudo()
            .search(
                [
                    ("model_name", "=", self._name),
                    "|",
                    ("view_ids", "in", current_view_id),
                    ("view_ids", "=", False),
                ]
            )
        )
        if not rules:
            return res
        try:
            root = etree.fromstring(res["arch"])
        except Exception:
            return res
        declared_fields = set(root.xpath("//field/@name"))
        for rule in rules:
            targets = root.xpath(rule.target_xpath or "//sheet")
            if not targets:
                continue
            target = targets[0]
            if rule.client_side:
                banner = self._build_client_banner(rule)
                if banner is None:
                    continue
                extra_fields = self._client_rule_missing_fields(rule, declared_fields)
            else:
                banner = self._build_server_banner(rule)
                extra_fields = []
            in_group = any(a.tag == "group" for a in target.iterancestors())
            if in_group:
                # Avoid layout distortion when the target sits inside a group.
                banner.set("colspan", "2")
                for f in extra_fields:
                    f.set("colspan", "2")
            # Inject any missing field declarations as hidden siblings so
            # py.js can resolve the names in our `invisible=` expression
            # even on form views that don't already render them.
            if rule.position == "before":
                for f in extra_fields:
                    target.addprevious(f)
                target.addprevious(banner)
            else:
                target.addnext(banner)
                for f in extra_fields:
                    target.addnext(f)
            # Track newly-declared fields so later rules sharing the same
            # name don't double-inject.
            for f in extra_fields:
                declared_fields.add(f.get("name"))
        res["arch"] = etree.tostring(root, encoding="unicode")
        return res

    def _client_rule_missing_fields(self, rule, declared_fields):
        """Return a list of hidden ``<field invisible="True"/>`` elements
        for any field referenced in ``rule.client_condition`` that isn't
        already declared in the form arch.

        Without this, a rule like ``customer_rank > 0 and not email`` on
        a partner form that doesn't render ``customer_rank`` would raise
        ``EvalError: Name 'customer_rank' is not defined`` at runtime and
        bork every browser test that opens the form.
        """
        condition = (rule.client_condition or "").strip()
        if not condition:
            return []
        try:
            tree = ast.parse(condition, mode="eval")
        except SyntaxError:
            # The save-time _check_client_condition constraint already
            # rejects malformed expressions; reaching here means the rule
            # was somehow saved with a bad expression. Don't crash the
            # whole view load — let _build_client_banner's try/except
            # handle it.
            return []
        visitor = _FieldNameCollector()
        visitor.visit(tree)
        model_fields = self.env[self._name]._fields
        needed = []
        for name in sorted(visitor.names):
            if name in _PYJS_RESERVED:
                continue
            if name not in model_fields:
                continue
            if name in declared_fields:
                continue
            needed.append(name)
        return [
            etree.Element("field", {"name": n, "invisible": "True"}) for n in needed
        ]

    def _build_server_banner(self, rule):
        """Heavy-path placeholder div — populated by an ORM RPC on every
        trigger-field change (see static/src/js/web_form_banner.esm.js)."""
        trigger_fields = ",".join(rule.trigger_field_ids.mapped("name"))
        return etree.Element(
            "div",
            {
                "class": "o_form_banner alert o_invisible_modifier",
                "role": "status",
                "data-rule-id": str(rule.id),
                "data-model": self._name,
                "data-trigger-fields": trigger_fields,
            },
        )

    def _build_client_banner(self, rule):
        """Fast-path self-contained alert div. Visibility is evaluated by
        Odoo's view compiler against the in-memory record (py.js); field
        interpolation is reactive via inline <field> tags. Zero RPC.

        Returns None if the message HTML cannot be parsed. The caller
        skips the rule in that case.
        """
        severity = rule.severity or "danger"
        condition = (rule.client_condition or "").strip() or "True"
        # Build the banner element via the etree API so lxml handles
        # attribute escaping. Naive f-string XML-building used to break on
        # `state == 'draft' and amount_total > 1000` because the single
        # quote terminated the `invisible='...'` attribute mid-expression.
        banner = etree.Element(
            "div",
            attrib={
                "class": f"alert alert-{severity}",
                "invisible": f"not ({condition})",
                "role": "status",
                "data-rule-id": str(rule.id),
                "data-model": self._name,
                "data-client": "1",
            },
        )
        # Parse the message body separately and attach as children. The
        # body is wrapped in a throw-away root because lxml needs a single
        # top-level element to parse mixed content.
        inner_html = rule._to_client_arch()
        try:
            body = etree.fromstring(f"<root>{inner_html}</root>")
        except etree.XMLSyntaxError:
            _logger.exception(
                "web_form_banner: failed to parse client-side rule '%s' "
                "message HTML; skipping. Make sure the message is valid "
                "XML (use <br/> not <br>, close every tag).",
                rule.display_name,
            )
            return None
        # `text` is the leading text node, children become banner's
        # children. lxml does the heavy lifting of attribute escaping.
        if body.text:
            banner.text = body.text
        for child in body:
            banner.append(child)
        return banner
