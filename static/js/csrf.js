/*
 * The form token for requests sent from script. Every POST must carry it
 * (utils/csrf.py). Forms carry it as a hidden field; a script sends it in the
 * X-CSRFToken header. The token comes from the meta tag in base.html, so this
 * is the one place scripts read it.
 */
(function () {
  'use strict';

  // The header name the server reads (Flask-WTF's default).
  var HEADER = 'X-CSRFToken';

  function token() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // Adds the token header to a headers object and returns it.
  window.withCsrfToken = function (headers) {
    var result = headers || {};
    result[HEADER] = token();
    return result;
  };
}());
