// Fixture for classList class usage (spec/css-coverage-roadmap.md P3).
// el.classList.add/remove/toggle('x') applies a bare CLASS NAME -> queries_dom StyleClass x.
// A generic .add('y') on a NON-classList object must NOT be treated as a class.

function toggleUI(el, set) {
  el.classList.add("fp-active");
  el.classList.toggle("is-open");
  el.classList.remove("fp-hidden");
  set.add("notaclass");                 // Set.add — NOT classList -> no edge
  document.querySelector(".existing");  // regression: still queries_dom 'existing'
}
