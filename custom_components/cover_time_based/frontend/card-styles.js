import { css } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

export const cardStyles = css`
      :host {
        display: block;
      }

      .card-header {
        font-size: 24px;
        font-weight: 400;
        padding: 24px 16px 16px;
        line-height: 32px;
        color: var(--ha-card-header-color, var(--primary-text-color));
      }

      .card-content {
        padding: 0 16px 16px;
      }

      .section {
        margin-bottom: 16px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }

      .section:last-child {
        border-bottom: none;
        margin-bottom: 0;
        padding-bottom: 0;
      }

      .field-label {
        font-weight: 500;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        margin-bottom: 8px;
        color: var(--primary-text-color);
      }

      .helper-text {
        font-size: 12px;
        color: var(--secondary-text-color, #727272);
        margin: -4px 0 8px;
      }

      .toggle-with-help {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 8px;
      }

      .toggle-label {
        font-size: 14px;
        color: var(--primary-text-color);
      }

      .toggle-with-help .toggle-switch {
        margin-left: auto;
      }

      .help-anchor {
        position: relative;
        display: inline-flex;
        align-items: center;
      }

      .help-icon {
        cursor: pointer;
        color: var(--secondary-text-color, #727272);
        --mdc-icon-size: 18px;
      }

      .help-icon:hover {
        color: var(--primary-color);
      }

      /* Transparent full-screen catcher so any outside tap dismisses the
         popover (works on touch devices, which have no hover/blur). */
      .popover-backdrop {
        position: fixed;
        inset: 0;
        z-index: 8;
      }

      .info-popover {
        position: absolute;
        top: calc(100% + 6px);
        left: 0;
        z-index: 9;
        width: max-content;
        max-width: 260px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 13px;
        line-height: 1.4;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
      }

      .sub-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
        display: block;
      }

      /* Entity info banner */
      .entity-info {
        margin-bottom: 16px;
        padding: 12px 16px;
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
        border-radius: 8px;
      }

      .entity-info-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }

      .entity-id {
        display: block;
        font-size: 0.85em;
        opacity: 0.8;
        font-family: var(--code-font-family, monospace);
      }

      .cover-controls-wrapper {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin: 8px 0;
      }

      .cover-controls-wrapper .cover-controls {
        margin: 0;
      }

      .cover-controls {
        display: flex;
        align-items: center;
        gap: 4px;
        margin: 8px 0;
      }

      .controls-label {
        font-size: 11px;
        color: inherit;
        opacity: 0.8;
        white-space: nowrap;
        min-width: 36px;
        text-align: right;
      }

      /* Tabs */
      .tabs {
        display: flex;
        border-bottom: 2px solid var(--divider-color, #e0e0e0);
        margin-bottom: 16px;
      }

      .tab {
        flex: 1;
        padding: 10px 16px;
        border: none;
        background: none;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        font-weight: 500;
        color: var(--secondary-text-color);
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        transition: color 0.2s, border-color 0.2s;
        font-family: inherit;
      }

      .tab:hover {
        color: var(--primary-text-color);
      }

      .tab.active {
        color: var(--primary-color);
        border-bottom-color: var(--primary-color);
      }

      .tab:disabled {
        opacity: 0.4;
        cursor: default;
      }

      /* Radio groups */
      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .radio-label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        color: var(--primary-text-color);
      }

      .radio-group.indent {
        margin-left: 28px;
        margin-top: 8px;
      }

      /* Tilt toggle */
      .tilt-toggle {
        display: flex;
        align-items: center;
        gap: 4px;
        cursor: pointer;
        font-size: var(--paper-font-body1_-_font-size, 14px);
        color: var(--primary-text-color);
        font-weight: 500;
      }

      /* Entity grid */
      .entity-grid {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      /* Dual motor config */
      .dual-motor-config {
        display: flex;
        gap: 16px;
        margin-top: 12px;
      }

      .dual-motor-config ha-textfield,
      .dual-motor-config ha-input {
        flex: 1;
      }

      .inline-field {
        margin-top: 8px;
      }

      ha-textfield {
        --mdc-text-field-fill-color: transparent;
      }

      ha-entity-picker {
        display: block;
      }

      .create-new-link {
        display: inline-block;
        margin-top: 8px;
        font-size: 13px;
        color: var(--primary-color);
        text-decoration: none;
        cursor: pointer;
      }

      .create-new-link:hover {
        text-decoration: underline;
      }

      /* Fieldset for disabling during calibration */
      fieldset {
        border: none;
        margin: 0;
        padding: 0;
      }

      fieldset:disabled {
        opacity: 0.5;
        pointer-events: none;
      }

      /* Timing table */
      .timing-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .timing-table th:first-child,
      .timing-table td:first-child {
        width: 65%;
      }

      .timing-table th:last-child,
      .timing-table td:last-child {
        width: 35%;
      }

      .timing-table th {
        text-align: left;
        padding: 8px 12px;
        border-bottom: 2px solid var(--divider-color);
        color: var(--secondary-text-color);
        font-weight: 500;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .timing-table td {
        padding: 10px 12px;
        border-bottom: 1px solid var(--divider-color);
        color: var(--primary-text-color);
      }

      .value-cell {
        font-family: var(--code-font-family, monospace);
        text-align: right;
        white-space: nowrap;
      }

      .timing-input {
        box-sizing: content-box;
        width: 14ch;
        padding: 4px 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 4px;
        font-family: var(--code-font-family, monospace);
        font-size: inherit;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        text-align: right;
      }

      .timing-input::placeholder {
        color: var(--secondary-text-color);
        font-style: italic;
        font-family: inherit;
      }

      .unit {
        color: var(--secondary-text-color);
        margin-left: 2px;
      }

      /* Native select for calibration dropdowns */
      .ha-select {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--card-background-color, var(--ha-card-background));
        color: var(--primary-text-color);
        font-size: var(--paper-font-body1_-_font-size, 14px);
        font-family: var(--paper-font-body1_-_font-family, inherit);
        cursor: pointer;
        box-sizing: border-box;
      }

      .ha-select:focus {
        outline: none;
        border-color: var(--primary-color);
      }

      /* Calibration */
      .cal-form {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: flex-end;
      }

      .cal-field {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 140px;
      }

      .cal-field-narrow {
        flex: 0;
        min-width: 100px;
      }

      .cal-active-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
        padding: 8px 0 0;
        font-size: var(--paper-font-body1_-_font-size, 14px);
      }

      .cal-active-buttons {
        display: flex;
        gap: 8px;
        padding-top: 4px;
      }

      .cal-step {
        opacity: 0.9;
        font-size: 0.9em;
      }

      .calibration-active {
        background: var(--warning-color, #ff9800);
        color: var(--text-primary-color, #fff);
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 0;
        border-bottom: none;
      }

      .cal-label {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--text-primary-color, #fff);
      }

      .button-row {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        margin-top: 8px;
      }

      /* Save indicator */
      .save-bar {
        display: flex;
        justify-content: flex-end;
        padding: 8px 0;
      }

      .saving-indicator {
        font-size: 12px;
        color: var(--secondary-text-color);
        font-style: italic;
      }

      .save-error {
        font-size: 12px;
        color: var(--error-color, #db4437);
        font-style: italic;
      }

      .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 24px;
        color: var(--secondary-text-color);
      }

      .lang-banner {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 12px 16px;
        margin: 0 0 16px;
        background: var(--secondary-background-color, #f5f5f5);
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.4;
      }

      .lang-banner ha-icon {
        color: var(--secondary-text-color, #727272);
        flex: 0 0 auto;
      }

      .lang-banner-body {
        display: flex;
        flex-direction: column;
        gap: 4px;
        flex: 1 1 auto;
        color: var(--primary-text-color, #212121);
      }

      .lang-banner-body a {
        color: var(--primary-color, #03a9f4);
        text-decoration: none;
        font-weight: 500;
      }

      .lang-banner-body a:hover {
        text-decoration: underline;
      }

      .lang-banner ha-icon-button {
        flex: 0 0 auto;
        cursor: pointer;
      }

      .yaml-warning {
        padding: 16px;
        margin: 8px 0;
        background: var(--warning-color, #ff9800);
        color: var(--text-primary-color, #fff);
        border-radius: 8px;
        font-size: 14px;
        line-height: 1.4;
      }

      @keyframes spin {
        from {
          transform: rotate(0deg);
        }
        to {
          transform: rotate(360deg);
        }
      }

      .spin {
        animation: spin 1s linear infinite;
      }
`;
