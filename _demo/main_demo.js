/**
 * main_demo.js - Demo JavaScript for Spashta-CKG 3.0
 * 
 * Demonstrates Tree-Sitter AST extraction, DOM queries, classList mutations,
 * and event listener callback resolutions.
 * 
 * Part of: Spashta-CKG Demo Project (_demo/)
 */

/**
 * Handle item click and apply dynamic style.
 */
function handleItemClick(event) {
    const target = event.currentTarget;
    target.classList.add("item-active");
    console.log("Item clicked:", target);
}

/**
 * Initialize the demo application.
 * Called when DOM is fully loaded.
 */
function initDemo() {
    console.log("Spashta-CKG 3.0 Demo Ready");
    
    // DOM query extraction
    const listElement = document.querySelector("#list-demo");
    if (listElement) {
        listElement.addEventListener("click", handleItemClick);
    }
}

document.addEventListener("DOMContentLoaded", initDemo);
