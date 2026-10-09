> Informe técnico de la API de Wompi Colombia (investigado el 2026-10-09 en docs.wompi.co, soporte.wompi.co y datos.gov.co). Los secretos de ejemplo de la documentación se reemplazaron por EJEMPLO_DE_LA_DOC.

# Wompi Colombia API: technical brief (researched 2026-10-09)

Sources are official only: docs.wompi.co (English pages, fetched raw as HTML on 2026-10-09), soporte.wompi.co, datos.gov.co.
Doc root: https://docs.wompi.co/en/docs/colombia/ (slugs: ambientes-y-llaves, tokens-de-aceptacion, transacciones, metodos-de-pago, fuentes-de-pago, fuentes-de-pago-3ds, fuentes-de-pago-3ds-sandbox, links-de-pago, widget-checkout-web, eventos, datos-de-prueba-en-sandbox, reembolsos-sandbox, errores).
Quotes are verbatim from the pages unless marked (paraphrase).

---------------------------------------------------------------------------
## 0. Recommended architecture (my inference, not in the docs)

- Top-ups: prefer Web Checkout / Widget with OUR OWN `reference` + integrity signature over Payment Links (links give no way to set a reference; see 3).
- Subscription: tokenize the card via the hosted Widget in tokenization mode (or encrypted POST /v1/tokens/cards) -> POST /v1/payment_sources (private key) -> each month POST /v1/transactions with `payment_source_id` + `recurrent: true`. Nequi: POST /v1/tokens/nequi -> wait for APPROVED -> payment source -> monthly transaction.
- Truth source for status: webhook `transaction.updated` (verified by checksum), with GET /v1/transactions/{id} (private key) as a server-side reconciliation fallback.

---------------------------------------------------------------------------
## 1. Base URLs and auth
Source: https://docs.wompi.co/en/docs/colombia/ambientes-y-llaves/

- Sandbox: `https://sandbox.wompi.co/v1`
- Production: `https://production.wompi.co/v1`
  (Quote: "For Sandbox the base URL that you must use is: https://sandbox.wompi.co/v1 / For Production ... https://production.wompi.co/v1")
- Keys: public `pub_test_...` / `pub_prod_...`; private `prv_test_...` / `prv_prod_...`; events secret `test_events_...` / `prod_events_...`; integrity secret `test_integrity_...` / `prod_integrity_...`.
  "Always take into account that when you are using the URL for an environments you need to use the correct keys for it."
  Environments are "completely independent from one another" (links, transactions made in sandbox are not visible in production).
- Header everywhere: `Authorization: Bearer <key>`. There is no HMAC request signing.
- Which key per endpoint (from the pages below):

| Endpoint | Key | Source |
|---|---|---|
| GET /merchants/info | public key in header `x-merchant-public-key` (NOT Authorization) | tokens-de-aceptacion |
| POST /tokens/cards, GET /tokens/keys/tokenization | public key as Bearer | metodos-de-pago |
| POST /tokens/nequi, GET /tokens/nequi/:token | public key ("with the public key as an authorizer") | fuentes-de-pago |
| POST /payment_links | private key Bearer ("Authorization: Bearer prv_test_...") | links-de-pago |
| GET /payment_links/:id | none ("This endpoint doesn't require any kind of authentication.") | links-de-pago |
| POST /payment_sources | private key, backend only ("requires the use of your private key ... Never do it from a user's device") for the normal (non-3DS) flow. The 3DS-sandbox page shows `Authorization: Bearer pub_test_your_public_key` for the 3DS flow (inconsistency, see section 13) | fuentes-de-pago, fuentes-de-pago-3ds-sandbox |
| POST /transactions (saved source) | private key, backend only | fuentes-de-pago, transacciones |
| GET /transactions/:id | private key only; "Requests without authentication or using a Public Key (pub_*) ... will return 404 Not Found" | transacciones, errores |
| POST /transactions/:id/void | private key | transacciones |
| POST /refunds (V2) | private key; public key -> 401/403 | reembolsos-sandbox |

- Docs inconsistency: card-tokenization code samples say `For Colombia use https://api.wompi.co/v1 as BASE_URL` (metodos-de-pago). The environments page says sandbox/production.wompi.co. Use the latter (the former is probably a legacy alias; untested).

---------------------------------------------------------------------------
## 2. Acceptance tokens
Source: https://docs.wompi.co/en/docs/colombia/tokens-de-aceptacion/

- NEW endpoint (use this one): `GET /merchants/info` with header `x-merchant-public-key: {{your_public_key}}`.
- DEPRECATION (verbatim): "The GET /merchants/:merchant_public_key endpoint (public key in the URL) will no longer be available after October 31, 2026. Migrate to the new GET /merchants/info endpoint with the public key in the x-merchant-public-key header before that date to avoid disruptions to your integration."
  (The old `GET /v1/merchants/{public_key}` still works until then; do not build on it.)
- Response (`data` also contains other business fields):
```
"presigned_acceptance":        { "acceptance_token": "eyJ...(JWT)", "permalink": "https://wompi.co/wp-content/uploads/2019/09/TERMINOS-Y-CONDICIONES-DE-USO-USUARIOS-WOMPI.pdf", "type": "END_USER_POLICY" },
"presigned_personal_data_auth": { "acceptance_token": "eyJ...(JWT)", "permalink": "https://wompi.com/assets/downloadble/autorizacion-administracion-datos-personales.pdf", "type": "PERSONAL_DATA_AUTH" }
```
- When required (verbatim): "in all those endpoints where a user's personal information is collected, such as when creating a transaction (POST /transactions) or a payment source (POST /payment_sources), you must send two Acceptance Tokens in the body of the request. One ... privacy policy (acceptance_token), and the other ... personal data processing (accept_personal_auth)."
- Body fields: `acceptance_token` = presigned_acceptance.acceptance_token; `accept_personal_auth` = presigned_personal_data_auth.acceptance_token.
- Explicit acceptance (verbatim): "The user must explicitly accept that they have read both contracts in the interface of your website or application, through checkboxes for example, and then the two tokens must be sent." Steps: 1 acquire tokens, 2 show links (the `permalink` PDFs), 3 make sure user accepted (one checkbox per contract), 4 send tokens.
- Token expiry: the JWT carries an `exp` claim (the sample payload decodes to an `exp`); the 400 error "Invalid acceptance token -> Generate a new acceptance token" implies fetch fresh, near the time of use. Exact lifetime NOT stated (I base64-decoded the sample JWTs: the END_USER_POLICY samples carry `exp` = `jit` + 3600 s, i.e. 1 hour; the PERSONAL_DATA_AUTH samples carry no `exp`. Samples only; treat as indicative.)
- Implication for monthly automatic charges: the two tokens are needed at payment-source creation (user present). The saved-source transaction examples (fuentes-de-pago step 3) do NOT include acceptance_token/accept_personal_auth. Whether POST /transactions with payment_source_id needs `acceptance_token` is not explicit (see 13). The generic transactions page lists `acceptance_token` as required.
- Hosted Widget/Checkout and Payment Links show the contracts themselves, so no acceptance tokens are needed on our side for those.

---------------------------------------------------------------------------
## 3. Payment links
Source: https://docs.wompi.co/en/docs/colombia/links-de-pago/

- `POST /v1/payment_links`, header `Authorization: Bearer prv_...`.
- Body (verbatim keys): required `name`, `description`, `single_use` (true = one APPROVED transaction only; false = multiple), `collect_shipping`. Docs also list `currency` ("Only COP"). Optional: `amount_in_cents` (null = customer chooses), `expires_at` (ISO 8601, UTC; docs example "2022-12-10 14:30:00"), `redirect_url`, `image_url`, `sku` ("Internal unique product identifier. 36 chars max."), `customer_data.customer_references[{label (24 chars max), is_required}]` (max 2), `taxes[{type: VAT|CONSUMPTION, amount_in_cents | percentage}]` (amount_in_cents must include taxes).
- Minimal example: `{"name":"Monthly rent - Wompi Tower Apartments","description":"Pay here your apartment monthly rent","single_use":false,"collect_shipping":false}`
- Response: `{"data":{"id":"3Z0Cfi","name":...,"single_use":true,"collect_shipping":false,"currency":"COP","amount_in_cents":null,"sku":null,"expires_at":null,"redirect_url":null,"image_url":null,"active":true,"customer_data":{...},"created_at":...,"updated_at":...,"merchant_public_key":"pub_prod_..."},"meta":{}}`
- Share URL (verbatim): `https://checkout.wompi.co/l/:payment_link_id` e.g. `https://checkout.wompi.co/l/3Z0Cfi`.
- Retrieve: `GET /v1/payment_links/:payment_link_id` (no auth).
- NO `reference` field exists on the payment link body. The docs do not say how the reference of a link-originated transaction is generated.
- Correlation: the webhook `data.transaction` has `payment_link_id` (event example shows `"payment_link_id": null` for a non-link transaction; the sandbox-data page shows `"payment_link_id": null` in a GET transaction response too). So the field exists in both. Strategy (inference): create one link per top-up (`single_use: true`, optional `expires_at`), store `{link_id -> our top-up id}`, and on `transaction.updated` match `transaction.payment_link_id`. `sku` is only on the link, not shown in the transaction/event body in the docs.
- Caveat: `redirect_url` to our site gets `?id=<transaction_id>` appended (same as checkout). Redirect is informational only.
- Support-site limits for links (from a search snippet, not opened in detail): min COP 2,500 / max COP 2,500,000 per link transaction; daily max COP 10,000,000 shared between link and card (see section 10; treat as uncertain).
- Reattempts (https://docs.wompi.co/en/docs/colombia/reintento-de-pago/): after a failed attempt the checkout lets the payer retry (3 min window) and "If you see one declined transaction and an approved one with the same reference, it means that it was done through the reattempting." -> one reference/link can produce several transactions; the webhook sends each. Key idempotency on transaction id, treat the reference/link as "paid" once any transaction is APPROVED.

---------------------------------------------------------------------------
## 4. Web Checkout / Widget and the integrity signature
Source: https://docs.wompi.co/en/docs/colombia/widget-checkout-web/

- Formula (verbatim): `"<Reference><Amount><Currency><IntegritySecret>"`; with expiration: `"<Reference><Amount><Currency><ExpirationDate><IntegritySecret>"`; SHA256, lowercase hex.
- Worked example (verified math): `sk8-438k4-xmxm392-sn2m` + `2490000` + `COP` + `prod_integrity_EJEMPLO_DE_LA_DOC` (el hash de ejemplo de la doc se calcula con su secreto de ejemplo; ver la URL citada) (python: `hashlib.sha256(s.encode()).hexdigest()`). With expiration `2023-06-09T20:28:50.000Z` the string is `...2490000COP2023-06-09T20:28:50.000Zprod_integrity_...`.
  Amount is `amount_in_cents` as an integer string with no separators. Expiration is the exact same string sent in `expiration-time`.
- "We recommend you to make this cryptography hash on the server side."
- Required params: `public-key`, `currency` (COP), `amount-in-cents`, `reference` ("once a reference is used for a payment on your account, it will not be possible to use it again"), `signature:integrity`.
  Optional: `redirect-url`, `expiration-time`, `customer-data:email|full-name|phone-number|phone-number-prefix|legal-id|legal-id-type`, `shipping-address:*`, `collect-shipping`, `collect-customer-legal-id`, `tax-in-cents:vat|consumption`, `payment-method` (PSE refs).
- Web Checkout: `<form action="https://checkout.wompi.co/p/" method="GET">` with hidden inputs named exactly as above (names use dashes, `signature:integrity`).
- Widget button: `<script src="https://checkout.wompi.co/widget.js" data-render="button" data-public-key="pub_..." data-currency="COP" data-amount-in-cents="4950000" data-reference="..." data-signature:integrity="..."></script>` inside a `<form>`; optional `data-redirect-url`, `data-expiration-time`, `data-customer-data:email`, etc.
- Custom button JS: `<script src="https://checkout.wompi.co/widget.js">` then `new WidgetCheckout({currency:'COP', amountInCents:2490000, reference:'...', publicKey:'pub_...', redirectUrl:'...', signature:{integrity:'...'} })` and `checkout.open(function(result){ result.transaction ... })`. (`signature: {integrity}` shown in the postMessage page: https://docs.wompi.co/en/docs/colombia/transporte-postmessage-widget/; the main page's JS example omits it but it is required.)
- Redirect (verbatim): "https://mystore.com.co/payments/result?id=01-1531231271-19365" - only `id` (transaction id) is appended. "Do not use the redirection as a validation method of your transactions, only for informative purposes."
- "Transaction queries from the frontend are no longer supported. Configure Webhooks."
- `redirect-url` "has to belong to your website".

---------------------------------------------------------------------------
## 5. Card tokenization (recurring) and Nequi tokenization

### Cards
Sources: https://docs.wompi.co/en/docs/colombia/metodos-de-pago/ , https://docs.wompi.co/en/docs/colombia/fuentes-de-pago/

a) API (card data touches OUR server): `POST /v1/tokens/cards`, `Authorization: Bearer <public key>`.
   - Encrypted (recommended): `GET /v1/tokens/keys/tokenization` -> `data.publicKey` (PEM); build a JWE (alg `RSA-OAEP-256`, enc `A256GCM`, compact serialization) over `{"number","cvc","exp_month" (2-digit string),"exp_year" (2 digits),"card_holder"}`; send `{"payload": "<jwe>"}`.
   - Simple: same endpoint, plain JSON body `{number, cvc, exp_month, exp_year, card_holder}` ("Use this option only if you cannot encrypt").
   - Response: `{"status":"CREATED","data":{"id":"tok_prod_1_...","created_at","brand":"VISA","name":"VISA-4242","last_four":"4242","bin","exp_year","exp_month","card_holder","expires_at"}}`. "Don't use a token more than once!"
   - Card must have CVC; only Visa/Mastercard ("as long as the card has a CVC").
b) Hosted Widget in tokenization mode (card data never touches our page) - verbatim from fuentes-de-pago ("Widget in tokenization mode"):
```html
<form method="POST" action="/process_token">
  <script
    src="https://checkout.wompi.co/widget.js"
    data-render="button"
    data-widget-operation="tokenize"
    data-public-key="pub_test_EJEMPLO_DE_LA_DOC"
  ></script>
</form>
```
   "With the token inside the response, you must do a POST to /v1/payment_sources from your server and using your private commerce key."
   NOT documented: the exact fields the widget submits to `action` (name of the hidden input, whether it is only the token id or the whole token object). Must be discovered by a sandbox test (see 13). The postMessage page confirms `bootstrapTransport: 'postmessage'` works "with the tokenization mode" (so a JS `WidgetCheckout` variant exists, but its tokenize config keys are not documented).
c) Antifraud script (optional but recommended): WompiJs `https://wompijs.wompi.com/libs/js/v1.js` with `data-public-key`, `$wompi.initialize(cb)` -> `data.sessionId`, `data.deviceData.deviceID`; send `session_id` (and `customer_data.device_id`) with payment source/transaction. Source: https://docs.wompi.co/en/docs/colombia/latest-version/ (the older cdn.wompi.co/libs/js/v1.js is "deprecated").

### Nequi
Source: fuentes-de-pago
- `POST /v1/tokens/nequi`, public key, body `{"phone_number": "3017654321"}` (10-digit Colombian mobile).
- Response `{"data":{"id":"nequi_prod_RQkUiuv3lEnDLiSao2Cz0iQLdFlyQOI5","status":"PENDING","phone_number":"3107654321","name":"Company Name"}}`; "the customer still needs to accept the subscription on his cellphone, so that the status changes from "PENDING" to "APPROVED"."
- Poll: `GET /v1/tokens/nequi/:nequi_token`; "Once you get an APPROVED string in the "status" property, it will be possible to properly create the payment source." (Docs show public key as authorizer for the POST; the GET auth is not stated: use the public key too (inference).)
- Event alternative to polling: `nequi_token.updated` (APPROVED or DECLINED) - eventos page.
- Then POST /v1/payment_sources with `{"type":"NEQUI","token":"nequi_...","customer_email",...,"acceptance_token","accept_personal_auth"}` -> `{"data":{"id":3891,"public_data":{"type":"NEQUI","phone_number":"..."},"type":"NEQUI","status":"AVAILABLE"}}`.
- Recurring Nequi charge: same POST /v1/transactions with `payment_source_id`; the docs say for non-card sources "ignore the payment_method field altogether". Each charge triggers a push to the user's Nequi app? NOT stated for subscription charges (a plain Nequi payment sends a push that must be accepted). Treat as uncertain; test in sandbox/prod with a real small amount.

---------------------------------------------------------------------------
## 6. Payment sources
Source: https://docs.wompi.co/en/docs/colombia/fuentes-de-pago/

- `POST /v1/payment_sources`, private key (backend only).
- Required (verbatim): `customer_email`; `type` ("CARD" or "NEQUI" (also DAVIPLATA, BANCOLOMBIA_TRANSFER)); `token`; `acceptance_token`; `accept_personal_auth`.
- Card body: `{"type":"CARD","token":"tok_prod_1_...","customer_email":"john_smith@example.com","acceptance_token":"eyJ...","accept_personal_auth":"eyJ..."}` (optional: `session_id`, `customer_data{device_id,full_name,phone_number}` from the WompiJs page).
- Response: `{"data":{"id":3891,"public_data":{"type":"CARD"},"type":"CARD","status":"AVAILABLE"}}` ("indicating the payment source was created and is available to use"). The `id` is an integer used as `payment_source_id`.
  (The 3DS page shows a richer card `public_data`: bin, last_four, exp_month, exp_year, card_holder, validity_ends_at, type.)
- Statuses seen: `AVAILABLE`, `PENDING` (3DS in progress), `DECLINED`, `ERROR`, `VOIDED`.
- Get: `GET /v1/payment_sources/{id}` (shown with public key in 3DS sandbox page, https://docs.wompi.co/en/docs/colombia/fuentes-de-pago-3ds-sandbox/ ; auth for non-3DS usage not explicit: private key from the backend should work (inference)).
- Void/cancel: `PUT /v1/payment_sources/{id}/void` with private key -> `status: "VOIDED"`; "if you attempt to create a transaction with this payment source, it will not be possible." (documented for DAVIPLATA/BANCOLOMBIA; presumably works for all - uncertain for CARD/NEQUI).
- Optional 3DS for the source (needs activation by Wompi's fraud team): 3DS for sources works for Mastercard and Visa; 3RI (automatic charges under 3DS protection) only Mastercard; flow = POST source -> poll `GET /payment_sources/{id}` every 2 s through `extra.three_ds_auth.current_step` (BROWSER_INFO, FINGERPRINT, CHALLENGE, AUTHENTICATION) until status `AVAILABLE|DECLINED|ERROR`. Sandbox 3DS cards: `2303 7799 5100 0446` (challenge), `2303 7799 5100 0354` (auth error), `2303 7799 5100 0347` (supported-version error). Request activation via Wompi support ("3D Secure Activation for Payment Sources - production"). This is NOT required for the basic flow; it is an add-on that needs front-end iframe work. Sources: fuentes-de-pago-3ds, fuentes-de-pago-3ds-sandbox.

---------------------------------------------------------------------------
## 7. Charging a saved source
Sources: https://docs.wompi.co/en/docs/colombia/fuentes-de-pago/ (step 3), https://docs.wompi.co/en/docs/colombia/transacciones/

- `POST /v1/transactions`, `Authorization: Bearer prv_...` (backend).
- Example 1 in fuentes-de-pago (with signature):
```json
{ "amount_in_cents": 4990000, "currency": "COP", "signature": "37c8...3bf5", "customer_email": "example@gmail.com",
  "payment_method": { "installments": 2 }, "reference": "sJK4489dDjkd390ds02", "payment_source_id": 3891 }
```
  "Number of installment if the payment source represents a card otherwise ignore the payment_method field altogether."
- COF/recurring example (without signature in the doc):
```json
{ "amount_in_cents": 4990000, "currency": "COP", "customer_email": "example@gmail.com",
  "payment_method": { "installments": 2 }, "reference": "sJK4489dDjkd390ds02", "payment_source_id": 3891, "recurrent": true }
```
  `recurrent` (verbatim): "true: ... subsequent charges for the same amount to be made periodically. (COF sales transaction with recurrence). false: ... charges for different amounts ... without any type of periodicity. (Stored COF sales transaction)." "If recurrent is not send, the transaction will be carried out without COF"; also ignored for non-Mastercard/Visa cards or when the commerce's processor is not RBM. Docs also say "paid_source_id [sic] becomes a mandatory field" with `recurrent`.
  For top-up style variable amounts use `recurrent: false`; for a fixed monthly fee use `true`.
- Required params per the generic transactions page (https://docs.wompi.co/en/docs/colombia/transacciones/): `acceptance_token`, `amount_in_cents` (integer), `currency` ("Only COP"), `customer_email`, `payment_method` (object), `reference` (max 255 chars, unique per transaction), `signature` (integrity signature). Optional: `customer_data`, `redirect_url`, `ip` (recommended; capture on backend, X-Forwarded-For), `session_id`.
  -> SIGNATURE: the transactions page lists `signature` as required and links to "Widget & Checkout Web - Generate an integrity signature" (same formula: reference + amount_in_cents + currency + integrity secret; no expiration unless used). So yes, send it also with private-key requests. Safe choice: ALWAYS include it. (The COF example omitting it is likely just abbreviated; not confirmed.)
- Response 201: `{"data":{"id":"1292-1602113476-10985","reference":"...","created_at","amount_in_cents","currency":"COP","customer_email","payment_method_type":"CARD","status":"PENDING","status_message":"The transaction is being processed","merchant":{...},"payment_method":{...}}}`. Transaction id format `<n>-<epoch>-<n>`; saved-source transactions webhook shows `payment_source_id`.
- Statuses: PENDING, APPROVED, DECLINED ("insufficient funds, invalid data, etc."), VOIDED ("only applies to credit/debit card"), ERROR. "A newly created transaction always has a PENDING status."
- Poll: `GET /v1/transactions/{id}` with the private key -> `{"data":{"id","reference","status","amount_in_cents","currency","payment_method_type","status_message"}}`; for cards `payment_method.extra.processor_response_code` ("e.g. 51") and `status_message` (e.g. "Fondos Insuficientes") are present (metodos-de-pago).
  Note: the docs present both statements: "Direct queries from the frontend are no longer supported" (use webhooks) AND, on metodos-de-pago, "we recommend periodically verifying (long polling)". Server-side polling with the private key is fine and supported; frontend/public-key polling is not.
- Errors: 422 INPUT_VALIDATION_ERROR with `{"error":{"type":"INPUT_VALIDATION_ERROR","messages":{"reference":["The reference has already been used."]}}}`; 401 invalid key; 404 NOT_FOUND_ERROR (also for unauthenticated/public-key transaction GET); 400 invalid acceptance token / incomplete payment method (https://docs.wompi.co/en/docs/colombia/errores/).
- Idempotency: a reference can only be used once per account -> use a deterministic reference per billing period (e.g. `sub-<id>-2026-11`) so a retried POST cannot double charge (duplicate reference -> 422). Caveat: a declined transaction also burns the reference, so retry attempts need a suffix (e.g. `...-r2`), and inside checkout "reattempts" reuse the same reference (see 3).
- 3DS: NOT required for charging a saved source in the basic flow; optional protection (Mastercard 3RI) once the source was created with 3DS and the account has it activated.
- Minimum amount: see 10 (support articles: COP 1,500 for Aggregator model, COP 1 for Gateway model; plan-dependent).

---------------------------------------------------------------------------
## 8. Events (webhooks)
Source: https://docs.wompi.co/en/docs/colombia/eventos/

- Config: set the events URL in the Commerce Dashboard, one URL per environment (sandbox and production separately).
- Event types: `transaction.updated` (final states APPROVED/VOIDED/DECLINED/ERROR), `nequi_token.updated` (APPROVED or DECLINED), `bancolombia_transfer_token.updated`.
- Body (verbatim example):
```json
{
  "event": "transaction.updated",
  "data": { "transaction": {
      "id": "01-1532941443-49201", "amount_in_cents": 4490000, "reference": "MZQ3X2DE2SMX",
      "customer_email": "john.doe@gmail.com", "currency": "COP", "payment_method_type": "NEQUI",
      "redirect_url": "https://mystore.com.co/payments/redirect", "status": "APPROVED",
      "shipping_address": null, "payment_link_id": null, "payment_source_id": null } },
  "sent_at": "2018-07-20T16:45:05.000Z",
  "signature": { "checksum": "3476DDA50F64CD7CBD160689640506FEBEA93239BC524FC0469B2C68A3CC8BD0",
                 "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
                 "timestamp": 1530291411 }
}
```
- Signature algorithm (verbatim steps):
  1. Concatenate the values of the fields named in `signature.properties`, in that order (each property is a dotted path into `data`, e.g. `transaction.id` -> `data.transaction.id`) -> `1234-1610641025-49201APPROVED4490000`
  2. Append `timestamp` (integer from `signature.timestamp`) -> `...44900001530291411`
  3. Append the Events secret (dashboard > "Secrets of technical integration"; `test_events_...` / `prod_events_...`) -> `...1530291411prod_events_EJEMPLO_DE_LA_DOC`
  4. SHA256 hex (php `hash("sha256", $s)`; ruby `Digest::SHA256.hexdigest`) -> `3476DDA50F64CD7CBD160689640506FEBEA93239BC524FC0469B2C68A3CC8BD0`
  5. "Compare your calculated checksum against the value in either the `X-Event-Checksum` HTTP header or the `signature.checksum` field. If they match, the event is legitimate; otherwise, discard it."
  Docs note: "The `properties` array can vary per event" (paraphrase) -> resolve dynamically, do not hard-code. The docs' example shows UPPERCASE hex while step 4's PHP/Ruby output is lowercase: compare case-insensitively with a constant-time compare.
  Inconsistency to know: the sample concatenation (`1234-1610641025-49201APPROVED4490000`) does not match the sample body's `id`/`amount` (docs example is illustrative); do not use it as a unit-test vector except for the hash step. A self-made vector is safer.
  Replay protection is NOT described; if wanted, reject old `timestamp` (our choice) and dedupe on transaction id + status.
- Retry (verbatim): "Whenever the HTTP status of your response is not 200, Wompi will consider that the event could not be notified correctly and will retry ... maximum 3 times during the next 24 hours, until obtaining a 200 response. The first retry will be carried out 30 minutes later, the second one at 3 hours and the last one after 24 hours."
- Expected response: HTTP status `200`; body ignored (empty is fine). Must be exactly 200 (a 201/204 is, by the docs' wording, a failure; return 200).
- Timeout: NOT STATED.
- `sent_at`: "Exact date at which the event was notified the first time".
- HTTPS recommended. Source IPs: NOT STATED.
- Nequi token events and data shape of `nequi_token.updated`: only named, body not documented (probably `data.nequi_token` with id/status; unverified).

---------------------------------------------------------------------------
## 9. Sandbox test data
Source: https://docs.wompi.co/en/docs/colombia/datos-de-prueba-en-sandbox/

- Cards (used with the tokenization endpoint or the widget): `4242 4242 4242 4242` -> APPROVED; `4111 1111 1111 1111` -> DECLINED; "If you use any other card ... the final status of the transaction will be ERROR." Any future expiry date and any 3-digit CVC.
- Nequi: `3991111111` -> APPROVED; `3992222222` -> DECLINED; any other number -> ERROR. (Documented for transactions; I assume the same numbers drive Nequi token approval in sandbox; not explicit for /tokens/nequi.)
- PSE: `financial_institution_code` "1" approved, "2" declined. Daviplata OTP `574829` approved, etc. (not needed).
- 3DS test cards: see section 6; `4242 4242 4242 4242` also supports the 3DS transaction scenarios (`three_ds_auth_type`: no_challenge_success, challenge_denied, challenge_v2, supported_version_error, authentication_error) per https://docs.wompi.co/en/docs/colombia/transacciones-con-3d-secure-v2/ .
- Refund V2 sandbox: `test_scenario` approved|declined|error|cancelled.
- No documented way to force a failed *recurring* charge on a saved source (e.g. a source created from 4111... would likely be DECLINED at charge time: inference, test it).

---------------------------------------------------------------------------
## 10. Currency, amounts and limits

- Currency: COP only ("Transaction currency. Only COP (Colombian pesos) is currently available." transacciones; same for links and widget). No USD. Prices in USD must be converted to COP by us (see TRM below).
- `amount_in_cents`: integer; "10000 = $100 COP" (transacciones) and "if you wish to charge $95.000 COP, you will enter: 9500000" (widget page) -> amount_in_cents = pesos x 100. Taxes inside `taxes` are informational and already included in the total.
- Minimums (support center, not the API docs; plan-dependent):
  - https://soporte.wompi.co/hc/es-419/articles/360038824313--Cu%C3%A1l-es-el-monto-m%C3%ADnimo-para-realizar-una-transacci%C3%B3n : "Agregador: desde $1.500; Gateway: desde $1".
  - https://soporte.wompi.co/hc/es-419/articles/360054848834--Cu%C3%A1l-es-el-tope-m%C3%ADnimo-o-m%C3%A1ximo-por-transacci%C3%B3n-si-pertenezco-al-modelo-Gateway : "los topes asignados son ilimitados; adicional el tope mínimo ... es de 1500 pesos" (Gateway with Bancolombia acquiring).
  - A search snippet (not verified on the page) said cards min 1,500 / max 250,000 and payment links min 2,500 / max 2,500,000, daily cap 10,000,000 (https://soporte.wompi.co/hc/es-419/articles/360020767434--Cu%C3%A1ntas-transacciones-m%C3%A1ximas-puedo-hacer-o-recibir-al-d%C3%ADa , page text did not render in my fetch). Treat max limits as account-specific; confirm in the merchant dashboard.
  - Nequi: no limit if the collecting account is a Bancolombia account; for a Nequi collecting account with caps, monthly balance cap COP 10,482,689.50 ("Actualidad 2025") (https://soporte.wompi.co/hc/es-419/articles/1500007715022--Cu%C3%A1l-es-el-monto-m%C3%ADnimo-y-m%C3%A1ximo-para-recibir-pagos-por-Nequi).
  - Rates (search snippet from https://wompi.com/es/co/planes-tarifas/): advanced plan cards "2.65% + $700 + IVA" (unverified, check page; it matters for pricing top-ups).
- Rate limits of the API: NOT FOUND.

---------------------------------------------------------------------------
## 11. Voids and refunds
Sources: https://docs.wompi.co/en/docs/colombia/transacciones/ , https://docs.wompi.co/en/docs/colombia/reembolsos-sandbox/

- Void: `POST /v1/transactions/{transaction_id}/void`, private key; "card transactions only, specific statuses only" (the docs' example typo says `priv_prod_xxx`). Status becomes VOIDED. Which statuses/time window: NOT STATED.
- Refunds V2: `POST /v1/refunds`, private key. Body: `transaction_id` (required, approved tx), `amount_in_cents` (required, total or partial), optional `reason`, `reference`..`reference_5`. Response `{"data":{"id","status":"APPROVED","status_message","v2_refund_id","amount_in_cents","transaction_id","reference",...,"created_at"}}`; statuses APPROVED/DECLINED/ERROR/CANCELLED. Available for Colombia (COP). The page is titled "Refunds V2 (Sandbox)"; the legacy V1 is `POST /v1/transactions/:id/refunds` (not processed by sandbox V2 logic). Whether V2 is live in production for all accounts: NOT clear.
- Refund of Nequi transactions: NOT STATED.
- Payment source void: section 6.

---------------------------------------------------------------------------
## 12. TRM (USD -> COP, official)

Free, no key, server-side friendly: Socrata open data of Colombia, dataset "Tasa de Cambio Representativa del Mercado- TRM", id `32sa-8pi3`.
- Latest rows (tested 2026-10-09):
  `GET https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=3&$order=vigenciadesde%20DESC`
  -> `[{"valor":"3218.75","unidad":"COP","vigenciadesde":"2026-10-09T00:00:00.000","vigenciahasta":"2026-10-09T00:00:00.000"}, {"valor":"3238.88",... "2026-10-08"}, {"valor":"3216.01",... "2026-10-07"}]`
- Fields: `valor` (string number, COP per 1 USD), `unidad` ("COP"), `vigenciadesde`, `vigenciahasta` (floating timestamps, date range during which the rate applies; weekend/holiday rates normally span a range).
- Rate valid on a date D: `GET https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde%3C='2026-10-09T00:00:00' AND vigenciahasta%3E='2026-10-09T00:00:00'` (tested, returned the 3218.75 row). Fallback: latest row ordered by vigenciadesde.
- Metadata: https://www.datos.gov.co/api/views/32sa-8pi3.json (columns: valor number, unidad text, vigenciadesde/vigenciahasta calendar_date; rowsUpdatedAt epoch 1791500762). Socrata may throttle anonymous clients (optional `X-App-Token`); cache the value for the day.
- Banco de la República alternative: not researched (the Socrata dataset is the official TRM from the Superfinanciera published by the Gobierno).

---------------------------------------------------------------------------
## 13. NOT FOUND / UNCERTAIN list (verify in sandbox or ask Wompi support)

1. Output of the tokenization Widget (`data-widget-operation="tokenize"`): which field names are POSTed to the form action / what the callback receives. Docs only say "With the token inside the response".
2. Whether POST /transactions with `payment_source_id` requires `signature`, `acceptance_token` and `accept_personal_auth`. Examples conflict (one has `signature`, the COF one has neither). Generic page says all are required. Plan: send signature always; test without acceptance_token in sandbox.
3. How the `reference` of a transaction created through a Payment Link is generated, and whether the link's `sku` appears in the transaction/event. Only `payment_link_id` is documented in the event body.
4. Auth for `GET /v1/payment_sources/{id}` outside 3DS (public key shown in 3DS flow). And whether POST /payment_sources accepts the public key (3DS page shows public; main page says private only).
5. Webhook delivery timeout, source IPs, replay window, `nequi_token.updated` body shape.
6. Lifetime of the acceptance tokens (JWT `exp`; likely about 1 h from the sample).
7. Maximum amount per card / link transaction, API rate limits, and which minimum applies to our account (Agregador 1,500 vs Gateway 1): depends on the commercial model.
8. Whether Nequi payment-source charges require the user to approve a push each time (a plain Nequi payment does). A silent recurring Nequi debit is not confirmed by the docs.
9. Void time windows; refund V2 availability in production; Nequi refunds.
10. `recurrent: true` only has effect for Visa/Mastercard on the RBM processor; behaviour with other processors/cards is a plain charge. Whether our merchant uses RBM: ask Wompi.
11. Card tokens `expires_at` (sample "2020-06-30") and whether an unused token expires quickly (create the payment source immediately after tokenization).
12. Docs mention `api.wompi.co/v1` as BASE_URL in the tokenization code samples; environments page says `production.wompi.co/v1`. Use the latter.
13. Spanish pages (docs.wompi.co/docs/colombia/...) were not read; English pages match what was reported by search results. The API reference (Swagger, https://app.swaggerhub.com/apis-docs/waybox/wompi/1.2.0) was not opened (JS app).
14. Fees were only seen in search snippets (2.65% + $700 + IVA for cards, Nequi ~1%): verify at https://wompi.com/es/co/planes-tarifas/ before showing prices.
