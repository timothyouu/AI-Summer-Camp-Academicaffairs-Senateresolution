interface LogoProps {
  size?: number;
  withWordmark?: boolean;
}

export default function Logo({ size = 54, withWordmark = false }: LogoProps) {
  const wordmarkWidth = withWordmark ? size * 3.75 : 0;
  return (
    <div className="flex items-center gap-2.5 text-navy" aria-label="California State University, Bakersfield">
      <svg width={size} height={size * 1.18} viewBox="0 0 64 76" role="img" aria-hidden="true">
        <defs>
          <clipPath id="shield-clip"><path d="M5 4h54v42c0 14-12 22-27 27C17 68 5 60 5 46V4Z" /></clipPath>
        </defs>
        <path d="M4 3h56v43c0 15-12 24-28 29C16 70 4 61 4 46V3Z" fill="#16305e" />
        <path d="M7 6h50v39c0 12-10 20-25 26C17 65 7 57 7 45V6Z" fill="#fff" />
        <g clipPath="url(#shield-clip)">
          <rect x="8" y="7" width="48" height="29" fill="#f5b301" />
          <circle cx="32" cy="33" r="10" fill="#fff" />
          <g stroke="#fff" strokeWidth="2.3">
            <path d="M32 8v14M13 13l11 12M51 13 40 25M9 31h14M55 31H41" />
          </g>
          <rect x="7" y="36" width="50" height="40" fill="#123b91" />
          <g fill="none" stroke="#fff" strokeWidth="2.3">
            <path d="M-2 68C14 44 23 43 30 37M9 75c12-21 24-29 38-38M24 76c7-17 18-29 34-37M40 76c3-13 10-24 21-32" />
          </g>
        </g>
        <path d="M5 4h54v42c0 14-12 22-27 27C17 68 5 60 5 46V4Z" fill="none" stroke="#f5b301" strokeWidth="2" />
      </svg>
      {withWordmark && (
        <svg width={wordmarkWidth} height={size} viewBox="0 0 210 58" aria-hidden="true">
          <text x="0" y="18" fill="#16305e" fontSize="12" fontWeight="600" fontFamily="Arial, sans-serif">CALIFORNIA STATE UNIVERSITY</text>
          <text x="0" y="47" fill="#16305e" fontSize="26" fontWeight="800" fontFamily="Arial, sans-serif">BAKERSFIELD</text>
        </svg>
      )}
    </div>
  );
}
