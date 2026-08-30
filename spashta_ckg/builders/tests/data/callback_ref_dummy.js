// Fixture for named-callback-reference call resolution (spec/js-callback-refs.md).
// addEventListener('evt', namedFn) hands the browser a function it later invokes — a real call
// relationship, resolved the SAME way a direct namedFn() call is. An inline/arrow handler is unchanged
// (nothing to resolve — no false edge, no ambiguity). An unresolved/ambiguous name is an ambiguity,
// never a guessed edge.

function init() {
  console.log("init");
}

function handleClick(e) {
  console.log(e);
}

window.fp = {
  showToast: function () {
    console.log("toast");
  },
};

function wireUp() {
  // named bare-identifier reference -> calls wireUp -> init (like a direct init() call)
  document.addEventListener("DOMContentLoaded", init);
  // dotted/member-expression reference -> calls wireUp -> handleClick
  document.body.addEventListener("click", handleClick);
  // inline anonymous handler -> UNCHANGED (no new edge, no ambiguity — nothing to resolve)
  document.body.addEventListener("change", function (evt) {
    console.log(evt);
  });
  // an unresolved name -> unresolved_call ambiguity, never a guessed edge
  document.body.addEventListener("keydown", notDefinedAnywhere);
}

function fireToast() {
  // a dotted reference resolved via the trailing-property fallback (fp.showToast)
  window.addEventListener("load", fp.showToast);
}
