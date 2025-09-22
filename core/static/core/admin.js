document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.app-card').forEach((card) => {
    const header = card.querySelector('.app-header');
    const content = card.querySelector('.app-content');
    if (!header || !content) {
      return;
    }

    header.addEventListener('click', () => {
      const isExpanded = header.getAttribute('aria-expanded') !== 'false';
      header.classList.toggle('collapsed', isExpanded);
      header.setAttribute('aria-expanded', String(!isExpanded));
      content.classList.toggle('collapsed', isExpanded);
    });
  });
});
