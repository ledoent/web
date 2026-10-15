## Banner presentation inside \<group\>

Placing a full-width inline banner inside a \<group\> is only partially
supported. Depending on the target XPath (especially when targeting a
\<field/\> rendered by certain widgets), the banner or surrounding
fields may render distorted.

## Limitations of draft eval context variable

- draft is always available in the eval context, but for new records
  (record_id = False) it only contains the trigger fields from the
  banner rules.
- For existing records, draft overlays the trigger field values on top
  of the persisted record; all other fields come from Model.new defaults
  rather than the database.
- Only simple field types are included: char, text, html, selection,
  boolean, integer, float, monetary, date, datetime, many2one, and
  many2many. **one2many/reference/other types are omitted.**

## Client-side mode follow-ups

- **Dynamic severity per record.** Today the severity (info/warning/
  danger) is baked into the alert's CSS class at view-load time so admins
  can't return `{"severity": "danger" if amount > 100000 else "warning"}`
  the way `message_value_code` can in server-side mode. One option: an
  OWL widget that reads a hidden `severity_expr` from the arch and
  toggles the alert class reactively.
- **Dotted-name interpolation.** `${partner_id.email}` is currently
  rejected because `<field name="partner_id.email"/>` isn't valid form
  arch. A small OWL inline-renderer that reads `record.data.partner_id`
  reactively and substitutes the related value would fix this without
  requiring a stored related field on the model.
- **Rule builder UI.** A small wizard that lets admins compose
  `client_condition` from a "field — operator — value" picker and
  compiles to a py.js-valid string. Avoids the "you have to know the
  grammar" hurdle for non-developer admins.
- **Live syntax validator.** Server-side `ast.parse` catches typos but
  not semantic mismatches (e.g. referencing a field not in the view).
  An OWL editor with `evaluateBooleanExpr` dry-run would surface those
  immediately in the rule form.
- **Auto-detection of py.js compatibility.** If `message_value_code`
  is a single boolean expression with no method calls, suggest
  promoting it to client-side mode on save.
