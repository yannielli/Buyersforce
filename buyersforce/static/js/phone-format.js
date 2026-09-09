/* Lightweight phone-number formatting for the country-code + phone field
 * pairs on signup and the account profile form. No external dependency:
 * the country <select> already carries each option's dial code as
 * data-dial (rendered server-side from app.py's PHONE_COUNTRIES), so this
 * file only needs to know how to *format* the digits, not what the dial
 * codes are.
 *
 * US/Canada (shared NANP numbering) get the exact "(555) 555-5555" mask.
 * A handful of other common countries get a reasonable grouped format.
 * Anything else (including "Other / not listed") just gets digits grouped
 * in 3s -- not an official national format, but readable, and nobody is
 * stuck if their country isn't in the list.
 */
(function () {
  function digitsOnly(s) {
    return (s || "").replace(/\D/g, "");
  }

  function groupGeneric(d) {
    var parts = [];
    for (var i = 0; i < d.length; i += 3) parts.push(d.slice(i, i + 3));
    return parts.join(" ");
  }

  function formatNANP(d) {
    d = d.slice(0, 10);
    if (d.length <= 3) return d;
    if (d.length <= 6) return "(" + d.slice(0, 3) + ") " + d.slice(3);
    return "(" + d.slice(0, 3) + ") " + d.slice(3, 6) + "-" + d.slice(6);
  }

  function formatGB(d) {
    d = d.slice(0, 10);
    if (d.length <= 4) return d;
    if (d.length <= 7) return d.slice(0, 4) + " " + d.slice(4);
    return d.slice(0, 4) + " " + d.slice(4, 7) + " " + d.slice(7);
  }

  function formatIN(d) {
    d = d.slice(0, 10);
    if (d.length <= 5) return d;
    return d.slice(0, 5) + " " + d.slice(5);
  }

  function formatAU(d) {
    d = d.slice(0, 9);
    if (d.length <= 3) return d;
    if (d.length <= 6) return d.slice(0, 3) + " " + d.slice(3);
    return d.slice(0, 3) + " " + d.slice(3, 6) + " " + d.slice(6);
  }

  function formatBR(d) {
    d = d.slice(0, 11);
    if (d.length <= 2) return d;
    if (d.length <= 7) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }

  var FORMATTERS = { US: formatNANP, CA: formatNANP, GB: formatGB, IN: formatIN, AU: formatAU, BR: formatBR };

  function wirePhoneField(inputId, selectId) {
    var input = document.getElementById(inputId);
    var select = document.getElementById(selectId);
    if (!input || !select) return;

    function currentDial() {
      var opt = select.options[select.selectedIndex];
      return (opt && opt.getAttribute("data-dial")) || "";
    }

    function extractNational(rawValue) {
      var digits = digitsOnly(rawValue);
      var dial = currentDial();
      if (dial && digits.indexOf(dial) === 0 && digits.length > dial.length) {
        var rest = digits.slice(dial.length);
        if (rest.length >= 7) digits = rest;
      }
      return digits;
    }

    function reformat() {
      var digits = extractNational(input.value);
      var fmt = FORMATTERS[select.value] || groupGeneric;
      var national = fmt(digits);
      var dial = currentDial();
      input.value = dial ? "+" + dial + " " + national : national;
    }

    input.addEventListener("input", reformat);
    select.addEventListener("change", reformat);
    reformat(); // normalize whatever the server rendered on load
  }

  window.BFPhone = { wire: wirePhoneField };
})();
