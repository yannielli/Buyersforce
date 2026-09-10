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

  // Auto-scroll message threads to latest
  const msgList = document.querySelector(".msg-list");
  if (msgList) msgList.scrollTop = msgList.scrollHeight;
});
