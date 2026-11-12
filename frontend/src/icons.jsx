/* Jeu d'icônes SVG inline : aucune dépendance externe, rendu net en dark mode. */
const Svg = ({ children, size = 20, ...props }) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...props}
  >
    {children}
  </svg>
);

export const IconShield = (p) => (
  <Svg {...p}>
    <path d="M12 3l7 3v5.2c0 4.4-2.9 7.5-7 9.8-4.1-2.3-7-5.4-7-9.8V6l7-3z" />
    <path d="M9.2 12.2l1.9 1.9 3.8-4" />
  </Svg>
);

export const IconActivity = (p) => (
  <Svg {...p}>
    <path d="M3 12h3.5l2-6.5 4 13 2.2-6.5H21" />
  </Svg>
);

export const IconWaves = (p) => (
  <Svg {...p}>
    <path d="M3 8c2.2 0 2.2 1.8 4.4 1.8S9.6 8 11.8 8s2.2 1.8 4.4 1.8S18.4 8 21 8" />
    <path d="M3 13.5c2.2 0 2.2 1.8 4.4 1.8s2.2-1.8 4.4-1.8 2.2 1.8 4.4 1.8 2.2-1.8 4.8-1.8" />
    <path d="M3 19c2.2 0 2.2 1.8 4.4 1.8s2.2-1.8 4.4-1.8 2.2 1.8 4.4 1.8 2.2-1.8 4.8-1.8" />
  </Svg>
);

export const IconFlask = (p) => (
  <Svg {...p}>
    <path d="M9 3h6M10 3v6.2L4.8 18a2.1 2.1 0 001.8 3h10.8a2.1 2.1 0 001.8-3L14 9.2V3" />
    <path d="M7.4 15h9.2" />
  </Svg>
);

export const IconBell = (p) => (
  <Svg {...p}>
    <path d="M18 8.6a6 6 0 10-12 0c0 6.7-2.5 6.7-2.5 8.4h17c0-1.7-2.5-1.7-2.5-8.4" />
    <path d="M9.8 20a2.4 2.4 0 004.4 0" />
  </Svg>
);

export const IconGauge = (p) => (
  <Svg {...p}>
    <path d="M20.4 17.2a9 9 0 10-16.8 0" />
    <path d="M12 13l3.7-3.7" />
    <path d="M12 17h.01" />
  </Svg>
);

export const IconCpu = (p) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" />
  </Svg>
);

export const IconDatabase = (p) => (
  <Svg {...p}>
    <ellipse cx="12" cy="5" rx="7.5" ry="3" />
    <path d="M4.5 5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V5" />
    <path d="M4.5 11v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
  </Svg>
);

export const IconServer = (p) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="6" rx="2" />
    <rect x="3" y="14" width="18" height="6" rx="2" />
    <path d="M7 7h.01M7 17h.01" />
  </Svg>
);

export const IconRadio = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="2.2" />
    <path d="M7.8 7.8a6 6 0 000 8.4M16.2 16.2a6 6 0 000-8.4" />
    <path d="M4.9 4.9a10 10 0 000 14.2M19.1 19.1a10 10 0 000-14.2" />
  </Svg>
);

export const IconPlay = (p) => (
  <Svg {...p}>
    <path d="M8 5.5v13l10-6.5-10-6.5z" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconPause = (p) => (
  <Svg {...p}>
    <path d="M8 5v14M16 5v14" />
  </Svg>
);

export const IconRefresh = (p) => (
  <Svg {...p}>
    <path d="M20.5 12a8.5 8.5 0 01-14.7 5.8L3.5 15.5" />
    <path d="M3.5 20v-4.5H8" />
    <path d="M3.5 12a8.5 8.5 0 0114.7-5.8l2.3 2.3" />
    <path d="M20.5 4v4.5H16" />
  </Svg>
);

export const IconArrowUpRight = (p) => (
  <Svg {...p}>
    <path d="M7 17L17 7M8 7h9v9" />
  </Svg>
);

export const IconSearch = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </Svg>
);

export const IconDownload = (p) => (
  <Svg {...p}>
    <path d="M12 3v12M8 11l4 4 4-4" />
    <path d="M4 21h16" />
  </Svg>
);

export const IconCheck = (p) => (
  <Svg {...p}>
    <path d="M20 6.5L9.5 17 4 11.5" />
  </Svg>
);

export const IconAlert = (p) => (
  <Svg {...p}>
    <path d="M12 3.5L22 21H2L12 3.5z" />
    <path d="M12 9v5M12 17.5h.01" />
  </Svg>
);

export const IconClock = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7v5.3l3.4 2" />
  </Svg>
);

export const IconZap = (p) => (
  <Svg {...p}>
    <path d="M13 2L4.5 13.5H11l-1 8.5L19.5 10H13l0-8z" />
  </Svg>
);

export const IconLayers = (p) => (
  <Svg {...p}>
    <path d="M12 2.8l9 5.1-9 5.1-9-5.1 9-5.1z" />
    <path d="M3 13.2l9 5.1 9-5.1" />
    <path d="M3 17.4l9 5.1 9-5.1" />
  </Svg>
);

export const IconBarChart = (p) => (
  <Svg {...p}>
    <path d="M4 3v18h17" />
    <path d="M8 16v-4M12.5 16V7.5M17 16v-6" />
  </Svg>
);

export const IconTerminal = (p) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M7.5 9l3 3-3 3M13 15h3.5" />
  </Svg>
);

export const IconChevronRight = (p) => (
  <Svg {...p}>
    <path d="M9 18l6-6-6-6" />
  </Svg>
);

export const IconCopy = (p) => (
  <Svg {...p}>
    <rect x="8.5" y="8.5" width="11" height="11" rx="2" />
    <path d="M15.5 8.5V6a2 2 0 00-2-2h-7a2 2 0 00-2 2v7a2 2 0 002 2h2.5" />
  </Svg>
);

export const IconWallet = (p) => (
  <Svg {...p}>
    <path d="M4 7.5V18a2 2 0 002 2h13V7.5H6a2 2 0 01-2-2V5h14v2.5" />
    <path d="M16.5 13.5h.01" />
  </Svg>
);

export const IconPercent = (p) => (
  <Svg {...p}>
    <path d="M19 5L5 19" />
    <circle cx="7" cy="7" r="1.6" />
    <circle cx="17" cy="17" r="1.6" />
  </Svg>
);

export const IconTrend = (p) => (
  <Svg {...p}>
    <path d="M3 17l6-6 4 4 7-8" />
    <path d="M14 7h6v6" />
  </Svg>
);

export const IconSparkles = (p) => (
  <Svg {...p}>
    <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3z" />
    <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z" />
  </Svg>
);

export const IconX = (p) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

export const IconMenu = (p) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
);

export const IconExternal = (p) => (
  <Svg {...p}>
    <path d="M14 4h6v6M20 4l-9 9" />
    <path d="M19 14v5a1.5 1.5 0 01-1.5 1.5h-12A1.5 1.5 0 014 19V7a1.5 1.5 0 011.5-1.5H11" />
  </Svg>
);

export const IconLock = (p) => (
  <Svg {...p}>
    <rect x="4.5" y="10" width="15" height="10" rx="2" />
    <path d="M8 10V7.5a4 4 0 118 0V10" />
    <path d="M12 14v2.5" />
  </Svg>
);
