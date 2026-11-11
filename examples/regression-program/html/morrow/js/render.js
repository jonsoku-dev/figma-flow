(function () {
  const root = document.getElementById('js-root');
  if (!root) return;
  const heading = document.createElement('h1');
  heading.id = 'js-required';
  heading.textContent = 'JS로 만든 상품 진열';
  root.append(heading);
})();
