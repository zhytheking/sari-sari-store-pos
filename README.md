# Frontend JavaScript — File Ownership Map

**READ THIS BEFORE EDITING ANY `.js` FILE.**

Every utility lives in exactly ONE place. If you see the same
function defined twice, that is a bug — report it.

---

## `api-client.js` — The Canonical File

Defines:

- `API` (object with `.get`, `.post`, `.put`, `.delete`)
- `API.auth.*`, `API.products.*`, `API.sales.*`, `API.inventory.*`, `API.admin.*`, `API.settings.*`, `API.reports.*`
- `_getCookie(name)`, `getCsrfToken()`
- `escapeHtml(text)`, `formatCurrency(amount)`
- `_parseServerDate`, `formatDate`, `formatDateOnly`, `formatTimeOnly`
- `formatRelativeTime`, `renderRelativeTime`, `refreshRelativeTimes`
- `showToast(message, type)`
- `showLoading(msg)`, `hideLoading()`
- `getCart()`, `saveCart(cart)`, `updateCartBadge()`
- `debounce(fn, ms)`, `throttle(fn, ms)`
- `logoutUser(event)`, `toggleMenu()`, `clearAutofilledFields()`

**Do not redefine these anywhere else.**

---

## `main.js` — Page-Agnostic Behaviors

Only:

- Body fade-in on DOM ready
- `.alert` auto-dismiss after 5s

No utilities. No page logic.

---

## Page Files

| File | Loaded by | Owns |
|---|---|---|
| `login.js` | `templates/login.html` | Login form, role from URL, password toggle |
| `products.js` | `templates/products/list.html` | Product table, categories, filters, pagination |
| `dashboard_admin.js` | `templates/dashboard/admin.html` | Dashboard stats, recent sales, date |
| `dashboard_cashier.js` | `templates/dashboard/cashier.html` | Cashier stats, my recent sales |
| `cashier_sales.js` | `templates/dashboard/cashier_sales.html` | My Sales page, receipt modal |
| `all_sales.js` | `templates/dashboard/all-sales.html` | All Sales page, cashier breakdown |
| `pos.js` | `templates/dashboard/pos.html` | Cart, barcode scanner, payment |
| `reports.js` | `templates/dashboard/reports.html` | Report generation, CSV export |
| `stocks.js` | `templates/admin/stocks.html` | Stock add/remove/adjust, add product |
| `categories.js` | `templates/admin/categories.html` | Category list, add, delete |
| `settings.js` | `templates/admin/settings.html` | Store settings, GCash QR, passwords |

---

## Rules

1. Every template inherits from `base.html`.
2. `base.html` loads `api-client.js` then `main.js`.
3. Each template loads its own page JS via `{% block extra_js %}`.
4. **Never** load `api-client.js` twice.
5. **Never** add inline `<script>` blocks with page logic.
6. **Never** redefine any function listed under `api-client.js` in a page file.

---

## When Something Doesn't Work

Run the contract test:

```powershell
python -m pytest backend/test/test_frontend_contracts.py -v
