# SteamSelfGifter Frontend

React + TypeScript + Vite frontend for SteamSelfGifter.

## Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **TanStack Query** - Data fetching & caching
- **React Router** - Client-side routing

## Directory Structure

```
frontend/
├── src/
│   ├── components/        # Reusable UI components
│   │   └── common/       # Buttons, cards, inputs, etc.
│   ├── hooks/            # React Query hooks for API
│   ├── pages/            # Page components
│   ├── services/         # API client, WebSocket
│   ├── stores/           # Zustand stores (toasts)
│   ├── types/            # TypeScript definitions
│   ├── App.tsx           # Main app with routing
│   └── main.tsx          # Entry point
├── public/               # Static assets
└── package.json          # Dependencies
```

## Development

### Setup

```bash
cd frontend
npm install
```

### Running

```bash
npm run dev     # Dev server at http://localhost:5173
npm run build   # Production build
npm test        # Run tests
```

### API Proxy

Dev server proxies `/api/*` requests to `http://localhost:8000` (no CORS issues).

## Pages

- **Dashboard** - Overview stats, recent activity, win rate
- **Giveaways** - Browse/filter/enter giveaways
- **Entries** - Entry history
- **Games** - Cached game data
- **Analytics** - Statistics and trends
- **Settings** - Configuration
- **Logs** - Activity logs

## Architecture

### Data Flow

```
Pages → Hooks (useGiveaways, etc.) → API Service → Backend
                ↓
         TanStack Query Cache
```

### Key Hooks

- `useGiveaways` / `useInfiniteGiveaways` - Giveaway data
- `useSettings` / `useUpdateSettings` - App settings
- `useSchedulerControl` - Start/stop automation
- `useWebSocket` - Real-time updates

### State Management

- **Server state**: TanStack Query (caching, refetching)
- **UI state**: Zustand (toasts, modals)
- **URL state**: React Router (filters, pagination)
