/* Submission stays with Django; this only explains an in-flight navigation. */
document.addEventListener('submit', function (event) {
  const form = event.target;
  if (!form.matches('form[data-submit-feedback]') || event.defaultPrevented) return;
  const feedback = form.querySelector('.form-busy');
  if (feedback) feedback.hidden = false;
  form.setAttribute('aria-busy', 'true');
});
window.addEventListener('pageshow', function () {
  document.querySelectorAll('form[aria-busy]').forEach(function (form) {
    form.removeAttribute('aria-busy');
    const feedback = form.querySelector('.form-busy');
    if (feedback) feedback.hidden = true;
  });
});
