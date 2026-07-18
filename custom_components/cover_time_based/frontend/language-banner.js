/**
 * The "your language isn't translated yet" nudge shown in the config card.
 *
 * Cover Time Based ships card strings in English, Portuguese and Polish. A user
 * on any other language silently reads English with no hint that asking for a
 * translation is welcome. This module builds a one-time, per-locale dismissable
 * banner inviting them to open a prefilled GitHub issue.
 *
 * Dismissals are stored per-locale rather than as a single flag: dismiss `de`,
 * switch HA to `fr`, then switch back, and a scalar store would have forgotten
 * the original dismissal and re-nagged. Storage is per-browser, and every access
 * is guarded — Safari private mode throws on localStorage, and a forgotten
 * dismissal is far better than a card that fails to render.
 */

import { html } from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";
import { isLanguageSupported } from "./translations.js";

/** Upstream repository — the issue link must not point at a fork. */
export const GITHUB_REPO_URL =
  "https://github.com/Sese-Schneider/ha-cover-time-based";

export const LANG_DISMISSED_STORAGE_KEY =
  "cover_time_based_card.dismissed_lang_requests";

/**
 * A prefilled "new issue" URL requesting a translation for `code`.
 *
 * Uses `?body=` rather than `?template=`: a template link resolves against the
 * repo's default branch, so it would prefill nothing until the template merged.
 *
 * Title and body are deliberately English rather than localised — they land in
 * the project's issue tracker, which the maintainers read in English. No
 * `labels=` parameter: the repo has no `translation` label to request.
 */
export function buildTranslationRequestUrl(code, displayName) {
  const params = new URLSearchParams({
    title: `Translation request: ${displayName} (${code})`,
    body: [
      `I'd like Cover Time Based to be translated into: **${displayName}** (\`${code}\`).`,
      ``,
      `- [ ] I'm happy to review the translation`,
    ].join("\n"),
  });
  return `${GITHUB_REPO_URL}/issues/new?${params.toString()}`;
}

/**
 * Native display name for a BCP-47 code ("fr" -> "français"), falling back to
 * the English name and then the raw code, with every Intl call guarded.
 *
 * Intl.DisplayNames defaults to fallback:"code", so an unknown tag echoes the
 * code straight back; the `!== code` guards stop that echo being mistaken for a
 * real name.
 */
export function languageDisplayName(code) {
  if (!code) return code;
  try {
    const native = new Intl.DisplayNames([code], { type: "language" }).of(code);
    if (native && native !== code) return native;
  } catch (_) {
    // Invalid locale for Intl — fall through to the English name.
  }
  try {
    const english = new Intl.DisplayNames(["en"], { type: "language" }).of(code);
    if (english && english !== code) return english;
  } catch (_) {
    // Intl unavailable — fall through to the raw code.
  }
  return code;
}

/** The dismissed locales, or [] when absent, unreadable or corrupt. */
function dismissedLocales() {
  try {
    const raw = window.localStorage.getItem(LANG_DISMISSED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

/** Whether the nudge was already dismissed for `code`. */
export function isLangDismissed(code) {
  return dismissedLocales().includes(code);
}

/** Record a dismissal for `code` (append + de-dup). */
export function persistLangDismissed(code) {
  try {
    const current = dismissedLocales();
    if (current.includes(code)) return;
    window.localStorage.setItem(
      LANG_DISMISSED_STORAGE_KEY,
      JSON.stringify([...current, code])
    );
  } catch (_) {
    // storage unavailable — the dismissal simply isn't remembered
  }
}

/**
 * The nudge, or "" when the language is covered or already dismissed.
 *
 * The copy always renders in English: by construction the banner only appears
 * to users whose language has no catalogue, so `_t` falls back to EN anyway —
 * which is why `language_request.*` exists in EN only.
 */
export function renderLanguageBanner(card) {
  const code = (card.hass?.language || "").replace(/_/g, "-");
  if (isLanguageSupported(code)) return "";
  if (card._dismissedLangs?.has(code) || isLangDismissed(code)) return "";

  const displayName = languageDisplayName(code);
  const message = card._t("language_request.message", { language: displayName });
  return html`
    <div class="lang-banner">
      <ha-icon icon="mdi:translate"></ha-icon>
      <div class="lang-banner-body">
        <span>${message}</span>
        <a
          href=${buildTranslationRequestUrl(code, displayName)}
          target="_blank"
          rel="noopener noreferrer"
          >${card._t("language_request.action")}</a
        >
      </div>
      <ha-icon-button
        .label=${card._t("language_request.dismiss")}
        @click=${() => card._dismissLanguageBanner(code)}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </ha-icon-button>
    </div>
  `;
}
