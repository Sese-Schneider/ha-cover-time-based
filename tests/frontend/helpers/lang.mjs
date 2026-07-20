/**
 * A language code no shipped catalogue will ever cover.
 *
 * Several tests need "a language we don't translate" — to prove strings fall
 * back to English, that locale resolution declines to match, and that the
 * request-a-translation banner appears. Naming a real language there is a trap:
 * the suite used `de` until German was translated, at which point five
 * assertions started failing with messages that blame the code ("expected 'de'
 * to be ''") rather than the stale fixture, in the pull request of whoever
 * contributed the translation.
 *
 * ISO 639-2 reserves qaa-qtz for local use, so `qaa` is a structurally valid
 * BCP-47 tag that cannot become a shipped catalogue. Intl.DisplayNames resolves
 * it without throwing — it echoes the code back — so the banner's display-name
 * and issue-URL paths behave exactly as they do for a real untranslated code.
 */
export const UNSHIPPED_LANG = "qaa";

/** A region variant of {@link UNSHIPPED_LANG}, for base-language fallback tests. */
export const UNSHIPPED_REGION = "qaa-QQ";
