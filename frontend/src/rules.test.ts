import { describe, expect, it } from "vitest";

import { describeCondition } from "./rules";

describe("describeCondition", () => {
  it("regulile din seed", () => {
    const eq = (field: string, value: unknown) => ({ all: [{ field, op: "eq", value }] });
    expect(describeCondition(eq("is_vat_payer", true))).toBe("plătitor de TVA");
    expect(describeCondition(eq("has_employees", false))).toBe("nu are angajați");
    expect(describeCondition({})).toBe("toți clienții");
  });

  it("grupuri imbricate și operatori", () => {
    expect(
      describeCondition({
        all: [
          { field: "is_vat_payer", op: "eq", value: true },
          {
            any: [
              { field: "legal_form", op: "in", value: ["SRL", "II"] },
              { field: "tax_regime", op: "is_null", value: true },
            ],
          },
        ],
      }),
    ).toBe(
      "plătitor de TVA și (forma juridică este una din SRL, ÎI sau regimul fiscal necompletat)",
    );
    expect(describeCondition({ all: [{ field: "has_transport", op: "ne", value: true }] })).toBe(
      "nu are transport",
    );
    expect(describeCondition({ any: [] })).toBe("niciun client");
  });
});
