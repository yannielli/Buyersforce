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

  // Cap compare checkboxes at 3
  const compareForm = document.getElementById("compare-form");
  if (compareForm) {
    const boxes = () => Array.from(compareForm.querySelectorAll('input[type="checkbox"]'));
    compareForm.addEventListener("change", () => {
      const checked = boxes().filter((b) => b.checked);
      boxes().forEach((b) => {
        b.disabled = checked.length >= 3 && !b.checked;
      });
      const submitBtn = document.getElementById("compare-submit");
      if (submitBtn) submitBtn.disabled = checked.length < 2;
    });
  }

  // Auto-scroll message threads to latest
  const msgList = document.querySelector(".msg-list");
  if (msgList) msgList.scrollTop = msgList.scrollHeight;
});
