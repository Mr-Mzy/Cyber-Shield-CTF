/*
  main.js
  -------
  One small helper: typeWriter() reveals a string one character at a
  time inside a given element, for the "terminal typing" effect on
  the landing page (called from index.html).
*/

function typeWriter(elementId, text, speed = 18) {
    const el = document.getElementById(elementId);
    if (!el) return;  // fail quietly if the element isn't on this page

    let i = 0;
    el.textContent = "";  // clear it first in case this ever runs twice

    function step() {
        if (i < text.length) {
            el.textContent += text.charAt(i);
            i++;
            setTimeout(step, speed);  // schedule the next character
        }
    }

    step();
}
