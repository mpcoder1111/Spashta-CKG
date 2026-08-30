/* Deterministic fixture for build_js_ast.py (MVP — spec/js-support.md US-1).
   Exercises: object-literal namespace defs (like window.fp), member-call resolution,
   bare function def+call, and an external callee that must become an ambiguity (never a
   guessed edge). */

// An object-literal namespace assigned to a member target (the window.fp pattern).
window.app = {
  greet: function (name) {
    return "hi " + name;
  },
  warn: function (msg) {
    window.app.greet(msg); // member call -> window.app.greet
  }
};

function helper() {
  return 1;
}

function run() {
  helper();               // bare call -> helper
  window.app.greet("x");  // member call -> window.app.greet
  console.log("done");    // external callee -> unresolved_call ambiguity, NOT a guessed edge
}

// Event coupling (Phase 2): a listener and a dispatcher of the SAME custom event name are
// coupled through one shared Event node. Both enclosing functions get the `Signal` role
// (vanilla adapter — "event handler or producer").
function init() {
  document.body.addEventListener("app:refresh", function () { // registers_event_handler -> Event 'app:refresh'
    helper();
  });
}

function fireRefresh() {
  document.body.dispatchEvent(new CustomEvent("app:refresh")); // dispatches_event -> Event 'app:refresh'
}

// DOM queries (Phase 2, cross-language): a literal selector -> a StyleClass/StyleID node named by the
// selector (joins by name to the CSS definition). A complex/dynamic selector -> ambiguity, never a guess.
function paint() {
  document.getElementById("main-panel");  // queries_dom -> StyleID 'main-panel'
  document.querySelectorAll(".widget");   // queries_dom -> StyleClass 'widget'
  document.querySelector(".a .b");        // compound selector -> unresolved_selector ambiguity
}
