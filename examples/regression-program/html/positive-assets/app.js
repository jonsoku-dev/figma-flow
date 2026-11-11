const read = document.getElementById('screen-coffee-read');
const credits = document.getElementById('screen-coffee-credits');
const open = document.getElementById('coffee-open');
const back = document.getElementById('coffee-back');
function showCredits(active) {
  read.hidden = active;
  credits.hidden = !active;
  history.replaceState(null, '', active ? '#credits' : '#read');
  (active ? document.getElementById('credits-title') : document.getElementById('read-title')).setAttribute('tabindex', '-1');
  (active ? document.getElementById('credits-title') : document.getElementById('read-title')).focus({preventScroll: true});
  window.scrollTo(0, 0);
}
open.addEventListener('click', () => showCredits(true));
back.addEventListener('click', () => showCredits(false));
window.addEventListener('hashchange', () => showCredits(location.hash === '#credits'));
if (location.hash === '#credits') showCredits(true);
