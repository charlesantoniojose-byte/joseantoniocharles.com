document.getElementById('year').textContent = new Date().getFullYear();

// Mobile nav
const navToggle = document.getElementById('navToggle');
const nav = document.getElementById('nav');

navToggle.addEventListener('click', () => {
  const isOpen = nav.classList.toggle('open');
  navToggle.setAttribute('aria-expanded', isOpen);
});

nav.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    nav.classList.remove('open');
    navToggle.setAttribute('aria-expanded', false);
  });
});

// Highlight the nav link for the section in view
const navLinks = [...nav.querySelectorAll('a[href^="#"]')];
const sections = navLinks.map((a) => document.querySelector(a.getAttribute('href'))).filter(Boolean);
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((a) => a.classList.toggle('is-current', a.getAttribute('href') === '#' + entry.target.id));
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  sections.forEach((s) => observer.observe(s));
}

// Project filter
const chips = document.querySelectorAll('.filter-bar .chip');
const cases = document.querySelectorAll('.case');
chips.forEach((chip) => {
  chip.addEventListener('click', () => {
    const filter = chip.dataset.filter;
    chips.forEach((c) => {
      const active = c === chip;
      c.classList.toggle('is-active', active);
      c.setAttribute('aria-pressed', active);
    });
    cases.forEach((card) => {
      card.hidden = filter !== 'all' && !card.dataset.cat.split(' ').includes(filter);
    });
  });
});

// Contact form: static hosting has no backend, so compose an email in the visitor's mail app
const form = document.getElementById('contactForm');
form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  const name = data.get('name').trim();
  const company = data.get('company').trim();
  const subject = `Portfolio inquiry from ${name}${company ? ' (' + company + ')' : ''}`;
  const body = `${data.get('message').trim()}\n\n${name}\n${data.get('email').trim()}${company ? '\n' + company : ''}`;
  window.location.href = `mailto:Jose.Antonio.Charles@outlook.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  document.getElementById('formNote').textContent = 'Your email app should open with the message ready to send. If it does not, email Jose.Antonio.Charles@outlook.com directly.';
});
