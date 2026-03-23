# HR Chatbot — UX/UI Design Layer Architecture

## Overview

The UX/UI layer sits on top of the completed 5-phase backend and provides a polished,
production-ready interface for employees, HR admins, and super admins. It is a React 18 +
TypeScript + Tailwind CSS SPA served from the `frontend/` Docker service.

---

## Component Map

```
App.tsx  (root — ToastProvider, auth, branding, mobile layout)
├── LoginPage.tsx          — credentials → MFA step-up flow
│   └── verifyMfaLogin()   — POST /auth/mfa/verify-login
├── Sidebar.tsx            — collapsible, date-grouped sessions, search, mobile overlay
├── ChatPage.tsx           — session management, history loading
│   └── ChatWindow.tsx     — message list + streaming text
│       ├── MessageBubble  — citations, confidence, feedback, escalation
│       └── ChatInput.tsx  — auto-resize textarea + role-aware quick chips
├── AdminDashboard.tsx     — KPI cards, document management, user approvals
├── UploadDocs.tsx         — drag-drop upload, version history
├── UserSettingsPage.tsx   — Profile / Security / Privacy tabs
│   ├── Profile tab        — full_name, email, phone, department
│   ├── Security tab       — TOTP MFA enrollment (QR + manual key + recovery codes)
│   └── Privacy tab        — GDPR Art.15 data export + Art.17 erasure
└── NotificationToast.tsx  — global toast notifications (success/error/warning/info)
```

---

## Feature Inventory

### U-01 — Chat Interface
- Streaming text with blinking cursor `▊`
- Auto-scroll to bottom on new messages
- Session history loaded on session switch

### U-02 — Source Citation Panel
- Citation cards with source filename, page number, excerpt
- Click citation → DocumentViewer modal (full document)
- Confidence badge (color-coded: green ≥0.8, amber ≥0.6, red <0.6)
- Faithfulness score shown if available

### U-03 — Role-Aware Quick Chips
**Location**: `ChatInput.tsx` — appears below the text input
- Shows AI-suggested follow-up questions from the last response (dynamic)
- Falls back to role-specific default chips when input is empty:
  - `employee` — leave, reimbursement, benefits, hours
  - `hr_admin` — onboarding, headcount, policy, documents
  - `manager` — team leave, promotions, reviews, org chart
  - `super_admin` — tenants, metrics, audit, models
- Max 3 chips from AI suggestions, max 4 from defaults
- Disabled state when chat is loading

### U-04 — Session Sidebar
**Location**: `Sidebar.tsx`
- **Date grouping**: Today / Yesterday / This Week / Older
- **Search**: Appears when >4 sessions; real-time filter
- **Collapse mode**: Icon-only rail (16px icons) with tooltips
- **Mobile**: Full overlay on mobile with hamburger toggle from main header

### U-05 — Role-Based Navigation
- `employee`: Chat, Settings
- `hr_admin`: Chat, Dashboard, Upload Docs, Settings
- `super_admin`: Chat, Dashboard, Upload Docs, Settings (all hr_admin routes)

### U-06 — MFA Step-Up Login
**Location**: `LoginPage.tsx`
- Two states: `credentials` and `mfa`
- If `POST /auth/login` returns `{mfa_required: true, mfa_token: "..."}`:
  - Show TOTP code screen (ShieldCheck icon, numeric keypad hint)
  - Auto-focus on 6-digit input, large monospace font
  - Back button returns to credentials step

### U-07 — User Settings Page
**Location**: `UserSettingsPage.tsx`
Three-tab layout:

**Profile tab**
- Full Name, Department, Email, Phone fields
- PATCH `/api/v1/users/me` on save
- Propagates department change to sidebar user info via `onProfileUpdate` callback

**Security tab (MFA)**
- Status badge (Enabled / Disabled)
- Enrollment flow: `POST /compliance/mfa/enroll` → QR code + manual secret key + copy button
- Confirmation: 6-digit code → `POST /compliance/mfa/verify` → 8 recovery codes displayed once
- Recovery codes: grid display + one-click copy all
- Disable: requires current TOTP code → `DELETE /compliance/mfa/disable`

**Privacy tab (GDPR)**
- Download data export (Art. 15): calls `GET /api/v1/users/{id}/gdpr-export`, triggers browser download of JSON
- Account erasure (Art. 17): confirmation flow requiring user to type `DELETE MY ACCOUNT` exactly

### U-08 — Toast Notifications
**Location**: `NotificationToast.tsx`
- Context-based (`ToastProvider` wraps `App`, `useToastHelpers()` hook inside)
- Types: `success` (emerald), `error` (red), `warning` (amber), `info` (blue)
- Auto-dismiss: success/info 4s, warning 5s, error 6s (persistent with `duration: 0`)
- Slide-in from right, slide-out on dismiss; stacks vertically bottom-right
- Used in: settings save, MFA actions, GDPR export, session expiry

### U-09 — Mobile Responsive Design
- Desktop: persistent sidebar (collapsible to icon rail)
- Mobile (`md:` breakpoint): sidebar hidden by default, full-screen overlay when open
- Mobile header: hamburger `Menu` icon + company name
- All touch events (`touchstart`) included in inactivity timeout listener

### U-10 — Tenant Branding
- `GET /api/v1/tenants/me/branding` called on login
- `company_name` replaces "HR Chatbot" in sidebar header and browser `<title>`
- `primary_color` (not yet applied to CSS variables — future enhancement)
- Graceful fallback to `{ company_name: 'HR Chatbot' }` if endpoint is missing

---

## Data Flow

```
Login success
  └─► App fetches branding (getTenantBranding)
      ├─► sets document.title
      └─► passes companyName to Sidebar

Chat flow
  ├─► ChatPage → useChat hook → streaming SSE
  ├─► last assistant message's suggested_questions → ChatInput chips
  └─► feedback/escalation → POST /chat/feedback, /chat/escalate

Settings flow
  ├─► UserSettingsPage mounts → getMyProfile() → populate fields
  ├─► Save profile → PATCH /users/me → onProfileUpdate() → App state update
  └─► MFA enroll → QR → verify → recovery codes (shown once)
```

---

## API Additions (frontend/src/services/api.ts)

| Function | Method | Endpoint |
|---|---|---|
| `verifyMfaLogin` | POST | `/auth/mfa/verify-login` |
| `enrollMfa` | POST | `/api/v1/compliance/mfa/enroll` |
| `confirmMfaEnrollment` | POST | `/api/v1/compliance/mfa/verify` |
| `disableMfa` | DELETE | `/api/v1/compliance/mfa/disable` |
| `getMyProfile` | GET | `/api/v1/users/me` |
| `updateMyProfile` | PATCH | `/api/v1/users/me` |
| `exportGdprData` | GET | `/api/v1/users/{id}/gdpr-export` |
| `requestGdprErasure` | DELETE | `/api/v1/users/{id}/gdpr-erase` |
| `getTenantBranding` | GET | `/api/v1/tenants/me/branding` |

---

## Files Changed

| File | Change |
|---|---|
| `frontend/src/App.tsx` | ToastProvider, settings page, mobile header, branding fetch |
| `frontend/src/pages/LoginPage.tsx` | MFA step-up state (`credentials` → `mfa`) |
| `frontend/src/pages/UserSettingsPage.tsx` | **New** — Profile / Security / Privacy |
| `frontend/src/pages/ChatPage.tsx` | Pass `role` prop through to ChatWindow |
| `frontend/src/components/Sidebar.tsx` | Date grouping, search, collapse, mobile overlay |
| `frontend/src/components/ChatInput.tsx` | Role-aware quick chips + AI suggested chips |
| `frontend/src/components/ChatWindow.tsx` | Pass `role` + last `suggested_questions` to ChatInput |
| `frontend/src/components/NotificationToast.tsx` | **New** — ToastProvider + useToastHelpers |
| `frontend/src/services/api.ts` | MFA, profile, GDPR, branding endpoints |

---

## Backend Endpoints Required (for full UX completeness)

These endpoints are implemented in Phase 5 but need corresponding backend routes if not already present:

1. `POST /auth/mfa/verify-login` — validates TOTP during login flow; returns `access_token`
2. `GET /api/v1/users/me` — returns full profile (full_name, email, phone, department, totp_enabled)
3. `PATCH /api/v1/users/me` — updates profile fields
4. `GET /api/v1/tenants/me/branding` — returns `{company_name, primary_color, logo_url}`

Routes 1 and 3-4 may need to be added to `backend/app/api/` if not present from Phase 3/5.
