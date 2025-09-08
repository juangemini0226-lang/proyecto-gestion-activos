document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.app-card .app-header').forEach(function (header) {
    header.addEventListener('click', function () {
      header.nextElementSibling.classList.toggle('collapsed');
    });
  });
});