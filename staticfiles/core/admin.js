document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.app-card .app-header').forEach((header) => {
    header.addEventListener('click', () => {
      header.classList.toggle('collapsed');
      header.nextElementSibling.classList.toggle('collapsed');
    });
  });

  const hideBtn = document.querySelector('.hide-actions');
  if (hideBtn) {
    hideBtn.addEventListener('click', () => {
      document.querySelector('.recent-actions').classList.add('hidden');
    });
  }
});