/**
 * Lit template for a HA text-field input, rendering <ha-input> on HA
 * 2026.4+ or <ha-textfield> on older versions.
 *
 * Property differences handled here:
 *   - <ha-textfield helper="..." suffix="s">  (old)
 *   - <ha-input hint="..."> ... <span slot="end">s</span></ha-input>  (new)
 */

import { html } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
import { textfieldTagName } from "./textfield.js";

export function renderTextfield({
  type,
  min,
  max,
  step,
  label = "",
  hint = "",
  suffix = "",
  placeholder = "",
  value,
  onChange,
}) {
  /* v8 ignore start -- ha-input is always registered in happy-dom tests; the ha-textfield
     else-branch (HA <2026.4 fallback) is unreachable in this environment. */
  if (textfieldTagName() === "ha-input") {
    /* v8 ignore stop */
    return html`
      <ha-input
        type=${type}
        min=${min}
        max=${max}
        step=${step}
        label=${label}
        hint=${hint}
        placeholder=${placeholder}
        .value=${value}
        @change=${onChange}
      >
        ${suffix ? html`<span slot="end">${suffix}</span>` : ""}
      </ha-input>
    `;
  }
  /* v8 ignore start -- ha-textfield fallback for HA <2026.4; unreachable in happy-dom tests */
  return html`
    <ha-textfield
      type=${type}
      min=${min}
      max=${max}
      step=${step}
      label=${label}
      helper=${hint}
      suffix=${suffix}
      placeholder=${placeholder}
      .value=${value}
      @change=${onChange}
    ></ha-textfield>
  `;
}
/* v8 ignore stop */
