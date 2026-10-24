// BuyersForce — small progressive-enhancement helpers (no build step, no deps)

// ---- Global "thinking" overlay, shown while a real page load is under
// way (a link navigation, or a form/button that submits for real --
// Start project, Add/Remove a vendor, etc.) so moving around the app
// never looks like a click did nothing. Deliberately does NOT fire for
// anything that doesn't actually leave this page -- a <details> toggle,
// a plain type="button" control, a link to "#", a new-tab or external
// link, or one of the few actions that just download a file (those are
// tagged data-no-loading below rather than guessed at here).
//
// A handful of spots navigate purely from JS (window.location = ...)
// after already calling preventDefault() on the triggering click/submit
// -- those can't be caught by the listeners below, so they call
// window.BFLoading.show() themselves right before navigating: the
// compare-selection buttons here, and the "ask a teammate" /
// template-switch redirects in project_detail.html and evaluations.html.
window.BFLoading = (function () {
  var overlay = document.getElementById("bf-nav-loading");
  var showTimer = null;
  var maxTimer = null;

  function show() {
    if (!overlay || overlay.classList.contains("is-visible")) { return; }
    clearTimeout(showTimer);
    showTimer = setTimeout(function () {
      overlay.classList.add("is-visible");
    }, 150);
    // Safety net: if nothing ever hides this (a popup blocked the
    // navigation, a download that was missed above, some edge case we
    // didn't anticipate), don't leave it on screen forever.
    clearTimeout(maxTimer);
    maxTimer = setTimeout(hide, 6000);
  }

  function hide() {
    clearTimeout(showTimer);
    clearTimeout(maxTimer);
    if (overlay) { overlay.classList.remove("is-visible"); }
  }

  if (overlay) {
    document.addEventListener("click", function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) { return; }
      var link = e.target.closest("a[href]");
      if (!link || link.dataset.noLoading !== undefined) { return; }
      if (link.target && link.target !== "" && link.target !== "_self") { return; }
      if (link.hasAttribute("download")) { return; }
      var href = link.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#" || /^(mailto|tel|javascript):/i.test(href)) { return; }
      var url;
      try { url = new URL(link.href, window.location.href); } catch (err) { return; }
      if (url.origin !== window.location.origin) { return; }
      if (url.href.split("#")[0] === window.location.href.split("#")[0]) { return; }
      show();
    });

    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (e.defaultPrevented || !(form instanceof HTMLFormElement)) { return; }
      if (form.dataset.noLoading !== undefined) { return; }
      var submitter = e.submitter;
      if (submitter && submitter.dataset.noLoading !== undefined) { return; }
      show();
    });

    // Covers the back/forward button (including the browser restoring a
    // page from its cache, which never re-fires DOMContentLoaded) -- the
    // overlay should never still be sitting over a page that's already
    // here and ready.
    window.addEventListener("pageshow", hide);
  }

  return { show: show, hide: hide };
})();

document.addEventListener("DOMContentLoaded", () => {
  // Role toggle on signup page
  document.querySelectorAll(".role-option").forEach((opt) => {
    opt.addEventListener("click", () => {
      const input = opt.querySelector("input");
      if (!input) return;
      document.querySelectorAll(".role-option").forEach((o) => o.classList.remove("selected"));
      opt.classList.add("selected");
      input.checked = true;
    });
  });

  // Score dot pickers on evaluation scorecards
  document.querySelectorAll(".score-pill-group").forEach((group) => {
    group.querySelectorAll(".score-dot").forEach((dot) => {
      dot.addEventListener("click", () => {
        const input = dot.querySelector("input");
        if (!input) return;
        group.querySelectorAll(".score-dot").forEach((d) => d.classList.remove("selected"));
        dot.classList.add("selected");
        input.checked = true;
      });
    });
  });

  // Vendor comparison selection for Discover + "Ask Frankie" results:
  // persisted in localStorage, not just read off whatever's checked on
  // the page right now. Discover's letter-jump/search/filter controls are
  // plain GET reloads, so without this, checking "Compare" on one vendor,
  // jumping to a different letter, and checking another used to lose the
  // first pick entirely. A separate, smaller cap (3) applies to Compare's
  // own "Short List" checkboxes, handled inline on compare.html since that
  // page's form controls live outside the <form> element itself
  // (form="shortlist-form") -- unrelated to this selection.
  const BF_COMPARE_KEY = "bf_compare_selection";
  function readCompareSelection() {
    try {
      const raw = window.localStorage.getItem(BF_COMPARE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }
  function writeCompareSelection(list) {
    try {
      window.localStorage.setItem(BF_COMPARE_KEY, JSON.stringify(list));
    } catch (e) {
      // storage unavailable (private browsing, quota, etc.) -- the
      // selection just won't survive a reload; nothing else to do.
    }
  }
  const compareChangeListeners = [];
  function notifyCompareChange() {
    const sel = readCompareSelection();
    compareChangeListeners.forEach((fn) => fn(sel));
  }
  // Exposed so discover.html's "Ask Frankie" chat script can read/add/
  // remove vendors found via chat into this very same cross-page
  // selection, without either file needing to know about the other's
  // markup.
  window.BFCompare = {
    getSelection: readCompareSelection,
    isSelected: (id) => readCompareSelection().some((v) => String(v.id) === String(id)),
    add: (vendor, max) => {
      const sel = readCompareSelection();
      if (sel.some((v) => String(v.id) === String(vendor.id))) return sel;
      if (max && sel.length >= max) return sel;
      sel.push(vendor);
      writeCompareSelection(sel);
      notifyCompareChange();
      return sel;
    },
    remove: (id) => {
      const sel = readCompareSelection().filter((v) => String(v.id) !== String(id));
      writeCompareSelection(sel);
      notifyCompareChange();
      return sel;
    },
    clear: () => {
      writeCompareSelection([]);
      notifyCompareChange();
    },
    onChange: (fn) => { compareChangeListeners.push(fn); },
  };

  const compareForm = document.getElementById("compare-form");
  if (compareForm) {
    const compareMax = parseInt(compareForm.dataset.compareMax, 10) || 5;
    const compareTray = document.getElementById("compare-tray");
    const compareTrayChips = document.getElementById("compare-tray-chips");
    const compareTrayCount = document.getElementById("compare-tray-count");
    const compareTrayClear = document.getElementById("compare-tray-clear");
    const compareTrayButton = document.getElementById("compare-tray-button");
    const compareSubmitBtn = document.getElementById("compare-submit");

    const boxes = () => Array.from(compareForm.querySelectorAll('input[type="checkbox"]'));

    const vendorFromCheckbox = (box) => ({
      id: box.value,
      company_name: box.dataset.companyName || "",
      accent: box.dataset.accent || "",
      initials: box.dataset.initials || "",
      logo_url: box.dataset.logoUrl || "",
    });

    const buildCompareUrl = (sel) => {
      const ids = sel.map((v) => v.id).join(",");
      return compareForm.getAttribute("action") + (ids ? "?ids=" + encodeURIComponent(ids) : "");
    };

    function renderCompareChip(vendor) {
      const chip = document.createElement("span");
      chip.className = "compare-chip";
      const logo = document.createElement("span");
      logo.className = "vendor-logo";
      logo.style.cssText = "width:18px;height:18px;font-size:8px;";
      logo.style.background = vendor.accent || "var(--brand)";
      if (vendor.logo_url) {
        const img = document.createElement("img");
        img.src = vendor.logo_url;
        img.alt = "";
        img.onerror = () => { img.remove(); logo.textContent = vendor.initials || ""; };
        logo.appendChild(img);
      } else {
        logo.textContent = vendor.initials || "";
      }
      const name = document.createElement("span");
      name.textContent = vendor.company_name || ("Vendor #" + vendor.id);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "compare-chip-remove";
      remove.setAttribute("aria-label", "Remove " + (vendor.company_name || "vendor") + " from comparison");
      remove.textContent = "×";
      remove.addEventListener("click", () => window.BFCompare.remove(vendor.id));
      chip.appendChild(logo);
      chip.appendChild(name);
      chip.appendChild(remove);
      return chip;
    }

    function renderCompareUI() {
      const sel = readCompareSelection();
      const selIds = sel.map((v) => String(v.id));

      // Sync this page's own checkboxes to the stored selection -- a
      // vendor checked on a previous letter/search page shows checked
      // here too if it's also on this page, and the cap disables the
      // rest once the selection (not just this page) is full.
      boxes().forEach((box) => {
        box.checked = selIds.indexOf(box.value) !== -1;
        box.disabled = !box.checked && sel.length >= compareMax;
      });

      // Any "+ Compare" buttons Ask Frankie has rendered into the chat so
      // far -- querySelectorAll just finds nothing until Frankie has.
      document.querySelectorAll(".ai-vendor-mini-compare-btn").forEach((btn) => {
        const added = selIds.indexOf(String(btn.dataset.vendorId)) !== -1;
        btn.classList.toggle("is-added", added);
        btn.textContent = added ? "✓ Added" : "+ Compare";
        btn.disabled = !added && sel.length >= compareMax;
      });

      if (compareTray) {
        compareTray.hidden = sel.length === 0;
        if (compareTrayChips) {
          compareTrayChips.innerHTML = "";
          sel.forEach((vendor) => compareTrayChips.appendChild(renderCompareChip(vendor)));
        }
        if (compareTrayCount) compareTrayCount.textContent = sel.length;
        if (compareTrayButton) {
          compareTrayButton.disabled = sel.length < 2;
          compareTrayButton.dataset.href = buildCompareUrl(sel);
        }
      }
      if (compareSubmitBtn) compareSubmitBtn.disabled = sel.length < 2;
    }

    compareForm.addEventListener("change", (e) => {
      if (!e.target || e.target.type !== "checkbox") return;
      const box = e.target;
      if (box.checked) {
        window.BFCompare.add(vendorFromCheckbox(box), compareMax);
      } else {
        window.BFCompare.remove(box.value);
      }
    });

    // Progressive enhancement: with JS, "Compare selected vendors" (and
    // the tray's own button) always compares the full cross-page
    // selection, not just whatever happens to be checked on the page in
    // view right now. Without JS, the form still submits normally with
    // just this page's checked boxes -- a smaller but working compare.
    compareForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const sel = readCompareSelection();
      if (sel.length < 2) return;
      window.BFLoading.show();
      window.location.href = buildCompareUrl(sel);
    });

    if (compareTrayButton) {
      compareTrayButton.addEventListener("click", () => {
        if (compareTrayButton.disabled) return;
        window.BFLoading.show();
        window.location.href = compareTrayButton.dataset.href || buildCompareUrl(readCompareSelection());
      });
    }
    if (compareTrayClear) {
      compareTrayClear.addEventListener("click", () => window.BFCompare.clear());
    }

    // "+ Compare" buttons inside Ask Frankie's chat results are added long
    // after this script runs, so this listens on a stable ancestor
    // instead of each button -- delegation picks up every one Frankie
    // ever renders, this turn or a later one.
    document.addEventListener("click", (e) => {
      const btn = e.target.closest && e.target.closest(".ai-vendor-mini-compare-btn");
      if (!btn) return;
      if (btn.classList.contains("is-added")) {
        window.BFCompare.remove(btn.dataset.vendorId);
      } else {
        window.BFCompare.add({
          id: btn.dataset.vendorId,
          company_name: btn.dataset.companyName || "",
          accent: btn.dataset.accent || "",
          initials: btn.dataset.initials || "",
          logo_url: btn.dataset.logoUrl || "",
        }, compareMax);
      }
    });

    window.BFCompare.onChange(renderCompareUI);
    renderCompareUI();
  }

  // "Open to Outreach" sub-options on the profile form: shown only
  // while the parent toggle is on, and "Not seeking outreach" is
  // mutually exclusive with the other three sub-options (checking it
  // clears them, and vice versa) since it says the opposite thing. The
  // server enforces the same exclusivity independently, in case this
  // JS never runs.
  const outreachEnabled = document.getElementById("outreach_enabled");
  const outreachSuboptions = document.getElementById("outreach-suboptions");
  if (outreachEnabled && outreachSuboptions) {
    outreachEnabled.addEventListener("change", () => {
      outreachSuboptions.style.display = outreachEnabled.checked ? "flex" : "none";
    });
    const noneBox = document.getElementById("outreach_none");
    const otherBoxes = Array.from(outreachSuboptions.querySelectorAll(".outreach-option"));
    if (noneBox) {
      noneBox.addEventListener("change", () => {
        if (noneBox.checked) otherBoxes.forEach((b) => { b.checked = false; });
      });
      otherBoxes.forEach((box) => {
        box.addEventListener("change", () => {
          if (box.checked) noneBox.checked = false;
        });
      });
    }
  }

  // Evaluation-template builder: success criteria start at 5 rows (each
  // defaulting to a 20% weight so they already sum to 100) and a buyer can
  // add one row at a time with "+ Add criterion" instead of being capped
  // at 5 -- up to the same MAX_EVAL_CRITERIA cap app.py enforces server-side
  // (read off data-max so the two never drift apart). The live "Total
  // weight" readout mirrors that same 100% check so a buyer sees a mismatch
  // before they submit, not after.
  const criteriaRows = document.getElementById("criteria-rows");
  const addCriterionBtn = document.getElementById("add-criterion-btn");
  const criteriaTotalValue = document.getElementById("criteria-total-value");
  if (criteriaRows && criteriaTotalValue) {
    const maxCriteria = parseInt(criteriaRows.dataset.max, 10) || 50;
    const criterionRows = () => Array.from(criteriaRows.querySelectorAll(".criterion-input-row"));
    const updateCriteriaTotal = () => {
      const rows = criterionRows();
      const total = rows.reduce((sum, row) => {
        const label = row.querySelector('input[name="criterion_label"]');
        const weight = row.querySelector('input[name="criterion_weight"]');
        if (!label || !weight || !label.value.trim()) return sum;
        return sum + (parseInt(weight.value, 10) || 0);
      }, 0);
      criteriaTotalValue.textContent = total;
      criteriaTotalValue.classList.toggle("total-mismatch", total !== 100);
      if (addCriterionBtn) addCriterionBtn.disabled = rows.length >= maxCriteria;
    };
    criteriaRows.addEventListener("input", updateCriteriaTotal);
    if (addCriterionBtn) {
      addCriterionBtn.addEventListener("click", () => {
        const rows = criterionRows();
        if (rows.length >= maxCriteria) return;
        const newRow = rows[0].cloneNode(true);
        const label = newRow.querySelector('input[name="criterion_label"]');
        const weight = newRow.querySelector('input[name="criterion_weight"]');
        // On the "edit template" page, rows[0] may be an existing
        // criterion carrying a hidden criterion_id -- a cloned row is
        // always a brand-new criterion, never a copy of that one, so
        // this must come back empty (evaluation_new.html has no such
        // field at all, so this is always a no-op there).
        const criterionId = newRow.querySelector('input[name="criterion_id"]');
        if (criterionId) criterionId.value = "";
        if (label) {
          label.value = "";
          label.placeholder = `Criterion ${rows.length + 1} (e.g. Ease of integration)`;
        }
        if (weight) weight.value = "0";
        criteriaRows.appendChild(newRow);
        updateCriteriaTotal();
        if (label) label.focus();
      });
    }
    updateCriteriaTotal();
  }

  // "Start project" form on the Evaluations tab: the project-name field is
  // pre-filled with a suggestion built from whichever "ready to evaluate"
  // vendors are checked, and keeps re-suggesting as the buyer (un)checks
  // vendors -- but only until they've actually typed their own name, so a
  // deliberate edit is never silently overwritten.
  const startProjectForm = document.getElementById("start-project-form");
  const projectNameInput = document.getElementById("project-name");
  if (startProjectForm && projectNameInput) {
    let nameEdited = false;
    const suggestProjectName = () => {
      if (nameEdited) return;
      const names = Array.from(startProjectForm.querySelectorAll(".ready-vendor-checkbox:checked"))
        .map((box) => {
          const row = box.closest(".ready-vendor-row");
          const label = row && row.querySelector("strong");
          return label ? label.textContent.trim() : "";
        })
        .filter(Boolean);
      projectNameInput.value = names.join(" vs. ");
    };
    projectNameInput.addEventListener("input", () => { nameEdited = true; });
    startProjectForm.querySelectorAll(".ready-vendor-checkbox").forEach((box) => {
      box.addEventListener("change", suggestProjectName);
    });
    suggestProjectName();
  }

  // "Close this evaluation" form on project_detail.html: show either the
  // winning-vendor radio list or the no-award reasons, never both, based
  // on which outcome radio is picked. Defaults to the "selected vendor"
  // fields showing (that radio starts checked), so this just handles
  // switching to "no vendor" and back.
  const outcomeSelected = document.getElementById("outcome-selected");
  const outcomeNoAward = document.getElementById("outcome-no-award");
  const outcomeSelectedFields = document.getElementById("outcome-selected-fields");
  const outcomeNoAwardFields = document.getElementById("outcome-no-award-fields");
  if (outcomeSelected && outcomeNoAward && outcomeSelectedFields && outcomeNoAwardFields) {
    const syncOutcomeFields = () => {
      outcomeSelectedFields.style.display = outcomeSelected.checked ? "block" : "none";
      outcomeNoAwardFields.style.display = outcomeNoAward.checked ? "block" : "none";
    };
    outcomeSelected.addEventListener("change", syncOutcomeFields);
    outcomeNoAward.addEventListener("change", syncOutcomeFields);
    syncOutcomeFields();
  }

  // "Rename or change scorecard" form on project_detail.html: only warn
  // before submitting if the template is actually being changed AND this
  // project already has scores recorded -- renaming alone, or switching
  // on a project nobody has scored yet, needs no confirmation.
  const editProjectTemplateSelect = document.getElementById("edit-project-template");
  const editProjectForm = editProjectTemplateSelect && editProjectTemplateSelect.closest("form");
  if (editProjectForm && editProjectTemplateSelect) {
    const originalTemplateId = editProjectTemplateSelect.dataset.current;
    const hasScores = editProjectTemplateSelect.dataset.hasScores === "1";
    editProjectForm.addEventListener("submit", (e) => {
      const changingTemplate = editProjectTemplateSelect.value !== originalTemplateId;
      if (changingTemplate && hasScores) {
        const ok = confirm(
          "Switching scorecards hides scores tied to criteria the new one doesn't have. " +
          "Nothing is deleted -- they'll come back if you switch back. Continue?"
        );
        if (!ok) e.preventDefault();
      }
    });
  }

  // Message threads list newest-first now (see app.py's thread queries),
  // so the latest message is already the first thing in view at the top
  // -- no auto-scroll needed (this used to scroll to the bottom, back
  // when oldest-first put the latest message there instead).

  // Time zone picker: a search box layered over the real <select> (built
  // server-side in _timezone_field.html, with optgroups and GMT-offset
  // labels -- "United States" pinned first, then the rest alphabetically).
  // The <select> still carries the value the form submits and works fine
  // with no JS at all; this just swaps in a filterable text box on top of
  // it so narrowing ~430 zones doesn't mean scrolling a giant dropdown.
  document.querySelectorAll("select[data-tz-picker]").forEach((select) => {
    const wrap = select.nextElementSibling;
    if (!wrap || !wrap.matches("[data-tz-picker-wrap]")) return;
    const input = wrap.querySelector(".tz-picker-input");
    const list = wrap.querySelector("[data-tz-picker-list]");
    const empty = wrap.querySelector("[data-tz-picker-empty]");
    const options = Array.from(wrap.querySelectorAll(".tz-picker-option"));
    const groups = Array.from(wrap.querySelectorAll(".tz-picker-group"));
    let highlighted = null;

    if (select.selectedIndex > 0) input.value = select.options[select.selectedIndex].text;
    select.style.display = "none";
    wrap.style.display = "block";

    const visibleOptions = () => options.filter((o) => o.style.display !== "none");

    const setHighlight = (option) => {
      if (highlighted) highlighted.classList.remove("highlighted");
      highlighted = option;
      if (highlighted) {
        highlighted.classList.add("highlighted");
        highlighted.scrollIntoView({ block: "nearest" });
      }
    };

    const filter = () => {
      const q = input.value.trim().toLowerCase();
      let anyVisible = false;
      options.forEach((o) => {
        const match = !q || o.textContent.toLowerCase().indexOf(q) !== -1;
        o.style.display = match ? "" : "none";
        if (match) anyVisible = true;
      });
      groups.forEach((g) => {
        let next = g.nextElementSibling;
        let hasVisible = false;
        while (next && !next.classList.contains("tz-picker-group")) {
          if (next.classList.contains("tz-picker-option") && next.style.display !== "none") hasVisible = true;
          next = next.nextElementSibling;
        }
        g.style.display = hasVisible ? "" : "none";
      });
      empty.style.display = anyVisible ? "none" : "block";
      setHighlight(null);
    };

    const open = () => { list.style.display = "block"; filter(); };
    const close = () => { list.style.display = "none"; setHighlight(null); };
    const choose = (option) => {
      select.value = option.dataset.value;
      input.value = option.textContent;
      close();
    };

    input.addEventListener("focus", open);
    input.addEventListener("input", () => {
      select.value = ""; // typing without picking a result must not silently submit the old value
      open();
    });
    input.addEventListener("keydown", (e) => {
      if (list.style.display === "none") return;
      const vis = visibleOptions();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const idx = vis.indexOf(highlighted);
        setHighlight(idx < vis.length - 1 ? vis[idx + 1] : vis[0]);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const idx = vis.indexOf(highlighted);
        setHighlight(idx > 0 ? vis[idx - 1] : vis[vis.length - 1]);
      } else if (e.key === "Enter") {
        if (highlighted) { e.preventDefault(); choose(highlighted); }
      } else if (e.key === "Escape") {
        close();
      }
    });
    options.forEach((o) => {
      o.addEventListener("mousedown", (e) => e.preventDefault());
      o.addEventListener("click", () => choose(o));
      o.addEventListener("mouseenter", () => setHighlight(o));
    });
    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target)) close();
    });
  });

  // Password visibility toggles: a "Show"/"Hide" button next to any
  // password field wrapped in .password-field (login, signup, accept
  // invite, and account's three password fields on the Change password
  // tab). One generic data-attribute handler instead of per-page wiring.
  document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
    const input = document.getElementById(btn.dataset.passwordToggle);
    if (!input) return;
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
});
