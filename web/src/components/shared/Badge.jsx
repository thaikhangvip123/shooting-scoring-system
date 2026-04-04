/**
 * components/shared/Badge.jsx
 */
import clsx from 'clsx';

export default function Badge({ children, variant = 'info', style }) {
  return (
    <span className={clsx('badge', `badge-${variant}`)} style={style}>
      {children}
    </span>
  );
}