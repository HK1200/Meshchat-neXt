import { describe, expect, it } from "vitest";
import { createI18n } from "vue-i18n";

describe("translation HTML security", () => {
    it("neutralizes iframe srcdoc before translated HTML is rendered", () => {
        const i18n = createI18n({
            legacy: false,
            locale: "en",
            escapeParameter: true,
            warnHtmlMessage: false,
            messages: { en: { probe: '<iframe srcdoc="<b>untrusted</b>"></iframe>' } },
        });
        const container = document.createElement("div");
        container.innerHTML = i18n.global.t("probe");
        expect(container.querySelector("iframe")).not.toBeNull();
        expect(container.querySelector("iframe").hasAttribute("srcdoc")).toBe(false);
        i18n.dispose();
    });
});
