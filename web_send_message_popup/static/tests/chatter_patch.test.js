import {asyncStep, mockService, waitForSteps} from "@web/../tests/web_test_helpers";
import {
    click,
    contains,
    defineMailModels,
    openFormView,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import {describe, expect, test} from "@odoo/hoot";

describe.current.tags("desktop");
defineMailModels();

describe("WebSendMessagePopup", () => {
    test("Send message opens the full composer popup, not the inline composer", async () => {
        const pyEnv = await startServer();
        const partnerId = pyEnv["res.partner"].create({name: "Test Partner"});
        mockService("action", {
            doAction(action) {
                asyncStep("full_composer");
                // The module routes the "message" path to the full composer
                // wizard instead of the inline chatter composer.
                expect(action.res_model).toBe("mail.compose.message");
                expect(action.target).toBe("new");
                expect(action.context.default_subtype_xmlid).toBe("mail.mt_comment");
                // Asserting the dispatched action is enough; do not chain to
                // super to avoid loading the wizard form in the unit test.
                return Promise.resolve();
            },
        });
        await start();
        await openFormView("res.partner", partnerId);
        await contains("button", {text: "Send message"});
        // Inline composer is absent before the click...
        await contains(".o-mail-Composer", {count: 0});
        await click("button", {text: "Send message"});
        await waitForSteps(["full_composer"]);
        // ...and stays absent after: the popup replaces it entirely.
        await contains(".o-mail-Composer", {count: 0});
    });
});
