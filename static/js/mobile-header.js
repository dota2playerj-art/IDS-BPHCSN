// The patient search in the header, on a phone. Below 992px the search box is hidden and the
// magnifier button opens it under the header; a tap outside it, Escape or a search closes it.
// From 992px up the button is hidden and this does nothing.
(function () {
  var button = document.querySelector('.search-toggle');
  var header = document.querySelector('.topheader');
  if (!button || !header) { return; }

  function setOpen(open) {
    header.classList.toggle('search-open', open);
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      var input = header.querySelector('.search-box input');
      if (input) { input.focus(); }
    }
  }

  button.addEventListener('click', function () {
    setOpen(!header.classList.contains('search-open'));
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { setOpen(false); }
  });
  document.addEventListener('click', function (event) {
    if (!header.contains(event.target)) { setOpen(false); }
  });
})();
