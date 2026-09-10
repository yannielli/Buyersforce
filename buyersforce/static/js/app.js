// BuyersForce — small progressive-enhancement helpers (no build step, no deps)

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

  // Cap Discover's compare checkboxes at 5 -- research/compare stage; a
  // separate, smaller cap (3) applies to Compare's own "Short List"
  // checkboxes, handled inline on compare.html since that page's form
  // controls live outside the <form> element itself (form="shortlist-form").
  const compareForm = document.getElementById("compare-form");
  if (compareForm) {
    const boxes = () => Array.from(compareForm.querySelectorAll('input[type="checkbox"]'));
    compareForm.addEventListener("change", () => {
      const checked = boxes().filter((b) => b.checked);
      boxes().forEach((b) => {
        b.disabled = checked.length >= 5 && !b.checked;
      });
      const submitBtn = document.getElementById("compare-submit");
      if (submitBtn) submitBtn.disabled = checked.length < 2;
    });
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

  // Auto-scroll message threads to latest
  const msgList = document.querySelector(".msg-list");
  if (msgList) msgList.scrollTop = msgList.scrollHeight;
});
