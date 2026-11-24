import { CREDIT } from '../data/product';

const LINKS = [
  { href: '#why', label: 'Why ARC' },
  { href: '#design', label: 'Design' },
  { href: '#layers', label: 'Designed in layers' },
  { href: '#configure', label: 'Finishes' },
  { href: '#top', label: 'Back to top' },
];

export function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <p className="footer__mark" aria-hidden="true">
          ARC
        </p>
        <nav className="footer__nav" aria-label="Footer">
          <ul>
            {LINKS.map((l) => (
              <li key={l.href}>
                <a href={l.href}>{l.label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="footer__text">
          <p>ARC is a fictional controller concept, made for a design portfolio. It is not a real product.</p>
          <p>The cart is a demo: nothing is sold, no payment is taken and no personal data is collected.</p>
        </div>
        <p className="footer__credit">
          {CREDIT.creator ? `Concept and design by ${CREDIT.creator}. ` : ''}
          {CREDIT.made}
        </p>
      </div>
    </footer>
  );
}
